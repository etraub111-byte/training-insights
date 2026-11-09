"""Derive all dashboard metrics from data/garmin.sqlite -> data/dashboard_data.json.
Formulas are documented in README.md and in the dashboard's Methodology section. No GPS data is used or exported."""
import os, sys, json, sqlite3, math, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from garmin_api import ROOT
db = sqlite3.connect("file:" + os.path.join(ROOT, "data", "garmin.sqlite") + "?mode=ro&nolock=1", uri=True)
OUT = os.path.join(ROOT, "data", "dashboard_data.json")
zones = json.loads(db.execute("SELECT raw FROM singles WHERE name='hr_zones'").fetchone()[0])[0]
FLOORS = [zones[f"zone{i}Floor"] for i in range(1, 6)]
GROUP = {"running": "Run", "trail_running": "Run", "treadmill_running": "Run",
         "cycling": "Ride", "virtual_ride": "Ride", "indoor_cycling": "Ride", "mountain_biking": "Ride",
         "hiking": "Hike", "lap_swimming": "Swim", "open_water_swimming": "Swim"}
GROUPS = ["Run", "Ride", "Hike", "Swim", "Other"]
def py(x):
    if x is None: return None
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (np.floating, float)): return None if (math.isnan(x) or math.isinf(x)) else round(float(x), 4)
    if isinstance(x, (np.bool_,)): return bool(x)
    if isinstance(x, dict): return {str(k): py(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, np.ndarray)): return [py(v) for v in x]
    return x

# ------------------------------------------------------------------ activities
feat = {i: json.loads(r) for i, r in db.execute("SELECT id, raw FROM features")}
rows = []
for aid, typ, raw in db.execute("SELECT id, type, raw FROM activities"):
    a = json.loads(raw); f = feat.get(aid, {})
    if not f.get("ok"): f = {}
    dur = (a.get("duration") or 0) / 60.0
    rows.append(dict(
        id=aid, date=a["startTimeLocal"][:10], start=a["startTimeLocal"][:16], type=typ, group=GROUP.get(typ, "Other"),
        dist_km=(a.get("distance") or 0) / 1000.0, dur_min=dur, mov_min=(a.get("movingDuration") or 0) / 60.0,
        avg_hr=a.get("averageHR"), max_hr=a.get("maxHR"), elev=a.get("elevationGain"), speed=a.get("averageSpeed"),
        cad=a.get("averageRunningCadenceInStepsPerMinute"), kcal=a.get("calories"),
        g_load=a.get("activityTrainingLoad"), te_a=a.get("aerobicTrainingEffect"), te_n=a.get("anaerobicTrainingEffect"),
        trimp=f.get("trimp"), zone_s=f.get("zone_s"), dec=f.get("decoupling_pct"), ef=f.get("ef"), ef_basis=f.get("ef_basis"),
        steady_s=f.get("steady_s"), grade=f.get("grade_m_per_km"), z2=(f.get("bands") or {}).get("z2"), z3=(f.get("bands") or {}).get("z3"),
        best_dist=f.get("best_dist") or {}, best_dur=f.get("best_dur_dist") or {}, best_pw=f.get("best_power") or {},
        np_w=f.get("np_w"), avg_w=f.get("avg_w"), has_fit=bool(f)))
A = pd.DataFrame(rows).sort_values("start").reset_index(drop=True)
EXCL = A[A.dur_min > 1440]                       # implausible multi-day "activities" (manual/forgotten timers)
A = A[A.dur_min <= 1440].reset_index(drop=True)

# load = Banister TRIMP computed per second from heart rate (HR-reserve fraction), units "TRIMP"
A["load"] = A.trimp
pair = A[(A.trimp > 0) & (A.g_load > 0)]
def cmp_stats(s_):
    return {"n": int(len(s_)), "pearson_r": round(float(np.corrcoef(s_.trimp, s_.g_load)[0, 1]), 2),
            "spearman_r": round(float(s_.trimp.rank().corr(s_.g_load.rank())), 2), "median_garmin_over_trimp": round(float((s_.g_load / s_.trimp).median()), 2)}
VAL = {"load_vs_garmin_training_load": {"all": cmp_stats(pair), **{g_: cmp_stats(x) for g_, x in pair.groupby("group") if len(x) >= 8}}}
A["imputed"] = False
per_min = {}
for g in GROUPS:
    s_ = A[(A.group == g) & (A.load > 0) & (A.dur_min >= 10)]
    if len(s_) >= 3: per_min[g] = float((s_.load / s_.dur_min).median())
