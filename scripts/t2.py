import time, json
from garmin_api import Client
c = Client()
def t(label, path, params=None, n=160):
    t0=time.time(); s,b=c.get(path,params,retries=1)
    if isinstance(b,(dict,list)):
        if isinstance(b,dict): d=list(b.keys())[:6]
        else: d=f"list[{len(b)}]"
        extra=json.dumps(b)[:n]
    else: d=None; extra=str(b)[:n]
    print(f"{label:34} {s} {round(time.time()-t0,1)}s keys={d} {extra!r}", flush=True)
D="2026-11-01"; E="2026-11-07"
t("daily v2 week","/usersummary-service/v2/dailysummaries",{"startDate":D,"endDate":E},60)
t("daily v2 1yr","/usersummary-service/v2/dailysummaries",{"startDate":"2025-11-01","endDate":E},60)
t("sleep summaries","/sleep-service/sleep/dailySleepSummariesByDate",{"startDate":D,"endDate":E})
t("sleep dailySleep date","/sleep-service/sleep/dailySleep",{"date":E})
t("hrv daily","/hrv-service/hrv/daily/%s/%s"%(D,E),None,80)
t("stress daily","/usersummary-service/stats/stress/daily/%s/%s"%(D,E))
t("steps daily","/usersummary-service/stats/steps/daily/%s/%s"%(D,E))
t("bodybattery","/wellness-service/wellness/bodyBattery/reports/daily",{"startDate":D,"endDate":E})
t("weight range","/weight-service/weight/range/%s/%s"%(D,E))
t("hr daily","/wellness-service/wellness/dailyHeartRate",{"date":E},80)
t("hr zones","/biometric-service/heartRateZones/v2")
t("fitness age","/fitnessage-service/fitnessage/v2/"+E)
t("settings","/userprofile-service/userprofile/settings",None,80)
t("usersummary daily","/usersummary-service/usersummary/daily",{"calendarDate":E},60)
t("wellness act summary","/wellnessactivity-service/activity/summary/range/%s/%s"%(D,E),None,100)
