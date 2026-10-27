# Research Hub

A private, offline web app for managing a final-year research project on Windows: deadlines and a
34-week timeline, supervisor meeting diary (Word export), Kanban tasks, hours tracking, references
with IEEE bibliography, literature matrix, a read-only index and full-text search of your research
folders, thesis word counts, a dataset label tracker, an experiment log for Jupyter, and viva practice.

Everything runs on your own computer at http://127.0.0.1:8000 and is stored in the `data/` folder.
Nothing is uploaded anywhere.

**📘 Full guide: [Research_Hub_Guide.pdf](Research_Hub_Guide.pdf)** (installation, configuration, every feature, backups, troubleshooting).

## Install (Windows)

1. Install **Python 3.11 or newer** from https://www.python.org/downloads/ and tick **"Add python.exe to PATH"**.
2. Download this repository (**Code → Download ZIP**, then *Extract All*) or clone it, into a folder such as `C:\ResearchHub`:
   ```
   git clone https://github.com/AshanVimod/ResearchHub.git C:\ResearchHub
   ```
3. Double-click **`start.bat`** once. It installs everything (a few minutes), puts a **Research Hub**
   shortcut on your desktop and opens the app.

From then on, just double-click the **Research Hub** desktop shortcut. It starts the app silently in the
background and opens your browser. To stop it: **Settings → Your data → Quit Research Hub**.

## Try the demo

Double-click **`demo.bat`** to open a separate copy with a made-up sample project (port 8010, stored in
`sample-data/`). Your real data is never touched. Delete `sample-data/` to reset the demo.

## Your data

| Where | What |
|---|---|
| `data/research.db` | Everything you enter (one SQLite file) |
| `data/library/` | PDFs uploaded on the References page |
| `data/exports/` | Word, CSV, Excel and .bib exports |
| `backups/` (or the folder set in Settings) | Daily and manual backup zips |

`data/`, `backups/` and `sample-data/` are git-ignored, so your work never ends up on GitHub.
**Settings → Your data** shows the paths, sizes and record counts.

## Logging experiments from Jupyter

```python
import sys; sys.path.append(r"C:\ResearchHub\scripts")
from log_experiment import log_run
log_run(run_name="rf_baseline_v1", approach="baseline", model="RandomForest",
        params={"n_estimators": 200}, metrics={"accuracy": 0.86, "f1": 0.81})
```

## Optional: semantic ("Meaning") search

```
.venv\Scripts\pip install -r requirements-semantic.txt
```
Then turn on **Settings → Semantic search**. See the guide for details.

## Keyboard

`/` search · `Alt+N` quick capture · `Alt+T` start/stop timer · `?` all shortcuts

## Author and license

© 2026 **Vimod R.A** · WhatsApp **0717869097** · ashanvimod01@gmail.com

Released under the [MIT License](LICENSE): free to use, copy and modify; please keep the copyright notice.

*Wishing you a focused, calm and successful research journey. Good luck with your viva!*
