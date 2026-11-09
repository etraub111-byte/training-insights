from garmin_api import Client
c = Client()
def n(b):
    if isinstance(b,list): return len(b)
    if isinstance(b,dict):
        for k in ("data","hrvSummaries","dailyWeightSummaries"):
            if k in b: return len(b[k])
        return 'dict'
    return b
for y in range(2014, 2026):
    a,b=f"{y}-06-01",f"{y}-06-07"
    r=[]
    for name,path,p in (
      ("daily","/usersummary-service/v2/dailysummaries",{"startDate":a,"endDate":b}),
      ("sleep","/sleep-service/sleep/dailySleepSummariesByDate",{"startDate":a,"endDate":b}),
      ("hrv",f"/hrv-service/hrv/daily/{a}/{b}",None),
      ("stress",f"/usersummary-service/stats/stress/daily/{a}/{b}",None),
      ("bb","/wellness-service/wellness/bodyBattery/reports/daily",{"startDate":a,"endDate":b}),
      ("weight",f"/weight-service/weight/range/{a}/{b}",None)):
        s,x=c.get(path,p,retries=1); r.append(f"{name}={s}/{n(x)}")
    print(y," ".join(r),flush=True)