fallback = 0.5 * float(np.median(list(per_min.values()))) if per_min else 0.0
for i, r in A[A.load.isna()].iterrows():          # activities without usable HR: typical load/min for that sport, duration capped at 4 h
    A.at[i, "load"] = (per_min.get(r.group, fallback)) * min(r.dur_min, 240); A.at[i, "imputed"] = True
VAL["load_imputed_activities"] = int(A.imputed.sum())
VAL["excluded_over_24h"] = [dict(id=int(r.id), date=r.date, type=r.type, hours=round(r.dur_min / 60, 1)) for _, r in EXCL.iterrows()]

# ------------------------------------------------------------------ daily frame
W = {}
for ep, date, raw in db.execute("SELECT endpoint, date, raw FROM daily"): W.setdefault(ep, {})[date] = json.loads(raw)
d0 = min(A.date.min(), min(W["daily"])); d1 = max(A.date.max(), max(W["daily"]))
days = pd.date_range(d0, d1, freq="D"); ds = [d.strftime("%Y-%m-%d") for d in days]
D = pd.DataFrame(index=ds)
for g in GROUPS:
    s = A[A.group == g].groupby("date")
    D[f"load_{g}"] = s.load.sum().reindex(ds).fillna(0.0)
    D[f"km_{g}"] = s.dist_km.sum().reindex(ds).fillna(0.0)
    D[f"min_{g}"] = s.dur_min.sum().reindex(ds).fillna(0.0)
D["load"] = D[[f"load_{g}" for g in GROUPS]].sum(axis=1)
D["n_act"] = A.groupby("date").id.count().reindex(ds).fillna(0).astype(int)
D["elev"] = A.groupby("date").elev.sum().reindex(ds).fillna(0.0)
atl = ctl = 0.0; ka, kc = 1 - math.exp(-1 / 7), 1 - math.exp(-1 / 42); ATL, CTL, TSB = [], [], []
for l in D.load.values:
    TSB.append(ctl - atl); atl += (l - atl) * ka; ctl += (l - ctl) * kc; ATL.append(atl); CTL.append(ctl)
D["atl"], D["ctl"], D["tsb"] = ATL, CTL, TSB
D["acute7"] = D.load.rolling(7, min_periods=7).sum(); D["chronic28"] = D.load.rolling(28, min_periods=28).sum() / 4.0
D["acwr"] = D.acute7 / D.chronic28.where(D.chronic28 > 0)
D["ramp7"] = D.ctl - D.ctl.shift(7)
D["warmup"] = [i < 42 for i in range(len(D))]
def pull(ep, fn):
    return pd.Series({d: fn(v) for d, v in W.get(ep, {}).items()}, dtype="float64").reindex(ds)
def g(dct, *ks):
    for k in ks:
        if not isinstance(dct, dict): return None
        dct = dct.get(k)
    return dct
D["rhr"] = pull("daily", lambda v: g(v, "heartRate", "restingValue"))
D["hr_max_day"] = pull("daily", lambda v: g(v, "heartRate", "maxValue"))
D["stress"] = pull("daily", lambda v: g(v, "stress", "avgLevel"))
D["bb_max"] = pull("daily", lambda v: g(v, "bodyBattery", "maxValue")); D["bb_min"] = pull("daily", lambda v: g(v, "bodyBattery", "minValue"))
D["bb_charged"] = pull("daily", lambda v: g(v, "bodyBattery", "chargedValue")); D["bb_drained"] = pull("daily", lambda v: g(v, "bodyBattery", "drainedValue"))
D["resp"] = pull("daily", lambda v: g(v, "respiration", "avgValue"))
D["im_mod"] = pull("daily", lambda v: g(v, "intensityMinutes", "moderate")); D["im_vig"] = pull("daily", lambda v: g(v, "intensityMinutes", "vigorous"))
D["steps"] = pull("steps", lambda v: v.get("totalSteps"))
D["sleep_h"] = pull("sleep", lambda v: (v.get("sleepTimeSeconds") or 0) / 3600.0 or None)
for k, n in (("deep", "deepSleepSeconds"), ("light", "lightSleepSeconds"), ("rem", "remSleepSeconds"), ("awake", "awakeSleepSeconds")):
    D[f"sl_{k}"] = pull("sleep", lambda v, n=n: (v.get(n) / 3600.0) if v.get(n) is not None and (v.get("sleepTimeSeconds") or 0) > 0 else None)
