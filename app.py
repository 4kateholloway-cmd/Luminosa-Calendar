# app.py — Luminosa Call Scheduler (Fallback, calendar + manual doctors editor)
# requirements.txt:
# streamlit==1.40.0
# pandas==2.2.3
# numpy==2.1.3
# streamlit-calendar==1.0.0

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="Physician Call Scheduler", layout="wide")
st.title("Physician Call Scheduler — Fallback (No OR-Tools)")
st.caption("Upload CSVs or build your doctor list in-app. Uses a simple round-robin algorithm with PTO blocking. Calendar view included.")

# ---------- Sidebar options ----------
with st.sidebar:
    st.subheader("Display & Summary Options")
    WEEKEND_WEIGHT = st.number_input("Weekend weight (summary only)", value=1.5, step=0.1, min_value=0.0)
    HOLIDAY_WEIGHT = st.number_input("Holiday weight (summary only)", value=2.0, step=0.1, min_value=0.0)
    default_view = st.selectbox("Calendar default view", ["dayGridMonth", "timeGridWeek", "timeGridDay"], index=0)
    show_week_numbers = st.checkbox("Show week numbers", value=False)
    if st.button("Clear schedule"):
        st.session_state.pop("schedule_df", None)
        st.session_state.pop("schedule_msg", None)
        st.rerun()

with st.expander("CSV format help", expanded=False):
    st.markdown("""
    **doctors.csv** → `id` (int), `name` (str), `fte` (float)  
    **shifts.csv** → `id` (int), `start` (YYYY-MM-DD HH:MM), `end` (YYYY-MM-DD HH:MM), `kind` (str), `is_weekend` (bool), `is_holiday` (bool)  
    **vacations.csv** (optional) → `doctor_id` (int), `start`, `end` (date or datetime)  
    Save as **CSV UTF-8** from Excel/Numbers to avoid encoding errors.
    """)

# ---------- Manual Doctors Editor ----------
st.subheader("Create a doctors list manually (optional)")
if "doctors_df_manual" not in st.session_state:
    st.session_state["doctors_df_manual"] = pd.DataFrame(
        {"id": pd.Series(dtype="int"),
         "name": pd.Series(dtype="str"),
         "fte": pd.Series(dtype="float")}
    )

edited_df = st.data_editor(
    st.session_state["doctors_df_manual"],
    num_rows="dynamic",
    use_container_width=True,
    key="doctor_editor",
    column_config={
        "id": st.column_config.NumberColumn("id", help="Unique integer ID"),
        "name": st.column_config.TextColumn("name", help="Doctor name"),
        "fte": st.column_config.NumberColumn("fte", min_value=0.1, max_value=1.5, step=0.1, help="Full-time equivalent")
    }
)
st.session_state["doctors_df_manual"] = edited_df

c_dl1, c_dl2 = st.columns(2)
with c_dl1:
    if st.button("Auto-fill IDs & FTE = 1.0 for blanks"):
        df = st.session_state["doctors_df_manual"].copy()
        # Fill name blanks first (drop truly empty rows)
        df = df[df["name"].astype(str).str.strip() != ""]
        # Assign IDs if missing or duplicated
        if "id" not in df or df["id"].isna().any() or df["id"].duplicated().any():
            df = df.reset_index(drop=True)
            df["id"] = range(1, len(df) + 1)
        # Default FTE 1.0 if missing
        if "fte" not in df:
            df["fte"] = 1.0
        df["fte"] = df["fte"].fillna(1.0)
        st.session_state["doctors_df_manual"] = df
        st.success("IDs and FTE filled.")

with c_dl2:
    csv_bytes = st.session_state["doctors_df_manual"].to_csv(index=False).encode("utf-8")
    st.download_button("Download doctors.csv", data=csv_bytes, file_name="doctors.csv", mime="text/csv", use_container_width=True)

# ---------- Helpers ----------
def parse_bool(x):
    if isinstance(x, bool): return x
    s = str(x).strip().lower()
    return s in ("1","true","t","yes","y")

