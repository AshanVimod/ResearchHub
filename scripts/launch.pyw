"""Open Research Hub from a desktop shortcut: start the server silently if needed, then open the browser.

Run with pythonw.exe (no console window). The server keeps running in the background until you press
Settings -> Quit Research Hub, sign out, or shut down. Its output goes to data/server.log.
"""
import ctypes
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402  (port and data folder, honouring RESEARCH_HUB_* overrides)

URL = f"http://{config.HOST}:{config.PORT}"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


def message(text: str, error: bool = True):
    ctypes.windll.user32.MessageBoxW(None, text, "Research Hub", 0x10 if error else 0x40)


def running() -> bool:
    """True when Research Hub (not some other program) answers on the port."""
    try:
        with urllib.request.urlopen(URL + "/api/timer", timeout=1) as r:
            return r.status == 200 and b"running" in r.read()
    except OSError:
        return False


def start_server() -> bool:
    if not PYTHON.exists():
        message("Research Hub is not installed yet.\n\nDouble-click start.bat in\n"
                f"{ROOT}\nonce; it sets everything up. After that this shortcut works on its own.")
        return False
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    log = open(config.DATA_DIR / "server.log", "ab")
    subprocess.Popen([str(PYTHON), str(ROOT / "app.py")], cwd=str(ROOT), stdin=subprocess.DEVNULL,
                     stdout=log, stderr=subprocess.STDOUT, close_fds=True,
                     creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP)
    for _ in range(60):  # up to 30 s; the first start also creates the database
        time.sleep(0.5)
        if running():
            return True
    message(f"Research Hub did not start within 30 seconds.\n\nSee the log for details:\n{config.DATA_DIR / 'server.log'}")
    return False


if __name__ == "__main__":
    if running() or start_server():
        webbrowser.open(URL)
