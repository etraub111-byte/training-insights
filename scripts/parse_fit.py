"""Parse downloaded .fit files into per-activity features (table `features`). Resumable.
No GPS positions are read or stored. Usage: python3 parse_fit.py [--max-seconds N] [--redo]"""
import sys, os, json, sqlite3, time, math, datetime as dt
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from garmin_api import ROOT
FIT = os.path.join(ROOT, "data", "fit"); DBP = os.path.join(ROOT, "data", "garmin.sqlite")
RUN = {"running", "trail_running", "treadmill_running"}
RIDE = {"cycling", "virtual_ride", "indoor_cycling", "mountain_biking"}
HIKE = {"hiking"}
DIST_M = [1000, 1609.344, 3000, 5000, 10000, 15000, 21097.5, 42195]
DUR_S = [60, 180, 300, 600, 1200, 1800, 3600]
PDUR_S = [5, 60, 300, 600, 1200, 1800, 3600]
GAP = 15.0

def rolling_mean(x, n):
    c = np.cumsum(np.insert(x, 0, 0.0)); return (c[n:] - c[:-n]) / n

def features(args):
    aid, typ, zones = args
    try:
        from fitparse import FitFile
        ts, f = [], {k: [] for k in ("hr", "spd", "alt", "dist", "pw", "temp")}
        for m in FitFile(os.path.join(FIT, f"{aid}.fit")).get_messages("record"):
            v = m.get_values(); t = v.get("timestamp")
            if t is None: continue
            ts.append(t.replace(tzinfo=dt.timezone.utc).timestamp())
            f["hr"].append(v.get("heart_rate")); f["spd"].append(v.get("enhanced_speed", v.get("speed")))
            f["alt"].append(v.get("enhanced_altitude", v.get("altitude"))); f["dist"].append(v.get("distance"))
            f["pw"].append(v.get("power")); f["temp"].append(v.get("temperature"))
        if len(ts) < 30: return aid, {"ok": False, "why": "too few records"}
        ts = np.array(ts); order = np.argsort(ts); ts = ts[order]
        T0 = ts[0]; t = ts - T0; n = int(t[-1]) + 1
        g = np.arange(n, dtype=float)
        gap = np.zeros(n, bool)
        # A long spacing between records is a PAUSE only if the athlete did not move across it. Smart-recording
        # writes sparse samples on steady stretches, which must not be mistaken for stopped time.
        draw = np.array([np.nan if x is None else float(x) for x in f["dist"]])[order]
        okd = ~np.isnan(draw)
        draw = np.interp(t, t[okd], draw[okd]) if okd.sum() >= 2 else None
        for i in np.where(np.diff(t) > GAP)[0]:
            if draw is not None and (draw[i+1] - draw[i]) / (t[i+1] - t[i]) >= 0.7: continue
            gap[int(math.ceil(t[i])):int(t[i+1])] = True
        def series(key):
            a = np.array([np.nan if x is None else float(x) for x in f[key]])[order]; ok = ~np.isnan(a)
            if ok.sum() < 10: return None
            return np.interp(g, t[ok], a[ok])
        hr, spd, alt, dist, pw = (series(k) for k in ("hr", "spd", "alt", "dist", "pw"))
        out = {"ok": True, "t0": dt.datetime.fromtimestamp(T0, dt.timezone.utc).isoformat(), "n": n, "gap_s": int(gap.sum())}
        if dist is not None: dist = np.maximum.accumulate(dist)
        if spd is None and dist is not None:
            spd = np.gradient(dist); spd = np.clip(spd, 0, None)
        minspd = 0.5 if (typ in RUN or typ in HIKE) else 1.0
        moving = (~gap) & (spd > minspd) if spd is not None else ~gap
        out["moving_s"] = int(moving.sum())
        hrv = hr is not None
        if hrv:
            hr = np.where((hr > 30) & (hr < 230), hr, np.nan)
            out["hr_cov"] = float(np.mean(~np.isnan(hr[moving]))) if moving.any() else 0.0
            z = np.zeros(6)
            h = hr[(~gap) & ~np.isnan(hr)]
            floors = [zones[f"zone{i}Floor"] for i in range(1, 6)]
            idx = np.searchsorted(floors, h, side="right")        # 0 = below Z1, 1..5 = zones
            for k in range(6): z[k] = float(np.sum(idx == k))
            out["zone_s"] = z.tolist()
            # Banister TRIMP from per-second HR (HR reserve fraction); constants from Garmin's HR settings
            rest, mx = zones["restingHeartRateUsed"], zones["maxHeartRateUsed"]
            ok_h = (~gap) & ~np.isnan(hr)
            if ok_h.sum() >= 0.5 * max(1, (~gap).sum()):
                hrr = np.clip((hr[ok_h] - rest) / (mx - rest), 0, 1)
                tr = float(np.sum(hrr * 0.64 * np.exp(1.92 * hrr)) / 60.0)
                out["trimp"] = tr * (float((~gap).sum()) / float(ok_h.sum()))
        # decoupling / efficiency (aerobic activities with sustained HR)
        if hrv and spd is not None and typ in RUN | RIDE | HIKE:
            ix = np.where(moving & ~np.isnan(hr))[0]
            ix = ix[ix >= 600]                                  # drop first 10 min warm-up
            if len(ix) >= 1500 and out["hr_cov"] >= 0.9:
                half = len(ix) // 2; a, b = ix[:half], ix[half:]
                use_pw = pw is not None and typ in RIDE and np.nanmean(pw[ix]) > 20
                eff = (lambda s: float(np.mean(pw[s]) / np.mean(hr[s]))) if use_pw else (lambda s: float(np.mean(spd[s]) * 60 / np.mean(hr[s])))
                e1, e2 = eff(a), eff(b)
                out.update(ef1=e1, ef2=e2, ef=eff(ix), ef_basis="power/HR" if use_pw else "m/min per bpm",
                           decoupling_pct=(e1 - e2) / e1 * 100, hr1=float(np.mean(hr[a])), hr2=float(np.mean(hr[b])),
                           steady_s=int(len(ix)))
        # elevation gain per km (smoothed altitude)
        if alt is not None and dist is not None and dist[-1] > 500:
            sm = rolling_mean(np.pad(alt, (15, 15), mode="edge"), 31)
            gain = float(np.sum(np.clip(np.diff(sm), 0, None)))
            out["grade_m_per_km"] = gain / (dist[-1] / 1000.0)
        # speed at HR bands (running/hiking/riding)
        if hrv and spd is not None:
            bands = {}
            for name, lo, hi in (("z2", zones["zone2Floor"], zones["zone3Floor"]), ("z3", zones["zone3Floor"], zones["zone4Floor"])):
                sel = moving & (hr >= lo) & (hr < hi)
                if sel.sum() >= 300: bands[name] = {"speed": float(np.mean(spd[sel])), "s": int(sel.sum())}
            out["bands"] = bands
        # best efforts on TIMER time: paused seconds (record gaps) are removed, matching Garmin's own splits
        act = ~gap
        if dist is not None and act.sum() > 60:
            da = np.maximum.accumulate(dist[act]); ga = np.arange(len(da), dtype=float); na = len(da)
            if typ in RUN:
                be = {}
                for D in DIST_M:
                    if da[-1] - da[0] >= D:
                        i = np.where(da + D <= da[-1])[0]
                        tt = np.interp(da[i] + D, da, ga) - ga[i]
                        sec = float(tt.min())
                        if sec > 0 and D / sec <= 8.5: be[str(D)] = sec      # reject GPS glitches (<1:58/km)
                out["best_dist"] = be
            if typ in RUN | RIDE:
                bs = {}
                for D in DUR_S:
                    if na > D + 1:
                        d_at = np.interp(ga[:na - D] + D, ga, da); bs[str(D)] = float(np.max(d_at - da[:na - D]))
                out["best_dur_dist"] = bs
        if pw is not None and typ in RIDE:
            p = np.nan_to_num(pw, nan=0.0)[act]; bp = {}
            for D in PDUR_S:
                if len(p) > D: bp[str(D)] = float(rolling_mean(p, D).max())
            out["best_power"] = bp
            if len(p) > 30:
                r30 = rolling_mean(p, 30); out["np_w"] = float(np.mean(r30 ** 4) ** 0.25); out["avg_w"] = float(np.mean(p))
        return aid, out
    except Exception as e:
        return aid, {"ok": False, "why": repr(e)[:150]}