D["sleep_score"] = pull("sleep", lambda v: g(v, "sleepScores", "overall", "value"))
D["hrv"] = pull("hrv", lambda v: v.get("lastNightAvg")); D["hrv_weekly"] = pull("hrv", lambda v: v.get("weeklyAvg"))
D["hrv_lo"] = pull("hrv", lambda v: g(v, "baseline", "balancedLow")); D["hrv_hi"] = pull("hrv", lambda v: g(v, "baseline", "balancedUpper"))
D["rhr7"] = D.rhr.rolling(7, min_periods=3).mean(); D["rhr_base"] = D.rhr.rolling(60, min_periods=14).median()
D["hrv7"] = D.hrv.rolling(7, min_periods=3).mean(); D["hrv_base"] = D.hrv.rolling(60, min_periods=20).mean(); D["hrv_sd"] = D.hrv.rolling(60, min_periods=20).std()
D["hrv_z"] = (D.hrv7 - D.hrv_base) / D.hrv_sd.where(D.hrv_sd > 0)
D["sleep7"] = D.sleep_h.rolling(7, min_periods=3).mean()
hrv_status = pd.Series({d: v.get("status") for d, v in W.get("hrv", {}).items()}).reindex(ds)

# ------------------------------------------------------------------ performance index (Daniels VDOT) + critical speed
def vdot(dist_m, t_s):
    t = t_s / 60.0
    if t < 3.5 or t > 180: return None
    v = dist_m / t
    return (-4.60 + 0.182258 * v + 0.000104 * v * v) / (0.8 + 0.1894393 * math.exp(-0.012778 * t) + 0.2989558 * math.exp(-0.1932605 * t))
assert abs(vdot(5000, 1200) - 49.8) < 0.2, vdot(5000, 1200)    # Daniels' published table: 5k in 20:00 -> VDOT 49.8
vd = {}; vd_how = {}
for _, r in A[A.type.isin(["running", "trail_running"])].iterrows():
    if r.grade is not None and not pd.isna(r.grade) and r.grade > 30: continue
    best = None
    for k, t in (r.best_dist or {}).items():
        if float(k) >= 3000: v = vdot(float(k), t); best = max(best or (0, ""), (v, f"{float(k)/1000:g}k"), key=lambda x: x[0]) if v else best
    for k, m in (r.best_dur or {}).items():
        if int(k) >= 1200:
            v = vdot(m, float(k)); best = max(best or (0, ""), (v, f"{int(k)//60}min"), key=lambda x: x[0]) if v else best
    if best and best[0] > 0: vd[r.id] = best[0]; vd_how[r.id] = best[1]
A["vdot"] = A.id.map(vd); A["vdot_basis"] = A.id.map(vd_how)
vser = A.dropna(subset=["vdot"]).groupby("date").vdot.max().reindex(ds)
D["vdot90"] = vser.rolling(90, min_periods=1).max().where(vser.rolling(90, min_periods=1).count() >= 1)
D.loc[vser.rolling(90, min_periods=1).count() < 1, "vdot90"] = np.nan
# critical speed model on rolling 180 days of best distances over 3/5/10/20 min (running): d = D' + CS * t
CS = []
runs = A[A.type.isin(["running", "trail_running"]) & ((A.grade.isna()) | (A.grade <= 30))]
for m_end in sorted({min(m, pd.Timestamp(d1)) for m in (pd.date_range(d0, d1, freq="MS") + pd.offsets.MonthEnd(0))}):
    lo = (m_end - pd.Timedelta(days=180)).strftime("%Y-%m-%d"); hi = m_end.strftime("%Y-%m-%d")
    w = runs[(runs.date > lo) & (runs.date <= hi)]; pts = []
    for dsec in (180, 300, 600, 1200):
        v = [r.best_dur.get(str(dsec)) for _, r in w.iterrows() if r.best_dur.get(str(dsec))]
        if v: pts.append((dsec, max(v)))
    if len(pts) == 4:
        t = np.array([p[0] for p in pts], float); d = np.array([p[1] for p in pts], float)
        slope, icpt = np.polyfit(t, d, 1); r2 = 1 - np.sum((d - (icpt + slope * t)) ** 2) / np.sum((d - d.mean()) ** 2)
        if 2.0 < slope < 6.5 and 0 <= icpt < 600: CS.append(dict(date=hi, cs=slope, dprime=icpt, r2=r2))

