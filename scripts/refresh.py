"""One command to refresh everything:  python3 scripts/refresh.py
Pulls new data from Garmin, downloads and parses new activity files, recomputes metrics, rebuilds dashboard.html."""
import os, sys, subprocess, time
HERE = os.path.dirname(os.path.abspath(__file__))
steps = [("Pull Garmin data", ["ingest.py"]), ("Download activity files", ["fit_download.py", "--max-seconds", "3000", "--workers", "4"]),
         ("Parse activity files", ["parse_fit.py", "--max-seconds", "3000"]), ("Compute metrics", ["analyze.py"]), ("Build dashboard", ["build_dashboard.py"])]
for label, cmd in steps:
    print(f"\n== {label}", flush=True); t0 = time.time()
    r = subprocess.run([sys.executable] + [os.path.join(HERE, cmd[0])] + cmd[1:])
    if r.returncode: sys.exit(f"{label} failed (exit {r.returncode}). Fix the error above and run again; completed work is kept.")
    print(f"   done in {time.time()-t0:.0f}s", flush=True)
print("\nOpen dashboard.html in your browser.")
