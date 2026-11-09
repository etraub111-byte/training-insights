"""Build dashboard.html (one self-contained file) from data/dashboard_data.json and scripts/dashboard_template.html."""
import os, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tpl = open(os.path.join(ROOT, "scripts", "dashboard_template.html"), encoding="utf-8").read()
data = open(os.path.join(ROOT, "data", "dashboard_data.json"), encoding="utf-8").read()
json.loads(data)                                   # fail loudly on bad data
data = data.replace("</", "<\\/")                   # keep the JSON from closing the script tag
i = tpl.index('<header class="top">')
head, body = tpl[:i], tpl[i:]
assert body.count("__DATA__") == 1
page = ('<!doctype html>\n<html lang="en"><head>\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        + head + '</head><body>\n' + body.replace("__DATA__", data) + '\n</body></html>\n')
out = os.path.join(ROOT, "dashboard.html")
open(out, "w", encoding="utf-8").write(page)
print("wrote", out, f"({len(page)/1e6:.1f} MB)")
