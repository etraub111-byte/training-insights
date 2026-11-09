import time, json
from garmin_api import Client
import garmin_api, urllib.request, urllib.error
c = Client(); t=c._token()
def raw(path):
    t0=time.time()
    req=urllib.request.Request(garmin_api.BASE+path,headers={"Authorization":"Bearer "+t})
    try:
        with urllib.request.urlopen(req,timeout=25) as f:
            b=f.read(); return f.status,len(b),round(time.time()-t0,1),None
    except urllib.error.HTTPError as e:
        return e.code,0,round(time.time()-t0,1),(e.read().decode()[:200], e.headers.get("Retry-After"))
    except Exception as e:
        return 'ERR',0,round(time.time()-t0,1),str(e)[:100]
A="/activitylist-service/activities/search/activities"
for q in ("?start=0&limit=100","?start=0&limit=200","?start=0&limit=500","?start=100&limit=100"):
    print(q, raw(A+q), flush=True)
