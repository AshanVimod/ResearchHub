"""Print docs/user-guide.html to Research_Hub_Guide.pdf (in the app folder) with headless Microsoft Edge."""
import subprocess
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent
SRC = DOCS / "user-guide.html"
OUT = DOCS.parent / "Research_Hub_Guide.pdf"
EDGE = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")]

edge = next((p for p in EDGE if p.exists()), None)
if not edge:
    sys.exit("Microsoft Edge not found")
subprocess.run([str(edge), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={OUT}", SRC.as_uri()], check=True, timeout=120)
print("Wrote", OUT)
