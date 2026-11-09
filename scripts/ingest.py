"""Resumable full-history ingest of Garmin Connect Personal API data into SQLite (data/garmin.sqlite).
Raw JSON is stored per record; metrics are derived later from it. Re-run any time to refresh.
Usage: python3 ingest.py [--full]   (--full ignores the 'already complete' shortcut for recent windows)
"""
import sys, os, json, sqlite3, time, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from garmin_api import Client, ROOT

DB = os.path.join(ROOT, "data", "garmin.sqlite")
os.makedirs(os.path.dirname(DB), exist_ok=True)
# nolock + in-memory journal: SQLite file locking fails on some mounted/synced folders. Run only one writer at a time.
db = sqlite3.connect("file:" + DB + "?nolock=1", uri=True)
db.execute("PRAGMA journal_mode=MEMORY"); db.execute("PRAGMA synchronous=OFF")
db.executescript("""
CREATE TABLE IF NOT EXISTS activities(id INTEGER PRIMARY KEY, start_local TEXT, type TEXT, raw TEXT);
CREATE TABLE IF NOT EXISTS daily(endpoint TEXT, date TEXT, raw TEXT, PRIMARY KEY(endpoint,date));
CREATE TABLE IF NOT EXISTS singles(name TEXT PRIMARY KEY, fetched TEXT, raw TEXT);
CREATE TABLE IF NOT EXISTS chunks(key TEXT PRIMARY KEY, n INTEGER, fetched TEXT);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
""")
c = Client()
TODAY = dt.date.today()
log = lambda *a: print(time.strftime("%H:%M:%S"), *a, flush=True)
def meta_get(k, d=None):
    r = db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone(); return r[0] if r else d
def meta_set(k, v):
    db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (k, str(v))); db.commit()

# ---- activities (newest first, 100/page; limit>=500 errors server-side)
def ingest_activities():
    complete = meta_get("activities_complete") == "1"
    start = 0 if complete else int(meta_get("activities_next", 0))
    new_total = 0
    while True:
        s, b = c.get("/activitylist-service/activities/search/activities", {"start": start, "limit": 100})
        if s != 200: raise SystemExit(f"activities failed at {start}: {s} {str(b)[:200]}")
        if not b: break
        ids = [a["activityId"] for a in b]
        known = {r[0] for r in db.execute("SELECT id FROM activities WHERE id IN (%s)" % ",".join("?"*len(ids)), ids)}
        for a in b:
            db.execute("INSERT OR REPLACE INTO activities VALUES(?,?,?,?)",
                       (a["activityId"], a.get("startTimeLocal"), (a.get("activityType") or {}).get("typeKey"), json.dumps(a)))
        new_total += len(ids) - len(known)
        start += 100
        if not complete: meta_set("activities_next", start)
        db.commit(); log(f"activities page start={start-100} got={len(b)} new={len(ids)-len(known)}")
        if complete and len(known) == len(ids): break   # refresh: reached already-stored history
        if len(b) < 100: break
    meta_set("activities_complete", 1); log("activities done, new:", new_total)

# ---- date-windowed endpoints
def windows(a, b, w):
    cur = a
    while cur <= b:
        end = min(cur + dt.timedelta(days=w-1), b); yield cur, end; cur = end + dt.timedelta(days=1)

def pull(name, a, b, w, call, extract, datekey):
    n_calls = 0
    for ws, we in windows(a, b, w):
        key = f"{name}:{ws}:{we}"
        done = db.execute("SELECT 1 FROM chunks WHERE key=?", (key,)).fetchone()
        if done and we < TODAY - dt.timedelta(days=7) and "--full" not in sys.argv: continue
        s, body = call(ws.isoformat(), we.isoformat())
        if s == 204: body = None
        elif s != 200: log(f"  {name} {ws}..{we} -> HTTP {s} {str(body)[:120]} (skipped, will retry next run)"); continue
        rows = (extract(body) if body is not None else None) or []
        for r in rows:
            d = r.get(datekey)
            if d: db.execute("INSERT OR REPLACE INTO daily VALUES(?,?,?)", (name, str(d)[:10], json.dumps(r)))
        db.execute("INSERT OR REPLACE INTO chunks VALUES(?,?,?)", (key, len(rows), dt.datetime.now().isoformat()))
        db.commit(); n_calls += 1
        if n_calls % 10 == 0: log(f"  {name}: through {we}")
        time.sleep(0.2)
    log(f"{name} done")

G = c.get
ENDPOINTS = [  # name, window days, call(a,b), extract(body), date key
  ("daily",  90, lambda a,b: G("/usersummary-service/v2/dailysummaries", {"startDate":a,"endDate":b}), lambda x: x["data"], "calendarDate"),
  ("sleep",  28, lambda a,b: G("/sleep-service/sleep/dailySleepSummariesByDate", {"startDate":a,"endDate":b}), lambda x: x, "calendarDate"),
  ("hrv",    90, lambda a,b: G(f"/hrv-service/hrv/daily/{a}/{b}"), lambda x: x["hrvSummaries"], "calendarDate"),
  ("stress", 28, lambda a,b: G(f"/usersummary-service/stats/stress/daily/{a}/{b}"), lambda x: x, "calendarDate"),
  ("steps",  28, lambda a,b: G(f"/usersummary-service/stats/steps/daily/{a}/{b}"), lambda x: x, "calendarDate"),
  ("bodybattery", 28, lambda a,b: G("/wellness-service/wellness/bodyBattery/reports/daily", {"startDate":a,"endDate":b}), lambda x: x, "date"),
  ("weight", 90, lambda a,b: G(f"/weight-service/weight/range/{a}/{b}"), lambda x: x["dailyWeightSummaries"], "summaryDate"),
]

def singles():
    for name, path in (("hr_zones", "/biometric-service/heartRateZones/v2"),
                       ("fitness_age", f"/fitnessage-service/fitnessage/v2/{TODAY}"),
                       ("settings", "/userprofile-service/userprofile/settings")):
        s, b = c.get(path)
        if s == 200: db.execute("INSERT OR REPLACE INTO singles VALUES(?,?,?)", (name, dt.datetime.now().isoformat(), json.dumps(b)))
        else: log("single", name, s)
    db.commit()

if __name__ == "__main__":
    log("token + activities"); ingest_activities(); singles()
    first_act = db.execute("SELECT MIN(substr(start_local,1,10)) FROM activities").fetchone()[0]
    a0 = dt.date.fromisoformat(first_act) - dt.timedelta(days=30) if first_act else dt.date(2019,1,1)
    log("earliest activity", first_act)
    name, w, call, ex, dk = ENDPOINTS[0]
    pull(name, a0, TODAY, w, call, ex, dk)
    fd = db.execute("SELECT MIN(date) FROM daily WHERE endpoint='daily'").fetchone()[0]
    a1 = max(a0, dt.date.fromisoformat(fd) - dt.timedelta(days=28)) if fd else a0
    log("earliest daily summary", fd, "-> other endpoints from", a1)
    for name, w, call, ex, dk in ENDPOINTS[1:]:
        pull(name, a1, TODAY, w, call, ex, dk)
    meta_set("last_ingest", dt.datetime.now().isoformat()); log("INGEST COMPLETE calls:", c.calls)
