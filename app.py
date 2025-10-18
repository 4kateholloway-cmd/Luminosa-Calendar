# app.py — Luminosa Call Scheduler (Built-in doctors, styled UI, stable calendar)
# Required packages: see requirements.txt below

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# ---------- Page & Basic Styling ----------
st.set_page_config(page_title="Luminosa Laborist Call Scheduler", layout="wide")

# Aesthetic polish (soft cards, rounded buttons/tabs, subtle shadows, legend pills)
st.markdown("""
<style>
/* Layout padding */
.block-container {padding-top: 1.2rem; padding-bottom: 2.5rem;}

/* Dataframes = rounded cards */
[data-testid="stDataFrame"] {border-radius:14px;overflow:hidden;border:1px solid #eef2ff}

/* Buttons */
.stButton>button, .stDownloadButton>button {
  border-radius:12px !important; padding:10px 14px !important;
  border:1px solid #dbeafe !important; transition: box-shadow .2s ease;
}
.stButton>button:hover, .stDownloadButton>button:hover {box-shadow:0 4px 16px rgba(37,99,235,.15)}

/* Tabs */
.stTabs [data-baseweb="tab"] {font-weight:600}
.stTabs [data-baseweb="tab"] > div {padding:10px 14px}

/* Sidebar background */
section[data-testid="stSidebar"] {background: linear-gradient(180deg,#fff 0%,#f7f9ff 100%);}

/* Legend pills */
.legend-pill {
  display:inline-block;padding:6px 10px;border-radius:999px;
  font-size:12px;margin-right:8px;border:1px solid #e5e7eb;
}
</style>
""", unsafe_allow_html=True)

# ---------- Header / Hero ----------
col_logo, col_title = st.columns([1,7], vertical_alignment="center")
with col_logo:
    st.markdown("🩺")
with col_title:
    st.markdown(
        "<div style='line-height:1.2; font-size:32px; font-weight:800'>Luminosa Laborist Call Scheduler</div>"
        "<div style='color:#4b5563; font-size:15px; margin-top:4px'>Fast, fair call assignments with a clean calendar view</div>",
        unsafe_allow_html=True
    )
st.markdown(
    "<div class='legend-pill' style='background:#e8f0ff'>Weekday</div>"
    "<div class='legend-pill' style='background:#e8f6f1'>Weekend</div>"
    "<div class='legend-pill' style='background:#feecec'>Holiday</div>",
    unsafe_allow_html=True
)

# ---------- Built-in Laborist doctors (permanent) ----------
DOCTORS_DEFAULT = [
    {"id": 1,  "name": "Holloway",        "fte": 1.0},
    {"id": 2,  "name": "Barnard",         "fte": 1.0},
    {"id": 3,  "name": "Shields",         "fte": 1.0},
    {"id": 4,  "name": "Mal Thompson",    "fte": 1.0},
    {"id": 5,  "name": "Yaghi",           "fte": 1.0},
    {"id": 6,  "name": "Simpson",         "fte": 1.0},
    {"id": 7,  "name": "Arya",            "fte": 1.0},
    {"id": 8,  "name": "Shaefer",         "fte": 1.0},
    {"id": 9,  "name": "Ramos-Gonzales",  "fte": 1.0},
    {"id": 10, "name": "Troy",            "fte": 1.0},
    {"id": 11, "name": "Carroll",         "fte": 1.0},
    {"id": 12, "name": "Landez",          "fte": 1.0},
    {"id": 13, "name": "Zamora",          "fte": 1.0},
    {"id": 14, "name": "Dutta",           "fte": 1.0},
    {"id": 15, "name": "Chavarria",       "fte": 1.0},
    {"id": 16, "name": "Garza",           "fte": 1.0},
    {"id": 17, "name": "Do",              "fte": 1.0},
    {"id": 18, "name": "Truong",          "fte": 1.0},
    {"id": 19, "name": "Galindo",         "fte": 1.0},
]
DOCTORS_DF = pd.DataFrame(DOCTORS_DEFAULT, columns=["id","name","fte"]).astype({"id": int, "fte": float})

