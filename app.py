
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from ortools.sat.python import cp_model

st.set_page_config(page_title="Physician Call Scheduler (MVP)", layout="wide")

st.title("Physician Call Scheduler (MVP)")
st.caption("Upload your doctors, shifts, and vacations CSVs, then click **Generate Schedule**.")

with st.expander("CSV format help", expanded=False):
    st.markdown("""
    **doctors.csv** (required)
    - Columns: `id` (int), `name` (str), `fte` (float)
    
    **shifts.csv** (required)
    - Columns: `id` (int), `start` (ISO datetime), `end` (ISO datetime), `kind` (str), `is_weekend` (bool), `is_holiday` (bool)
    - Example datetime: `2025-10-01 07:00`
    
    **vacations.csv** (optional)
    - Columns: `doctor_id` (int), `start` (ISO datetime or date), `end` (ISO datetime or date)
    """)

col1, col2, col3 = st.columns(3)
with col1:
    doctors_file = st.file_uploader("Upload doctors.csv", type=["csv"], key="doctors")
with col2:
    shifts_file = st.file_uploader("Upload shifts.csv", type=["csv"], key="shifts")
with col3:
    vacations_file = st.file_uploader("Upload vacations.csv (optional)", type=["csv"], key="vacations")

def parse_bool(x):
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    return s in ("1", "true", "t", "yes", "y")

def load_data():
    if not doctors_file or not shifts_file:
        st.stop()
    doctors = pd.read_csv(doctors_file)
    shifts = pd.read_csv(shifts_file)
    vacations = pd.read_csv(vacations_file) if vacations_file else pd.DataFrame(columns=["doctor_id","start","end"])
    # Normalize
    doctors["id"] = doctors["id"].astype(int)
    doctors["fte"] = doctors["fte"].astype(float)
    shifts["id"] = shifts["id"].astype(int)
    shifts["start"] = pd.to_datetime(shifts["start"])
    shifts["end"] = pd.to_datetime(shifts["end"])
    shifts["is_weekend"] = shifts["is_weekend"].apply(parse_bool)
    shifts["is_holiday"] = shifts["is_holiday"].apply(parse_bool)
    if not vacations.empty:
        vacations["doctor_id"] = vacations["doctor_id"].astype(int)
        vacations["start"] = pd.to_datetime(vacations["start"])
        vacations["end"] = pd.to_datetime(vacations["end"])
    return doctors, shifts, vacations

st.markdown("---")
WEEKEND_WEIGHT = st.number_input("Weekend weight", value=1.5, step=0.1, min_value=0.0)
HOLIDAY_WEIGHT = st.number_input("Holiday weight", value=2.0, step=0.1, min_value=0.0)
MIN_REST_HOURS = st.number_input("Min rest between calls (hours)", value=24, step=1, min_value=0)

def shift_weight(row):
    w = 1.0
    if row["is_weekend"]:
        w *= WEEKEND_WEIGHT
    if row["is_holiday"]:
        w *= HOLIDAY_WEIGHT
    return w

