
# Physician Call Scheduler — DIY Starter

This is a minimal, working starter to help you build your own on-call scheduler.

## What's inside
- `app.py` — Streamlit web app that reads CSVs, runs an OR-Tools solver, and outputs a schedule
- `requirements.txt` — Python dependencies
- `sample_doctors.csv`, `sample_shifts.csv`, `sample_vacations.csv` — example data to try

## Quick start (local)
1. Install Python 3.10+
2. Create a virtual env (optional) and install deps:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   streamlit run app.py
   ```
4. In the browser, upload the **sample CSVs** (or your own), set weights/rest hours, click **Generate Schedule**.

## CSV formats
- **doctors.csv**
  - `id` (int), `name` (str), `fte` (float)
- **shifts.csv**
  - `id` (int), `start` (YYYY-MM-DD HH:MM), `end` (YYYY-MM-DD HH:MM), `kind` (str), `is_weekend` (bool), `is_holiday` (bool)
- **vacations.csv** (optional)
  - `doctor_id` (int), `start` (YYYY-MM-DD or datetime), `end` (YYYY-MM-DD or datetime)

## Notes
- Weekend & holiday weighting and min rest are adjustable in the UI.
- The solver balances weighted call loads by FTE and avoids overlapping PTO and short rest windows.
- Extend this by adding: role eligibility, max weekends per month, lock-and-resolve, swap workflows, etc.
