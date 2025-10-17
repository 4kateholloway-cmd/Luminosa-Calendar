# app.py — fallback version (no OR-Tools required)

import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Physician Call Scheduler (Fallback)", layout="wide")
st.title("Physician Call Scheduler — Fallback (No OR-Tools)")
st.caption("Upload doctors, shifts, and vacations CSVs, then click Generate. Uses a simple round-robin algorithm with PTO blocking.")

with st.expander("CSV format help", expanded=False):
    st.markdown("""
    **doctors.csv**
    - Columns: `id` (int), `name` (str), `fte` (float)

    **shifts.csv**
    - Columns: `id` (int), `start` (YYYY-MM-DD HH:MM), `end` (YYYY-MM-DD HH:MM), `kind` (str), `is_weekend` (bool), `is_holiday` (bool)

    **vacations.csv** (optional)
    - Columns: `doctor_id` (int), `start` (date or datetime), `end` (date or datetime)
    """)

col1, col2, col3 = st.columns(3)
with col1:
    doctors_file = st.file_uploader("Upload doctors.csv", type=["csv"], key="doctors")
with col2:
    shifts_file = st.file_uploader("Upload shifts.csv", type=["csv"], key="shifts")
with col3:
    vacations_file = st.file_uploader("Upload vacations.csv (optional)", type=["csv"], key="vacations")

def parse_bool(x):
    if isinstance(x, bool): return x
    s = str(x).strip().lower()
    return s in ("1","true","t","yes","y")

def load_data():
    if not doctors_file or not shifts_file:
        st.stop()
    doctors = pd.read_csv(doctors_file)
    shifts = pd.read_csv(shifts_file)
    vacations = pd.read_csv(vacations_file) if vacations_file else pd.DataFrame(columns=["doctor_id","start","end"])

    # normalize types
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
WEEKEND_WEIGHT = st.number_input("Weekend weight (for summary only)", value=1.5, step=0.1, min_value=0.0)
HOLIDAY_WEIGHT = st.number_input("Holiday weight (for summary only)", value=2.0, step=0.1, min_value=0.0)

def overlaps(a_start, a_end, b_start, b_end):
    return not (a_end <= b_start or a_start >= b_end)

def fallback_round_robin(doctors_df, shifts_df, vacations_df):
    """Assigns shifts in order, skipping doctors who are on PTO for that shift.
       Simple and predictable; does NOT enforce rest windows or complex fairness.
    """
    d_ids = doctors_df["id"].tolist()
    name_by_id = dict(zip(doctors_df["id"], doctors_df["name"]))
    vac_map = {}
    for _, v in vacations_df.iterrows():
        vac_map.setdefault(int(v["doctor_id"]), []).append((v["start"], v["end"]))

    rows = []
    ix = 0
    for _, sh in shifts_df.sort_values(["start","id"]).iterrows():
        assigned = False
        tried = 0
        while tried < len(d_ids):
            d = d_ids[ix % len(d_ids)]
            ix += 1
            tried += 1

            # block if PTO overlaps
            blocked = False
            for (vs, ve) in vac_map.get(int(d), []):
                if overlaps(sh["start"], sh["end"], vs, ve):
                    blocked = True
                    break
            if blocked:
                continue

            # assign!
            rows.append({
                "shift_id": int(sh["id"]),
                "start": sh["start"],
                "end": sh["end"],
                "kind": sh["kind"],
                "is_weekend": bool(sh["is_weekend"]),
                "is_holiday": bool(sh["is_holiday"]),
                "doctor_id": int(d),
                "doctor": name_by_id[d],
            })
            assigned = True
            break

        if not assigned:
            return None, f"Could not place shift {sh['id']} ({sh['start']}→{sh['end']}) due to overlapping PTO for all doctors."

    out = pd.DataFrame(rows).sort_values(["start","shift_id"]).reset_index(drop=True)
    return out, None

def add_weights(df):
    w = []
    for _, r in df.iterrows():
        wt = 1.0
        if r["is_weekend"]: wt *= WEEKEND_WEIGHT
        if r["is_holiday"]: wt *= HOLIDAY_WEIGHT
        w.append(wt)
    df = df.copy(); df["weight"] = w
    return df

if st.button("Generate Schedule", type="primary"):
    try:
        doctors, shifts, vacations = load_data()
    except Exception as e:
        st.error(f"Error reading CSVs: {e}")
        st.stop()

    schedule, err = fallback_round_robin(doctors, shifts, vacations)
    if err:
        st.error(err)
    else:
        st.success("Schedule generated (fallback mode).")
        st.dataframe(schedule, use_container_width=True)

        # Download CSV
        csv = schedule.to_csv(index=False).encode("utf-8")
        st.download_button("Download schedule.csv", data=csv, file_name="schedule.csv", mime="text/csv")

        # Fairness summary (informational)
        st.subheader("Fairness summary (informational)")
        weighted = add_weights(schedule)
        summary = weighted.groupby("doctor").agg(
            shifts=("shift_id","count"),
            weighted_calls=("weight","sum"),
            weekends=("is_weekend","sum"),
            holidays=("is_holiday","sum"),
        ).reset_index()
        st.dataframe(summary, use_container_width=True)

else:
    st.info("Upload your CSVs and click **Generate Schedule**.")