# ------------------------------------------------------------------ progression, records
PROG = {}
for dist in ("1000", "1609.344", "5000", "10000", "21097.5"):
    pts = []
    for _, r in A.iterrows():
        t = (r.best_dist or {}).get(dist)
        if t and r.type in ("running", "trail_running", "treadmill_running"): pts.append([r.date, round(t, 1), int(r.id)])
    PROG[dist] = sorted(pts)
POWER = {}
for dsec in ("5", "60", "300", "600", "1200", "1800", "3600"):
    POWER[dsec] = sorted([[r.date, round(r.best_pw[dsec], 1)] for _, r in A.iterrows() if r.best_pw.get(dsec)])
dd = D.copy()
records = []
def fmt_t(s):
    s = int(round(s)); h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
for dist, label in (("1609.344", "Fastest mile"), ("5000", "Fastest 3.1 mi"), ("10000", "Fastest 6.2 mi"), ("21097.5", "Fastest half marathon (13.1 mi)")):
    if PROG[dist]:
        b = min(PROG[dist], key=lambda p: p[1]); records.append(dict(label=label, value=fmt_t(b[1]), date=b[0], sport="Run"))
rr = A[A.group == "Run"]
if len(rr):
    r = rr.loc[rr.dist_km.idxmax()]; records.append(dict(label="Longest run", value=f"{r.dist_km*0.621371:.1f} mi", date=r.date, sport="Run"))
    r = rr.loc[rr.elev.fillna(0).idxmax()]; records.append(dict(label="Most climbing in a run", value=f"{r.elev*3.28084:,.0f} ft", date=r.date, sport="Run"))
rd = A[A.group == "Ride"]
if len(rd):
    r = rd.loc[rd.dist_km.idxmax()]; records.append(dict(label="Longest ride", value=f"{r.dist_km*0.621371:.1f} mi", date=r.date, sport="Ride"))
    if POWER["1200"]: b = max(POWER["1200"], key=lambda p: p[1]); records.append(dict(label="Best 20-min power", value=f"{b[1]:.0f} W", date=b[0], sport="Ride"))
hk = A[A.group == "Hike"]
if len(hk):
    r = hk.loc[hk.dist_km.idxmax()]; records.append(dict(label="Longest hike", value=f"{r.dist_km*0.621371:.1f} mi", date=r.date, sport="Hike"))
    r = hk.loc[hk.elev.fillna(0).idxmax()]; records.append(dict(label="Most climbing in a hike", value=f"{r.elev*3.28084:,.0f} ft", date=r.date, sport="Hike"))
wk = D.assign(wk=pd.to_datetime(D.index).to_period("W-SUN")).groupby("wk").agg(km=("km_Run", "sum"), load=("load", "sum"), mins=("min_Run", "sum"))
if len(wk):
    w = wk.km.idxmax(); records.append(dict(label="Biggest running week", value=f"{wk.km.max()*0.621371:.1f} mi", date=str(w.start_time.date()), sport="Run"))
    w = wk.load.idxmax(); records.append(dict(label="Highest-load week", value=f"{wk.load.max():.0f} load", date=str(w.start_time.date()), sport="All"))
r = A.loc[A.load.idxmax()]; records.append(dict(label="Hardest single activity (load)", value=f"{r.load:.0f}", date=r.date, sport=r.group))
# streaks of consecutive days with an activity >= 10 min
act_days = set(A[A.dur_min >= 10].date); best = cur = 0; best_end = None
for d_ in ds:
    cur = cur + 1 if d_ in act_days else 0
    if cur > best: best, best_end = cur, d_
records.append(dict(label="Longest daily streak (>=10 min)", value=f"{best} days", date=best_end, sport="All"))

# ------------------------------------------------------------------ insights
INS = {}
def pct_rank(x, arr):
    arr = np.array([a for a in arr if not np.isnan(a)]); return float(np.mean(arr <= x) * 100) if len(arr) else None
