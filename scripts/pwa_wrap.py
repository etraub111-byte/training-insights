"""Package the encrypted dashboard as an installable web app (add to iPhone home screen).

usage: python scripts/pwa_wrap.py <encrypted.html> <outdir>
Writes <outdir>/index.html (with app tags injected), manifest and icons.
"""
import json, shutil, sys
from pathlib import Path

src, out = Path(sys.argv[1]), Path(sys.argv[2])
pwa = Path(__file__).resolve().parent.parent / "pwa"
html = src.read_text(encoding="utf-8")

tags = (
    '<link rel="manifest" href="manifest.webmanifest">'
    '<link rel="apple-touch-icon" href="icon-180.png">'
    '<meta name="apple-mobile-web-app-capable" content="yes">'
    '<meta name="mobile-web-app-capable" content="yes">'
    '<meta name="apple-mobile-web-app-title" content="Training">'
    '<meta name="apple-mobile-web-app-status-bar-style" content="default">'
    '<meta name="theme-color" content="#0f1720">'
)
if "</head>" not in html:
    sys.exit("pwa_wrap: no </head> found in encrypted page")
html = html.replace("</head>", tags + "</head>", 1)
if 'name="viewport"' not in html:
    html = html.replace("<head>", '<head><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">', 1)

out.mkdir(parents=True, exist_ok=True)
(out / "index.html").write_text(html, encoding="utf-8")
(out / "manifest.webmanifest").write_text(json.dumps({
    "name": "Training Insights", "short_name": "Training",
    "start_url": "./", "scope": "./", "display": "standalone",
    "background_color": "#0f1720", "theme_color": "#0f1720",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
    ],
}), encoding="utf-8")
for f in ("icon-180.png", "icon-192.png", "icon-512.png"):
    shutil.copy(pwa / f, out / f)
(out / ".nojekyll").write_text("")
print("pwa_wrap: wrote", out / "index.html", f"({len(html)/1e6:.2f} MB)")
