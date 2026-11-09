import sys, json, time
sys.path.insert(0, __import__('os').path.dirname(__file__))
from garmin_api import Client
c = Client()
def show(label, r, n=220):
    s, b = r
    print(label, s, (json.dumps(b)[:n] if not isinstance(b, str) else b[:n]).replace("\n"," "))
# activities paging
for lim in (100, 500, 1000):
    s, b = c.get("/activitylist-service/activities/search/activities", {"start": 0, "limit": lim})
    print("limit", lim, s, len(b) if isinstance(b, list) else b)
total = 0; start = 0; last = None
while True:
    s, b = c.get("/activitylist-service/activities/search/activities", {"start": start, "limit": 100})
    if s != 200 or not b: print("stop", s, start); break
    total += len(b); start += 100; last = b[-1]
print("activities total", total, "oldest", last.get("startTimeLocal") if last else None)
# daily summaries history depth and range limits
for a, bnd in (("2026-10-01","2026-11-07"),("2026-01-01","2026-11-07")):
    show("dailysummaries v2 %s..%s"%(a,bnd), c.get("/usersummary-service/v2/dailysummaries", {"startDate": a, "endDate": bnd}), 100)
for y in range(2013, 2026):
    s, b = c.get("/usersummary-service/v2/dailysummaries", {"startDate": f"{y}-06-01", "endDate": f"{y}-06-07"})
    n = len(b.get("data", [])) if isinstance(b, dict) else b
    print("daily", y, s, n)