ok_days = D.index[~D.warmup]
wk_med = D.loc[ok_days, "acute7"].replace(0, np.nan).median()
cond = (D.acwr > 1.5) & (D.acute7 >= 0.8 * wk_med) & (~D.warmup)
eps, cur = [], None
for i, d_ in enumerate(ds):
    if cond.iloc[i]:
        if cur and i - cur["_last"] <= 3: cur["_last"] = i
        else:
            if cur: eps.append(cur)
            cur = {"_first": i, "_last": i}
if cur: eps.append(cur)
over = []
for e in eps:
    a_, b_ = e["_first"], e["_last"]; seg = D.iloc[a_:b_ + 1]
    pre = D.rhr.iloc[max(0, a_ - 14):a_].mean(); post = D.rhr.iloc[b_ + 1:b_ + 8].mean()
    hpre = D.hrv.iloc[max(0, a_ - 14):a_].mean(); hpost = D.hrv.iloc[b_ + 1:b_ + 8].mean()
    over.append(dict(start=ds[a_], end=ds[b_], days=b_ - a_ + 1, peak_acwr=seg.acwr.max(), peak_week_load=seg.acute7.max(),
                     rhr_change=(post - pre) if not (np.isnan(pre) or np.isnan(post)) else None,
                     hrv_change=(hpost - hpre) if not (np.isnan(hpre) or np.isnan(hpost)) else None))
INS["overreaching"] = sorted(over, key=lambda x: -x["peak_acwr"])[:10]
INS["overreaching_total"] = len(over)
# detraining: >=14 consecutive days without an activity >= 10 min
gaps, i = [], 0
while i < len(ds):
    if ds[i] not in act_days:
        j = i
        while j + 1 < len(ds) and ds[j + 1] not in act_days: j += 1
        if j - i + 1 >= 14 and i > 0 and j < len(ds) - 1:
            c0 = D.ctl.iloc[i - 1]; c1 = D.ctl.iloc[j]
            rec_days = None
            for k in range(j + 1, len(ds)):
                if D.ctl.iloc[k] >= 0.9 * c0: rec_days = k - j; break
            gaps.append(dict(start=ds[i], end=ds[j], days=j - i + 1, ctl_before=c0, ctl_after=c1, ctl_drop_pct=(c0 - c1) / c0 * 100 if c0 > 0 else None, days_to_regain_90pct=rec_days))
        i = j + 1
    else: i += 1
INS["detraining"] = gaps
# training blocks before the best performance peaks
def window_feats(end_idx, span):
    lo = max(0, end_idx - span); seg = D.iloc[lo:end_idx]; seg_dates = set(seg.index)
    acts = A[A.date.isin(seg_dates)]; z = np.zeros(6)
    for zs in acts.zone_s.dropna(): z += np.array(zs)
    hard = (z[4] + z[5]) / z[1:].sum() if z[1:].sum() > 0 else np.nan
    wks = len(seg) / 7.0
    return dict(sessions_wk=len(acts[acts.dur_min >= 10]) / wks, run_km_wk=seg.km_Run.sum() / wks, load_wk=seg.load.sum() / wks,
                hard_share=hard, sleep_h=seg.sleep_h.mean(), rhr=seg.rhr.mean(), hrv=seg.hrv.mean(),
                tsb_end=D.tsb.iloc[end_idx] if end_idx < len(D) else np.nan, ctl_end=D.ctl.iloc[end_idx] if end_idx < len(D) else np.nan,
                acwr_end=D.acwr.iloc[end_idx] if end_idx < len(D) else np.nan)
base_idx = list(range(56, len(ds), 7)); base = [window_feats(i, 56) for i in base_idx if i >= 42 + 56 - 56 and not D.warmup.iloc[i]]
base_med = {k: float(np.nanmedian([b[k] for b in base])) for k in base[0]} if base else {}
v90 = D.vdot90.values; cand = []
for lo in range(0, len(ds), 180):
    seg = v90[lo:lo + 180]
    if np.isfinite(seg).any():
        j = lo + int(np.nanargmax(seg))
        if j >= 70: cand.append((j, float(v90[j])))
chosen = []
for j, v in sorted(cand, key=lambda p: -p[1]):
    if all(abs(j - i) >= 120 for i, _ in chosen): chosen.append((j, v))
    if len(chosen) == 5: break
