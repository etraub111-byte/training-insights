"""Download .fit files for activities (resumable, threaded). Files go to data/fit/<id>.fit.
Usage: python3 fit_download.py [--max-seconds N] [--workers N]"""
import sys, os, io, zipfile, sqlite3, time, json, threading, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import garmin_api
from garmin_api import Client, ROOT
args = sys.argv[1:]
arg = lambda n, d: int(args[args.index(n)+1]) if n in args else d
MAXS, WORKERS = arg("--max-seconds", 150), arg("--workers", 4)
OUT = os.path.join(ROOT, "data", "fit"); os.makedirs(OUT, exist_ok=True)
db = sqlite3.connect("file:" + os.path.join(ROOT, "data", "garmin.sqlite") + "?nolock=1", uri=True, check_same_thread=False)
db.execute("PRAGMA journal_mode=MEMORY"); db.execute("PRAGMA synchronous=OFF")
db.execute("CREATE TABLE IF NOT EXISTS fit_status(id INTEGER PRIMARY KEY, status TEXT, bytes INTEGER, at TEXT)")
SKIP_TYPES = {"strength_training", "stop_watch", "other", "hiit"}
rows = db.execute("""SELECT a.id FROM activities a LEFT JOIN fit_status f ON f.id=a.id
  WHERE f.id IS NULL AND a.type NOT IN (%s) AND json_extract(a.raw,'$.duration')>=300
  ORDER BY a.start_local DESC""" % ",".join("?"*len(SKIP_TYPES)), tuple(SKIP_TYPES)).fetchall()
todo = [r[0] for r in rows]; print("to download:", len(todo), flush=True)
c = Client(); c._token(); lock = threading.Lock(); t_end = time.time() + MAXS; done = [0, 0]

def fetch(aid):
    if time.time() > t_end: return
    delay = 2
    for attempt in range(5):
        req = urllib.request.Request(garmin_api.BASE + f"/download-service/files/activity/{aid}", headers={"Authorization": "Bearer " + c.token})
        try:
            with urllib.request.urlopen(req, timeout=60) as f: b = f.read()
            if b[:2] == b"PK":
                z = zipfile.ZipFile(io.BytesIO(b)); name = [n for n in z.namelist() if n.lower().endswith(".fit")][0]
                data = z.read(name)
            else: data = b
            open(os.path.join(OUT, f"{aid}.fit"), "wb").write(data)
            with lock:
                db.execute("INSERT OR REPLACE INTO fit_status VALUES(?,?,?,datetime('now'))", (aid, "ok", len(data))); db.commit(); done[0] += 1
            return
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504): time.sleep(delay); delay *= 2; continue
            with lock:
                db.execute("INSERT OR REPLACE INTO fit_status VALUES(?,?,?,datetime('now'))", (aid, f"http_{e.code}", 0)); db.commit(); done[1] += 1
            return
        except Exception as e:
            if attempt == 4: print('error', aid, repr(e)[:120], flush=True)
            time.sleep(delay); delay *= 2
    # leave unrecorded so a later run retries
with ThreadPoolExecutor(WORKERS) as ex: list(ex.map(fetch, todo))
left = db.execute("SELECT count(*) FROM activities a LEFT JOIN fit_status f ON f.id=a.id WHERE f.id IS NULL AND a.type NOT IN (%s) AND json_extract(a.raw,'$.duration')>=300" % ",".join("?"*len(SKIP_TYPES)), tuple(SKIP_TYPES)).fetchone()[0]
print(f"ok this run: {done[0]}, failed: {done[1]}, remaining: {left}", flush=True)
