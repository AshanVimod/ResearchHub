"""One-time download of front-end libraries into static/vendor.

Run once with internet access:  .venv\\Scripts\\python scripts\\fetch_vendor.py
After that the app never touches a CDN.
"""
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "static" / "vendor"
NPM = "https://cdn.jsdelivr.net/npm/"

FILES = {
    "bootstrap/bootstrap.min.css": "bootstrap@5.3.3/dist/css/bootstrap.min.css",
    "bootstrap/bootstrap.bundle.min.js": "bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js",
    "bootstrap-icons/bootstrap-icons.min.css": "bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
    "bootstrap-icons/fonts/bootstrap-icons.woff2": "bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff2",
    "bootstrap-icons/fonts/bootstrap-icons.woff": "bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff",
    "htmx/htmx.min.js": "htmx.org@2.0.4/dist/htmx.min.js",
    "alpine/alpine.min.js": "alpinejs@3.14.8/dist/cdn.min.js",
    "fullcalendar/index.global.min.js": "fullcalendar@6.1.15/index.global.min.js",
    "sortable/Sortable.min.js": "sortablejs@1.15.6/Sortable.min.js",
    "chartjs/chart.umd.js": "chart.js@4.4.7/dist/chart.umd.js",
    "fonts/eb-garamond-latin-500-normal.woff2": "@fontsource/eb-garamond@5.1.0/files/eb-garamond-latin-500-normal.woff2",
    "fonts/eb-garamond-latin-600-normal.woff2": "@fontsource/eb-garamond@5.1.0/files/eb-garamond-latin-600-normal.woff2",
    "fonts/eb-garamond-latin-500-italic.woff2": "@fontsource/eb-garamond@5.1.0/files/eb-garamond-latin-500-italic.woff2",
}

# PDF.js prebuilt viewer (used from Phase 2).
PDFJS_ZIP = "https://github.com/mozilla/pdf.js/releases/download/v4.10.38/pdfjs-4.10.38-legacy-dist.zip"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "research-hub-fetch-vendor"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main() -> int:
    failed = []
    for dest, src in FILES.items():
        path = VENDOR / dest
        if path.exists() and path.stat().st_size:
            print(f"  ok   {dest}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_bytes(fetch(NPM + src))
            print(f"  got  {dest}")
        except Exception as exc:  # report and continue
            failed.append(dest)
            print(f"  FAIL {dest}: {exc}")
    pdfjs = VENDOR / "pdfjs"
    if not (pdfjs / "web" / "viewer.html").exists():
        try:
            zipfile.ZipFile(io.BytesIO(fetch(PDFJS_ZIP))).extractall(pdfjs)
            print("  got  pdfjs/")
        except Exception as exc:
            failed.append("pdfjs")
            print(f"  FAIL pdfjs: {exc}")
    else:
        print("  ok   pdfjs/")
    if failed:
        print(f"\n{len(failed)} download(s) failed; re-run when online.")
        return 1
    print("\nAll front-end libraries are in static/vendor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