INS["best_blocks"] = [dict(peak_date=ds[i], vdot=v, **window_feats(i, 56)) for i, v in sorted(chosen)]
INS["block_baseline"] = base_med
# PR events and what preceded them
PR = []                      # season-best events: faster than every effort at that distance in the previous 365 days
for dist, pts in PROG.items():
    for k_, (dte, t, aid) in enumerate(pts):
        prev = [q[1] for q in pts[:k_] if 0 < (pd.Timestamp(dte) - pd.Timestamp(q[0])).days <= 365]
        if len(prev) >= 3 and t < min(prev) - 0.5: PR.append((dte, dist))
pr_dates = sorted({d_ for d_, _ in PR if D.index.get_loc(d_) >= 98})
pr_f = [window_feats(D.index.get_loc(d_), 28) for d_ in pr_dates]
base28 = [window_feats(i, 28) for i in range(98, len(ds), 7)]
INS["pr_analysis"] = dict(n_events=len(pr_dates), by_feature={}, dates=pr_dates[-12:])
for k in ("sessions_wk", "run_km_wk", "load_wk", "hard_share", "sleep_h", "rhr", "hrv", "tsb_end", "ctl_end", "acwr_end"):
    vals = [p[k] for p in pr_f if not pd.isna(p[k])]; allv = [b[k] for b in base28 if not pd.isna(b[k])]
    if len(vals) >= 5 and len(allv) >= 20:
        INS["pr_analysis"]["by_feature"][k] = dict(pr_median=float(np.median(vals)), typical_median=float(np.median(allv)), pr_pct_rank=pct_rank(float(np.median(vals)), allv), n=len(vals))
# next-run performance vs prior recovery state (detrended)
rr = A[A.ef.notna() & (A.type.isin(["running", "trail_running"])) & ((A.grade.isna()) | (A.grade <= 30))].copy()
rr["t"] = pd.to_datetime(rr.date); rr["lef"] = np.log(rr.ef.astype(float))
res = []
for i, r in rr.iterrows():
    nb = rr[(abs((rr.t - r.t).dt.days) <= 45) & (rr.index != i)]
    res.append(r.lef - nb.lef.median() if len(nb) >= 5 else np.nan)
rr["resid"] = res
Dj = D.assign(rhr_dev=D.rhr - D.rhr.rolling(28, min_periods=10).median(), load_prev1=D.load.shift(1), load_prev3=D.load.rolling(3).sum().shift(1))
facs = [("Sleep duration (night before)", "sleep_h"), ("Sleep score", "sleep_score"), ("HRV (last night avg)", "hrv"),
        ("Resting HR vs 28d norm", "rhr_dev"), ("Load yesterday", "load_prev1"), ("Load last 3 days", "load_prev3"), ("Form (TSB)", "tsb")]
corr = []
for lab, col in facs:
    x = rr.date.map(Dj[col]); m = (~x.isna()) & (~rr.resid.isna())
    n = int(m.sum())
    if n >= 15:
        r_ = float(np.corrcoef(x[m].astype(float), rr.resid[m].astype(float))[0, 1])
        t_ = r_ * math.sqrt((n - 2) / max(1e-9, 1 - r_ * r_)); p_ = math.erfc(abs(t_) / math.sqrt(2))
        corr.append(dict(factor=lab, r=r_, n=n, p=p_))
INS["efficiency_correlates"] = corr
INS["efficiency_n_runs"] = int(rr.resid.notna().sum())

# ------------------------------------------------------------------ validation + coverage
bv = {}
for dist, gk in (("1000", "fastestSplit_1000"), ("1609.344", "fastestSplit_1609"), ("5000", "fastestSplit_5000"), ("10000", "fastestSplit_10000")):
    dif = []
    for aid, raw in db.execute("SELECT id, raw FROM activities"):
        a = json.loads(raw); f = feat.get(aid, {})
        if f.get("ok") and dist in (f.get("best_dist") or {}) and a.get(gk): dif.append(f["best_dist"][dist] - a[gk])
    dif = np.array(dif)
    if len(dif): bv[dist] = dict(n=int(len(dif)), within_2s=float(np.mean(abs(dif) <= 2)), within_5s=float(np.mean(abs(dif) <= 5)), within_15s=float(np.mean(abs(dif) <= 15)), median_diff_s=float(np.median(dif)))
VAL["best_effort_vs_garmin_splits"] = bv
pw_pairs = []
for aid, raw in db.execute("SELECT id, raw FROM activities"):
    a = json.loads(raw); f = feat.get(aid, {})
    if (f.get("best_power") or {}).get("1200") and a.get("max20MinPower"): pw_pairs.append(f["best_power"]["1200"] / a["max20MinPower"])