def solve(doctors_df, shifts_df, vacations_df):
    model = cp_model.CpModel()
    D = len(doctors_df)
    S = len(shifts_df)
    # Variables
    x = {}
    for s in range(S):
        for d in range(D):
            x[(s,d)] = model.NewBoolVar(f"x_s{s}_d{d}")
    # Each shift covered exactly once
    for s in range(S):
        model.Add(sum(x[(s,d)] for d in range(D)) == 1)
    # Vacations: block assignments that overlap
    vac_map = {}
    for _, v in vacations_df.iterrows():
        vac_map.setdefault(int(v["doctor_id"]), []).append((v["start"], v["end"]))
    for s, sh in shifts_df.reset_index().iterrows():
        for d, doc in doctors_df.reset_index().iterrows():
            blocks = False
            for (vs, ve) in vac_map.get(int(doc["id"]), []):
                if not (sh["end"] <= vs or sh["start"] >= ve):
                    blocks = True
                    break
            if blocks:
                model.Add(x[(s,d)] == 0)
    # Min rest between calls
    for d in range(D):
        for s1 in range(S):
            for s2 in range(S):
                if s1 >= s2: 
                    continue
                dt = (shifts_df.iloc[s2]["start"] - shifts_df.iloc[s1]["end"]).total_seconds() / 3600.0
                if -MIN_REST_HOURS < dt < MIN_REST_HOURS:
                    model.Add(x[(s1,d)] + x[(s2,d)] <= 1)
    # Balancing objective (weighted)
    weights = shifts_df.apply(shift_weight, axis=1).tolist()
    total_weight = sum(weights)
    total_fte = doctors_df["fte"].sum()
    target_per_fte = total_weight / total_fte if total_fte > 0 else 0.0
    totals = []
    devs = []
    for d, doc in doctors_df.reset_index().iterrows():
        tot = model.NewIntVar(0, 100000, f"tot_d{d}")
        # Multiply by 100 to avoid floats
        model.Add(tot == sum(int(weights[s]*100) * x[(s,d)] for s in range(S)))
        totals.append(tot)
        target = int(target_per_fte * float(doc["fte"]) * 100)
        dev_pos = model.NewIntVar(0, 100000, f"devp_d{d}")
        dev_neg = model.NewIntVar(0, 100000, f"devn_d{d}")
        model.Add(tot - target == dev_pos - dev_neg)
        devs += [dev_pos, dev_neg]
    # Small penalty for consecutive days
    consec_hits = []
    for d in range(D):
        for s in range(S-1):
            hit = model.NewBoolVar(f"consec_d{d}_s{s}")
            model.Add(hit >= x[(s,d)] + x[(s+1,d)] - 1)
            consec_hits.append(hit)
    model.Minimize(10 * sum(devs) + 1 * sum(consec_hits))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0
    res = solver.Solve(model)
    if res not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, "No feasible schedule with the current constraints."
    # Build output
    rows = []
    for s, sh in shifts_df.reset_index().iterrows():
        for d, doc in doctors_df.reset_index().iterrows():
            if solver.Value(x[(s,d)]) == 1:
                rows.append({
                    "shift_id": int(sh["id"]),
                    "start": sh["start"],
                    "end": sh["end"],
                    "kind": sh["kind"],
                    "is_weekend": bool(sh["is_weekend"]),
                    "is_holiday": bool(sh["is_holiday"]),
                    "doctor_id": int(doc["id"]),
                    "doctor": str(doc["name"]),
                })
    out = pd.DataFrame(rows).sort_values(["start","shift_id"]).reset_index(drop=True)
    return out, None

if st.button("Generate Schedule", type="primary"):
    try:
        doctors, shifts, vacations = load_data()
    except Exception as e:
        st.error(f"Error reading CSVs: {e}")
        st.stop()
    schedule, err = solve(doctors, shifts, vacations)
    if err:
        st.error(err)
    else:
        st.success("Schedule generated!")
        st.dataframe(schedule, use_container_width=True)
        # Download as CSV
        csv = schedule.to_csv(index=False).encode("utf-8")
        st.download_button("Download schedule.csv", data=csv, file_name="schedule.csv", mime="text/csv")
        # Basic fairness summary
        st.subheader("Fairness summary")
        weights = []
        for _, row in schedule.iterrows():
            w = 1.0
            if row["is_weekend"]:
                w *= WEEKEND_WEIGHT
            if row["is_holiday"]:
                w *= HOLIDAY_WEIGHT
            weights.append(w)
        schedule["weight"] = weights
        summary = schedule.groupby(["doctor"]).agg(
            shifts=("shift_id","count"),
            weighted_calls=("weight","sum")
        ).reset_index()
        st.dataframe(summary, use_container_width=True)
else:
    st.info("Upload your CSVs, tune weights and rest hours, then click **Generate Schedule**.")
    # redeploy



