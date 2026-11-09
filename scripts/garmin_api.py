"""Minimal Garmin Connect Personal API client (stdlib only). Never prints secrets."""
import os, json, time, urllib.request, urllib.error, urllib.parse
BASE = "https://personal.connectapi.garmin.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_env():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

class Client:
    def __init__(self):
        load_env()
        self.key = os.environ.get("GARMIN_API_KEY")
        if not self.key:
            raise SystemExit("GARMIN_API_KEY missing (put it in .env)")
        self.token = None; self.token_t = 0; self.calls = 0

    def _token(self):
        if self.token and time.time() - self.token_t < 20 * 3600:
            return self.token
        req = urllib.request.Request(
            BASE + "/personalapitoken-service/personal-api/personal-api-key/token",
            method="POST", headers={"Authorization": "ApiKey " + self.key})
        with urllib.request.urlopen(req, timeout=30) as f:
            self.token = f.read().decode().strip()
        self.token_t = time.time()
        return self.token

    def get(self, path, params=None, retries=6):
        url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
        delay = 2
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers={"Authorization": "Bearer " + self._token(), "Accept": "application/json"})
                self.calls += 1
                with urllib.request.urlopen(req, timeout=60) as f:
                    body = f.read().decode()
                    return f.status, (json.loads(body) if body.strip() else None)
            except urllib.error.HTTPError as e:
                body = e.read().decode()[:400]
                if e.code == 401:
                    self.token = None
                elif e.code in (429, 500, 502, 503, 504):
                    ra = e.headers.get("Retry-After")
                    time.sleep(float(ra) if ra and ra.isdigit() else delay); delay = min(delay * 2, 60); continue
                else:
                    return e.code, body
                if attempt == retries - 1:
                    return e.code, body
            except (urllib.error.URLError, TimeoutError):
                time.sleep(delay); delay = min(delay * 2, 60)
        return 0, "failed after retries"
