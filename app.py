# app.py — Luminosa Call Scheduler (Fallback, stable calendar)
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
st.caption("Upload doctors, shifts, and vacations CSVs, then press Generate. Output is saved in session so the calendar won’t disappear.")

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
with st.form("inputs_form", clear_on_submit=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        f_doctors = st.file_uploader("Upload doctors.csv", type=["csv"], key="doctors_up")
    with c2:
        f_shifts = st.file_uploader("Upload shifts.csv", type=["csv"], key="shifts_up")
    with c3:
        f_vac = st.file_uploader("Upload vacations.csv (optional)", type=["csv"], key="vac_up")
    submitted = st.form_submit_button("Generate Schedule", use_container_width=True)

if submitted:
    try:
        if not f_doctors or not f_shifts:
            st.session_state["schedule_df"] = None
            st.session_state["schedule_msg"] = "Please upload doctors.csv and shifts.csv."
        else:
            doctors = pd.read_csv(f_doctors)
            shifts = pd.read_csv(f_shifts)
            vacations = pd.read_csv(f_vac) if f_vac else pd.DataFrame(columns=["doctor_id","start","end"])
            # normalize
            doctors["id"] = doctors["id"].astype(int)
            if "fte" in doctors.columns: doctors["fte"] = doctors["fte"].astype(float)
            shifts["id"] = shifts["id"].astype(int)
            shifts["start"] = pd.to_datetime(shifts["start"])
            shifts["end"] = pd.to_datetime(shifts["end"])
            shifts["is_weekend"] = shifts["is_weekend"].apply(parse_bool)
            shifts["is_holiday"] = shifts["is_holiday"].apply(parse_bool)
            if not vacations.empty:
                vacations["doctor_id"] = vacations["doctor_id"].astype(int)
                vacations["start"] = pd.to_datetime(vacations["start"])
                vacations["end"] = pd.to_datetime(vacations["end"])

            schedule, err = fallback_round_robin(doctors, shifts, vacations)
            if err:
                st.session_state["schedule_df"] = None
                st.session_state["schedule_msg"] = err
            else:
                st.session_state["schedule_df"] = schedule
                st.session_state["schedule_msg"] = "Schedule generated (cached)."
    except Exception as e:
        st.session_state["schedule_df"] = None
        st.session_state["schedule_msg"] = f"Error reading CSVs: {e}"

# ---------- Render cached result (persists across reruns) ----------
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
    st.info("Upload your CSVs in the form above and click **Generate Schedule**.")