def overlaps(a_start, a_end, b_start, b_end):
    return not (a_end <= b_start or a_start >= b_end)

def fallback_round_robin(doctors_df, shifts_df, vacations_df):
    """Simple round-robin that skips doctors on PTO for that shift."""
    d_ids = doctors_df["id"].tolist()
    if not d_ids:
        return None, "No doctors found."
    name_by_id = dict(zip(doctors_df["id"], doctors_df["name"]))

    vac_map = {}
    for _, v in vacations_df.iterrows():
        vac_map.setdefault(int(v["doctor_id"]), []).append((v["start"], v["end"]))

    rows, ix = [], 0
    for _, sh in shifts_df.sort_values(["start","id"]).iterrows():
        assigned = False
        for _ in range(len(d_ids)):
            d = d_ids[ix % len(d_ids)]
            ix += 1
            # block if PTO overlaps
            blocked = any(overlaps(sh["start"], sh["end"], vs, ve) for (vs, ve) in vac_map.get(int(d), []))
            if blocked:
                continue
            rows.append({
                "shift_id": int(sh["id"]),
                "start": sh["start"],
                "end": sh["end"],
                "kind": sh.get("kind", "A"),
                "is_weekend": bool(sh["is_weekend"]),
                "is_holiday": bool(sh["is_holiday"]),
                "doctor_id": int(d),
                "doctor": name_by_id.get(d, f"Doctor {d}"),
            })
            assigned = True
            break
        if not assigned:
            return None, f"Could not place shift {sh['id']} ({sh['start']}→{sh['end']}) due to overlapping PTO for all doctors."
    return pd.DataFrame(rows).sort_values(["start","shift_id"]).reset_index(drop=True), None

def add_weights(df, wk_wt, hol_wt):
    def wrow(r):
        w = 1.0
        if r["is_weekend"]: w *= wk_wt
        if r["is_holiday"]: w *= hol_wt
        return w
    out = df.copy()
    out["weight"] = out.apply(wrow, axis=1)
    return out

# ---------- Input form (prevents intermediate reruns) ----------
st.markdown("---")
st.subheader("Generate schedule")