VAL["best_20min_power_vs_garmin"] = dict(n=len(pw_pairs), median_ratio=float(np.median(pw_pairs)) if pw_pairs else None)
st_ok = tot = 0
for v in W["sleep"].values():
    if v.get("sleepTimeSeconds"): 
        tot += 1; st_ok += abs((v.get("deepSleepSeconds") or 0) + (v.get("lightSleepSeconds") or 0) + (v.get("remSleepSeconds") or 0) - v["sleepTimeSeconds"]) <= 120
VAL["sleep_stages_sum_to_total"] = dict(n=tot, share_within_2min=st_ok / tot if tot else None)
cov = {}
for col, lab in (("rhr", "Resting HR"), ("sleep_h", "Sleep"), ("hrv", "HRV"), ("stress", "Stress"), ("bb_max", "Body Battery"), ("steps", "Steps")):
    s = D[col].dropna(); cov[lab] = dict(days=int(len(s)), first=s.index[0] if len(s) else None, last=s.index[-1] if len(s) else None)
cov["Weight"] = dict(days=len(W.get("weight", {})), first=min(W["weight"]) if W.get("weight") else None, last=max(W["weight"]) if W.get("weight") else None)
cov["Activities"] = dict(days=int(A.shape[0]), first=A.date.min(), last=A.date.max())
cov["Activities with heart rate"] = int(A.trimp.notna().sum()); cov["Activities with Garmin training load"] = int(A.g_load.notna().sum())
cov["Activities with power"] = int(A.np_w.notna().sum()); cov["FIT files parsed"] = int(A.has_fit.sum())
cov["VO2max"] = "Not exposed by the Garmin Personal API (no endpoint). A running performance index (VDOT) is derived from your best efforts instead."
cov["Gear"] = "Not exposed by the Garmin Personal API (no gear endpoint). Gear mileage can't be computed."
cov["Timezones"] = "Activity and daily dates use Garmin's local calendar date, so travel (US to Japan) is handled by the device's local time."
cov["Devices"] = dict(manufacturer_counts={str(k): int(v) for k, v in A.id.map(lambda i: json.loads(db.execute('select raw from activities where id=?', (int(i),)).fetchone()[0]).get('manufacturer')).value_counts(dropna=False).items()})

# ------------------------------------------------------------------ export
dcols = [c for c in D.columns if c != "warmup"]
daily = {"dates": ds, **{c: py(D[c].round(3).tolist()) for c in dcols}, "warmup": D.warmup.tolist(), "hrv_status": py(hrv_status.where(hrv_status.notna(), None).tolist())}
acols = ["id", "date", "start", "type", "group", "dist_km", "dur_min", "mov_min", "avg_hr", "max_hr", "elev", "speed", "cad", "kcal", "g_load", "te_a", "te_n", "trimp", "load", "imputed",
         "zone_s", "dec", "ef", "ef_basis", "steady_s", "grade", "np_w", "avg_w", "vdot", "vdot_basis"]
acts = []
for _, r in A.iterrows():
    o = {c: py(r[c]) for c in acols}
    o["z2"] = py(r.z2["speed"]) if isinstance(r.z2, dict) else None; o["z3"] = py(r.z3["speed"]) if isinstance(r.z3, dict) else None
    acts.append(o)
out = dict(generated=dt.datetime.now().isoformat(timespec="seconds"),
           meta=dict(rest_hr=zones["restingHeartRateUsed"], max_hr=zones["maxHeartRateUsed"], zone_floors=FLOORS, first=d0, last=d1,
                     n_activities=len(A), per_min_load=py(per_min)),
           daily=daily, activities=acts, progression=PROG, power=POWER, critical_speed=py(CS), records=py(records), insights=py(INS), validation=py(VAL), coverage=py(cov))
s = json.dumps(out, allow_nan=False, separators=(",", ":"))
open(OUT, "w").write(s); print("wrote", OUT, f"{len(s)/1e6:.2f} MB")
print(VAL["load_vs_garmin_training_load"]); print("imputed", VAL["load_imputed_activities"], "vdot acts", int(A.vdot.notna().sum()), "CS pts", len(CS))
print("overreach episodes", len(over), "detrain gaps", len(gaps), "PR events", len(pr_dates), "blocks", len(INS["best_blocks"]))