# ---------- Sidebar options ----------
with st.sidebar:
    st.subheader("Display & Summary Options")
    WEEKEND_WEIGHT = st.number_input("Weekend weight (summary only)", value=1.5, step=0.1, min_value=0.0)
    HOLIDAY_WEIGHT = st.number_input("Holiday weight (summary only)", value=2.0, step=0.1, min_value=0.0)
    default_view = st.selectbox("Calendar default view", ["dayGridMonth", "timeGridWeek", "timeGridDay"], index=0)
    show_week_numbers = st.checkbox("Show week numbers", value=False)
    st.divider()
    st.subheader("Built-in Doctors")
    st.dataframe(DOCTORS_DF, use_container_width=True, hide_index=True)
    st.download_button(
        "Download doctors.csv",
        data=DOCTORS_DF.to_csv(index=False).encode("utf-8"),
        file_name="doctors.csv",
        mime="text/csv",
        use_container_width=True
    )
    if st.button("Clear generated schedule"):
        st.session_state.pop("schedule_df", None)
        st.session_state.pop("schedule_msg", None)
        st.toast("Cleared cached schedule", icon="🧹")
        st.rerun()

with st.expander("CSV format help", expanded=False):
    st.markdown("""
**shifts.csv** → `id` (int), `start` (YYYY-MM-DD HH:MM), `end` (YYYY-MM-DD HH:MM), `kind` (str), `is_weekend` (bool), `is_holiday` (bool)  
**vacations.csv** (optional) → `doctor_id` (int), `start`, `end` (date or datetime)  
Save as **CSV UTF-8** from Excel/Numbers to avoid encoding errors.
""")

# ---------- Helpers ----------
def parse_bool(x):
    if isinstance(x, bool): return x
    s = str(x).strip().lower()
    return s in ("1","true","t","yes","y")

def overlaps(a_start, a_end, b_start, b_end):
    return not (a_end <= b_start or a_start >= b_end)

def fallback_round_robin(doctors_df, shifts_df, vacations_df):
    """Simple round-robin that skips doctors on PTO for a shift."""
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
        # rotate across doctors until one is not on PTO
        for _ in range(len(d_ids)):
            d = d_ids[ix % len(d_ids)]
            ix += 1
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

# ---------- Generate schedule (form prevents mid-upload reruns) ----------
st.markdown("---")
st.subheader("Generate schedule")

with st.form("inputs_form", clear_on_submit=False):
    c2, c3 = st.columns(2)
    with c2:
        f_shifts = st.file_uploader("Upload shifts.csv", type=["csv"], key="shifts_up")
    with c3:
        f_vac = st.file_uploader("Upload vacations.csv (optional)", type=["csv"], key="vac_up")
    submitted = st.form_submit_button("Generate Schedule", use_container_width=True)

if submitted:
    try:
        doctors = DOCTORS_DF.copy()

        # Sanitize doctors: ensure non-empty names, sequential IDs, float FTE
        doctors = doctors[doctors["name"].astype(str).str.strip() != ""].reset_index(drop=True)
        doctors["id"] = range(1, len(doctors) + 1)
        if "fte" not in doctors.columns: doctors["fte"] = 1.0
        doctors["fte"] = doctors["fte"].astype(float)

        # Diagnostic
        st.info(f"Loaded {len(doctors)} doctors: " + ", ".join(doctors['name'].astype(str).tolist()))

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

            schedule, err = fallback_round_robin(doctors, shifts, vacations)
            if err:
                st.session_state["schedule_df"] = None
                st.session_state["schedule_msg"] = err
            else:
                st.session_state["schedule_df"] = schedule
                st.session_state["schedule_msg"] = "Schedule generated (cached)."
                st.toast("Schedule generated and cached ✅", icon="✅")

    except Exception as e:
        st.session_state["schedule_df"] = None
        st.session_state["schedule_msg"] = f"Error: {e}"

