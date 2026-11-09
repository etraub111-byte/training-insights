import datetime as dt
from garmin_api import Client
c = Client()
end = dt.date(2026,11,7)
EP = {
 "dailysummaries": ("/usersummary-service/v2/dailysummaries", lambda a,b: {"startDate":a,"endDate":b}, ""),
 "sleepSummaries": ("/sleep-service/sleep/dailySleepSummariesByDate", lambda a,b: {"startDate":a,"endDate":b}, ""),
 "hrv": ("/hrv-service/hrv/daily/{a}/{b}", None, ""),
 "stress": ("/usersummary-service/stats/stress/daily/{a}/{b}", None, ""),
 "steps": ("/usersummary-service/stats/steps/daily/{a}/{b}", None, ""),
 "bodybattery": ("/wellness-service/wellness/bodyBattery/reports/daily", lambda a,b: {"startDate":a,"endDate":b}, ""),
 "weight": ("/weight-service/weight/range/{a}/{b}", None, ""),
 "intensity?": ("/usersummary-service/stats/hydration/daily/{a}/{b}", None, ""),
}
for name,(path,pf,_) in EP.items():
    res=[]
    for days in (14,28,31,32,60,90,92,180,365):
        a=(end-dt.timedelta(days=days-1)).isoformat(); b=end.isoformat()
        if pf: s,_r=c.get(path,pf(a,b),retries=1)
        else: s,_r=c.get(path.format(a=a,b=b),None,retries=1)
        res.append((days,s))
        if s!=200: break
    print(name,res,flush=True)