if __name__ == "__main__":
    maxs = int(sys.argv[sys.argv.index("--max-seconds") + 1]) if "--max-seconds" in sys.argv else 140
    db = sqlite3.connect("file:" + DBP + "?nolock=1", uri=True); db.execute("PRAGMA journal_mode=MEMORY"); db.execute("PRAGMA synchronous=OFF")
    db.execute("CREATE TABLE IF NOT EXISTS features(id INTEGER PRIMARY KEY, raw TEXT)")
    if "--redo" in sys.argv: db.execute("DELETE FROM features")
    zones = json.loads(db.execute("SELECT raw FROM singles WHERE name='hr_zones'").fetchone()[0])[0]
    todo = db.execute("""SELECT a.id, a.type FROM activities a JOIN fit_status f ON f.id=a.id AND f.status='ok'
        LEFT JOIN features x ON x.id=a.id WHERE x.id IS NULL ORDER BY a.start_local DESC""").fetchall()
    print("to parse:", len(todo), flush=True)
    end = time.time() + maxs; done = bad = 0
    with Pool(4) as pool:
        for aid, res in pool.imap_unordered(features, [(i, t, zones) for i, t in todo], chunksize=4):
            db.execute("INSERT OR REPLACE INTO features VALUES(?,?)", (aid, json.dumps(res))); done += 1; bad += (not res.get("ok"))
            if done % 50 == 0: db.commit()
            if time.time() > end: pool.terminate(); break
    db.commit()
    left = db.execute("SELECT count(*) FROM fit_status f LEFT JOIN features x ON x.id=f.id WHERE f.status='ok' AND x.id IS NULL").fetchone()[0]
    print(f"parsed {done} (failed {bad}), remaining {left}", flush=True)