# ---------- Render cached result (persists across reruns) ----------
schedule = st.session_state.get("schedule_df")
msg = st.session_state.get("schedule_msg")

if msg:
    if schedule is None:
        st.error(msg)
    else:
        st.success(msg)

if schedule is not None:
    # Small KPIs
    total_shifts = len(schedule)
    weekends = int(schedule["is_weekend"].sum())
    holidays = int(schedule["is_holiday"].sum())
    unique_docs = schedule["doctor"].nunique()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total shifts", f"{total_shifts}")
    k2.metric("Weekend shifts", f"{weekends}")
    k3.metric("Holiday shifts", f"{holidays}")
    k4.metric("Doctors scheduled", f"{unique_docs}")

    # Filters
    fc1, fc2, fc3 = st.columns([2,2,1])
    with fc1:
        doc_list = ["All doctors"] + sorted(schedule["doctor"].unique().tolist())
        pick_doc = st.selectbox("Filter by doctor", doc_list, index=0)
    with fc2:
        kind_list = ["All kinds"] + sorted(schedule["kind"].astype(str).str.upper().unique().tolist())
        pick_kind = st.selectbox("Filter by shift kind", kind_list, index=0)
    with fc3:
        st.write("")
        clear = st.button("Clear filters")

    filt = schedule.copy()
    if pick_doc != "All doctors":
        filt = filt[filt["doctor"] == pick_doc]
    if pick_kind != "All kinds":
        filt = filt[filt["kind"].astype(str).str.upper() == pick_kind]
    if clear:
        st.experimental_rerun()

    # Tabs
    tab_table, tab_cal, tab_summary = st.tabs(["📋 Table", "🗓️ Calendar", "📊 Summary"])

    # Table tab
    with tab_table:
        st.dataframe(filt, use_container_width=True)
        st.download_button(
            "Download filtered schedule.csv",
            data=filt.to_csv(index=False).encode("utf-8"),
            file_name="schedule_filtered.csv",
            mime="text/csv"
        )

    # Calendar tab
    with tab_cal:
        try:
            from streamlit_calendar import calendar as st_calendar
        except Exception:
            st.error("Calendar component not installed. Add `streamlit-calendar==1.0.0` to requirements.txt and redeploy.")
        else:
            events = []
            for _, r in filt.iterrows():
                title = f"{r['doctor']} ({str(r.get('kind','A')).upper()})"
                start_iso = pd.to_datetime(r["start"]).isoformat()
                # FullCalendar's end is exclusive: +1 minute avoids truncation in month view
                end_iso = (pd.to_datetime(r["end"]) + pd.Timedelta(minutes=1)).isoformat()
                base = "#2563eb"  # weekday blue
                if bool(r["is_weekend"]): base = "#10b981"  # weekend green
                if bool(r["is_holiday"]): base = "#ef4444"  # holiday red
                if str(r.get("kind","A")).upper() == "B" and not r["is_holiday"] and not r["is_weekend"]:
                    base = "#93c5fd"  # lighter weekday for B
                events.append({
                    "title": title,
                    "start": start_iso,
                    "end": end_iso,
                    "allDay": True,
                    "backgroundColor": base,
                    "borderColor": base
                })

            options = {
                "initialView": default_view,
                "height": 750,
                "firstDay": 0,
                "headerToolbar": {"left":"prev,next today","center":"title","right":"dayGridMonth,timeGridWeek,timeGridDay"},
                "displayEventTime": False,
                "weekNumbers": show_week_numbers,
            }
            st.caption("🔎 Tip: Click a day to switch views. Use filters above to focus on one physician.")
            st_calendar(events=events, options=options)

    # Summary tab
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
    st.info("Upload your **shifts.csv** (and optional **vacations.csv**) above, then click **Generate Schedule**.")