with st.form("inputs_form", clear_on_submit=False):
    use_manual_doctors = st.checkbox("Use the manual doctor list above (ignore doctors.csv upload)", value=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        f_doctors = st.file_uploader("Upload doctors.csv", type=["csv"], key="doctors_up", disabled=use_manual_doctors)
    with c2:
        f_shifts = st.file_uploader("Upload shifts.csv", type=["csv"], key="shifts_up")
    with c3:
        f_vac = st.file_uploader("Upload vacations.csv (optional)", type=["csv"], key="vac_up")
    submitted = st.form_submit_button("Generate Schedule", use_container_width=True)

if submitted:
    try:
        # Doctors source: manual or file
        if use_manual_doctors:
            doctors = st.session_state["doctors_df_manual"].copy()
            doctors = doctors[doctors["name"].astype(str).str.strip() != ""]
            # Validate/fill
            if doctors.empty:
                st.session_state["schedule_df"] = None
                st.session_state["schedule_msg"] = "Enter at least one doctor in the manual table."
            else:
                # ensure id and fte
                if "id" not in doctors.columns or doctors["id"].isna().any() or doctors["id"].duplicated().any():
                    doctors = doctors.reset_index(drop=True)
                    doctors["id"] = range(1, len(doctors) + 1)
                if "fte" not in doctors.columns:
                    doctors["fte"] = 1.0
                doctors["id"] = doctors["id"].astype(int)
                doctors["fte"] = doctors["fte"].astype(float)
        else:
            if not f_doctors:
                st.session_state["schedule_df"] = None
                st.session_state["schedule_msg"] = "Please upload doctors.csv or check 'Use the manual doctor list'."
            else:
                doctors = pd.read_csv(f_doctors)
                doctors["id"] = doctors["id"].astype(int)
                if "fte" in doctors.columns: doctors["fte"] = doctors["fte"].astype(float)

        # Shifts & vacations
        if not f_shifts:
            st.session_state["schedule_df"] = None
            st.session_state["schedule_msg"] = "Please upload shifts.csv."
        else:
            shifts = pd.read_csv(f_shifts)
            shifts["id"] = shifts["id"].astype(int)
            shifts["start"] = pd.to_datetime(shifts["start"])
            shifts["end"] = pd.to_datetime(shifts["end"])
            shifts["is_weekend"] = shifts["is_weekend"].apply(parse_bool)
            shifts["is_holiday"] = shifts["is_holiday"].apply(parse_bool)
            vacations = pd.read_csv(f_vac) if f_vac else pd.DataFrame(columns=["doctor_id","start","end"])
            if not vacations.empty:
                vacations["doctor_id"] = vacations["doctor_id"].astype(int)
                vacations["start"] = pd.to_datetime(vacations["start"])
                vacations["end"] = pd.to_datetime(vacations["end"])

            # Solve
            schedule, err = fallback_round_robin(doctors, shifts, vacations)
            if err:
                st.session_state["schedule_df"] = None
                st.session_state["schedule_msg"] = err
            else:
                st.session_state["schedule_df"] = schedule
                st.session_state["schedule_msg"] = "Schedule generated (cached)."

    except Exception as e:
        st.session_state["schedule_df"] = None
        st.session_state["schedule_msg"] = f"Error: {e}"

# ---------- Render cached result ----------
schedule = st.session_state.get("schedule_df")
msg = st.session_state.get("schedule_msg")

if msg:
    if schedule is None:
        st.error(msg)
    else:
        st.success(msg)

if schedule is not None:
    tab_table, tab_cal, tab_summary = st.tabs(["📋 Table", "🗓️ Calendar", "📊 Summary"])

    with tab_table:
        st.dataframe(schedule, use_container_width=True)
        st.download_button(
            "Download schedule.csv",
            data=schedule.to_csv(index=False).encode("utf-8"),
            file_name="schedule.csv",
            mime="text/csv"
        )

    with tab_cal:
        try:
            from streamlit_calendar import calendar as st_calendar
        except Exception:
            st.error("Calendar component not installed. Add `streamlit-calendar==1.0.0` to requirements.txt and redeploy.")
        else:
            events = []
            for _, r in schedule.iterrows():
                title = f"{r['doctor']} ({str(r.get('kind','A')).upper()})"
                start_iso = pd.to_datetime(r["start"]).isoformat()
                end_iso = (pd.to_datetime(r["end"]) + pd.Timedelta(minutes=1)).isoformat()
                base = "#2563eb"  # weekday
                if bool(r["is_weekend"]): base = "#10b981"  # weekend
                if bool(r["is_holiday"]): base = "#ef4444"  # holiday
                if str(r.get("kind","A")).upper() == "B" and not r["is_holiday"] and not r["is_weekend"]:
                    base = "#93c5fd"  # lighter for B on weekdays
                events.append({
                    "title": title, "start": start_iso, "end": end_iso,
                    "allDay": True, "backgroundColor": base, "borderColor": base
                })
            options = {
                "initialView": default_view,
                "height": 750,
                "firstDay": 0,
                "headerToolbar": {"left":"prev,next today","center":"title","right":"dayGridMonth,timeGridWeek,timeGridDay"},
                "displayEventTime": False,
                "weekNumbers": show_week_numbers,
            }
            st.caption("Tip: Use the toolbar to switch months or change views.")
            st_calendar(events=events, options=options)

    with tab_summary:
        weighted = add_weights(schedule, WEEKEND_WEIGHT, HOLIDAY_WEIGHT)
        summary = weighted.groupby("doctor").agg(
            shifts=("shift_id","count"),
            weighted_calls=("weight","sum"),
            weekends=("is_weekend","sum"),
            holidays=("is_holiday","sum"),
        ).reset_index()
        st.dataframe(summary, use_container_width=True)

else:
    st.info("Upload your CSVs or build your doctors list above, then click **Generate Schedule**.")


