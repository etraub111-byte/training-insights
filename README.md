# Garmin training insights

A personal dashboard built from your whole Garmin Connect history, using only the Garmin Connect Personal API.

## Refresh in one command

    python3 scripts/refresh.py

Then open `dashboard.html`. The first run takes a few minutes. Later runs only fetch what is new.

## One-time setup

1. Put your key in `.env` in this folder: `GARMIN_API_KEY=...` (already done). The file is excluded by `.gitignore`.
2. Install the libraries: `pip install fitparse numpy pandas`
3. Python 3.9 or newer.

Your key expires on Nov 7, 2027. Garmin emails a reminder a week before. To replace it, delete the key at connect.garmin.com/app/settings/personalApiToken, create a new one, and paste it into `.env`.

## What is in this folder

| Path | Purpose |
|---|---|
| `dashboard.html` | The dashboard. One file, works offline apart from the web font. |
| `data/garmin.sqlite` | Everything pulled from Garmin, stored as raw JSON per record. |
| `data/fit/` | One `.fit` file per activity (second by second heart rate, speed, power). |
| `data/dashboard_data.json` | Computed metrics that feed the dashboard. |
| `scripts/ingest.py` | Pulls activities, daily summaries, sleep, HRV, stress, steps, Body Battery, weight, HR zones. Resumable. |
| `scripts/fit_download.py` | Downloads new activity files. Resumable. |
| `scripts/parse_fit.py` | Extracts per-activity features (TRIMP, zones, decoupling, best efforts, power). No GPS is read. |
| `scripts/analyze.py` | Computes every metric and insight. |
| `scripts/build_dashboard.py` | Inlines the data into `dashboard.html`. |
| `scripts/garmin_api.py` | Small API client. Never prints the key. |

## How the API works

- Your key is exchanged for a 24 hour access token at `POST /personalapitoken-service/personal-api/personal-api-key/token`. There are no refresh tokens, so every run just asks for a new one.
- Activity lists return at most 100 per page (500 or more errors).
- Date-range limits found by testing: daily summaries 90 days, HRV 90, weight 90, sleep 28, stress 28, steps 28, Body Battery 28. The scripts chunk to those sizes.
- History goes back to your first activity (Oct 2019). Heart rate, sleep and Body Battery start then. HRV starts Sep 2022.
- Not available from this API: VO2max, gear and gear mileage, training status. The dashboard says so rather than guessing.

## Metrics and formulas

The dashboard's Method tab lists every formula and the checks against Garmin's own numbers. In short:

- Load is Banister TRIMP from per-second heart rate, with resting and max HR from your Garmin settings (47 and 197), male coefficients 0.64 and 1.92.
- Fitness (CTL) is a 42 day exponential average, fatigue (ATL) a 7 day one, form (TSB) is yesterday's CTL minus ATL.
- Performance index is Daniels VDOT from your best efforts of 1.9 miles or longer and 20 minute or longer windows.
- Best efforts use timer time with paused time removed, matching Garmin's splits.

## Things worth knowing

- `dashboard.html` contains your health data (heart rate, sleep, HRV). It has no GPS and no activity names. Treat it as private.
- SQLite is opened without file locking so it works on synced or mounted folders. Do not run two refreshes at the same time.
- Activities longer than 24 hours (three forgotten timers) are excluded from totals.


## Units

The dashboard shows miles, feet and minutes per mile only. The stored data stays metric internally (dist_km, elev in meters) and is converted when drawn, so no refresh or re-ingest is needed to change how it looks. Update everything with `python3 scripts/refresh.py`.

## Kyoto Marathon tab
Calendar, weekly mileage, run types, plan vs actual, coaching notes and race-day plan for the Feb 21, 2027 race (goal 2:54:30). Change the goal on the tab and everything recalculates.

## Live phone app (auto-updating)
A GitHub Actions job (`.github/workflows/refresh.yml`) runs `scripts/refresh.py` every 10 minutes using your Garmin key stored as a GitHub secret, then publishes the dashboard, encrypted with your page password, to GitHub Pages as an installable app.
- One-time setup: `brew install gh && gh auth login`, then `bash scripts/deploy_setup.sh`.
- iPhone: open the printed link in Safari, Share, Add to Home Screen.
- Refresh now: GitHub app or website, Actions, Refresh dashboard, Run workflow.
- Data between runs lives in the Actions cache, not in the repo. The repo is public but contains no data or keys.
