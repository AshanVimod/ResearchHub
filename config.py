"""Paths, defaults and feature flags for Research Hub."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# RESEARCH_HUB_DATA lets you point a second copy (a demo, a test run) at another folder.
DATA_DIR = Path(os.environ.get("RESEARCH_HUB_DATA") or BASE_DIR / "data")
DB_PATH = DATA_DIR / "research.db"
LIBRARY_DIR = DATA_DIR / "library"
EXPORTS_DIR = DATA_DIR / "exports"
LOG_PATH = DATA_DIR / "app.log"
SECRET_KEY_PATH = DATA_DIR / "secret_key"
FALLBACK_BACKUP_DIR = BASE_DIR / "backups"
MIGRATIONS_DIR = BASE_DIR / "hub" / "migrations"

# Author credit shown in the sidebar and on Settings -> About.
AUTHOR = {
    "name": "Vimod R.A",
    "whatsapp": "0717869097",
    "whatsapp_link": "https://wa.me/94717869097",
    "email": "ashanvimod01@gmail.com",
    "year": 2026,
    "wish": "Wishing you a focused, calm and successful research journey. Good luck with your viva!",
}

HOST = "127.0.0.1"
PORT = int(os.environ.get("RESEARCH_HUB_PORT") or 8000)
TOTAL_WEEKS = 34

TIME_CATEGORIES = ["reading", "coding", "data", "writing", "meeting",
                   "experiments", "presentation", "admin"]

# Key -> default value. Lists are stored newline-separated.
DEFAULT_SETTINGS = {
    "project_title": "",
    "student_name": "",
    "reg_no": "",
    "supervisor_name": "",
    "project_start_date": "",
    "semester1_start": "",
    "semester1_end": "",
    "semester2_start": "",
    "semester2_end": "",
    "research_roots": "",
    "thesis_docx_path": "",
    "backup_dir": "",
    "backups_to_keep": "10",
    "hours_target": "400",
    "meeting_gap_days": "14",
    "signed_meetings_per_semester": "5",
    "crossref_mailto": "",
    "index_exclude_globs": "\n".join([".git", ".idea", "__pycache__", "node_modules",
                                      ".venv", "*.tmp", "~$*"]),
    "index_max_text_mb": "5",
    "semantic_search_enabled": "false",
}

# Settings shown on /settings, grouped. (key, label, input type, help)
SETTINGS_FORM = [
    ("Project", [
        ("project_title", "Project title", "text", "Shown in the header and on exports."),
        ("student_name", "Student name", "text", ""),
        ("reg_no", "Registration no.", "text", ""),
        ("supervisor_name", "Supervisor", "text", "Default attendee for diary entries."),
        ("project_start_date", "Project start date", "date", "Required. Week numbers and milestone dates are computed from it."),
    ]),
    ("Semesters", [
        ("semester1_start", "Semester 1 start", "date", ""),
        ("semester1_end", "Semester 1 end", "date", ""),
        ("semester2_start", "Semester 2 start", "date", ""),
        ("semester2_end", "Semester 2 end", "date", ""),
    ]),
    ("Targets and reminders", [
        ("hours_target", "Hours target", "number", "Guideline minimum is 400 hours."),
        ("meeting_gap_days", "Meeting gap alert (days)", "number", "Red alert when no meeting for this long."),
        ("signed_meetings_per_semester", "Signed meetings per semester", "number", ""),
    ]),
    ("Files and backup", [
        ("research_roots", "Research folders", "textarea", "One folder per line, e.g. C:\\Users\\you\\Documents\\Research. Read-only: the app never changes these files."),
        ("thesis_docx_path", "Thesis .docx path", "text", "Your thesis Word file; the Thesis page counts its words per chapter."),
        ("backup_dir", "Backup folder", "text", "For example a OneDrive folder. Empty = the backups folder next to the app."),
        ("backups_to_keep", "Backups to keep", "number", ""),
        ("index_exclude_globs", "Indexer excludes", "textarea", "One pattern per line."),
        ("index_max_text_mb", "Max text file size (MB)", "number", ""),
    ]),
    ("Integrations", [
        ("crossref_mailto", "Crossref contact e-mail", "email", "Optional; sent with DOI lookups as polite-pool contact."),
        ("semantic_search_enabled", "Semantic search", "bool", "Search by meaning. Needs the optional packages in requirements-semantic.txt (see the guide)."),
    ]),
]
