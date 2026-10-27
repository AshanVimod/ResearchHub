"""Fill a separate demo copy of Research Hub with made-up sample data, so you can explore every page.

Run through demo.bat, which points RESEARCH_HUB_DATA at sample-data/ so your real data/ is never touched.
Everything here is fictional: the project, people, references, files, labels and experiment runs.
Running it again does nothing once the sample project exists.
"""
import os
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if not os.environ.get("RESEARCH_HUB_DATA"):
    sys.exit("Run this through demo.bat (it sets RESEARCH_HUB_DATA so your real data folder is not used).")

import config  # noqa: E402
from app import create_app  # noqa: E402
from hub import db  # noqa: E402
from hub.services import diary, experiments, labels, refs, tasks, timeline, timer  # noqa: E402
from hub.services import settings as st  # noqa: E402

RESEARCH = config.DATA_DIR / "Sample research folder"
TITLE = "Sample project: Forecasting Urban Air Quality with Low-Cost Sensors"


def make_files():
    """A small fake research folder: two PDFs (one duplicated), notes and a CSV."""
    import pymupdf
    (RESEARCH / "Papers").mkdir(parents=True, exist_ok=True)
    (RESEARCH / "Notes").mkdir(exist_ok=True)
    (RESEARCH / "Data").mkdir(exist_ok=True)
    papers = {
        "Example2021 - Calibrating low-cost PM2.5 sensors.pdf": [
            "Calibrating low-cost PM2.5 sensors (sample paper, fictional)",
            "Low-cost particulate sensors drift with humidity. We compare linear calibration with random forests.",
            "Random forest calibration reduced error by a third. Humidity was the most important feature."],
        "Sample2023 - Short-term air quality forecasting.pdf": [
            "Short-term air quality forecasting with gradient boosting (sample paper, fictional)",
            "We forecast next-day PM2.5 from sensor history, weather and traffic counts.",
            "Gradient boosting beat persistence baselines. Missing data was handled by interpolation."],
    }
    for name, pages in papers.items():
        doc = pymupdf.open()
        for text in pages:
            doc.new_page().insert_textbox(pymupdf.Rect(72, 72, 520, 760), text, fontsize=12)
        doc.save(RESEARCH / "Papers" / name)
        doc.close()
    copy = RESEARCH / "Papers" / "Example2021 - Calibrating low-cost PM2.5 sensors (copy).pdf"
    copy.write_bytes((RESEARCH / "Papers" / "Example2021 - Calibrating low-cost PM2.5 sensors.pdf").read_bytes())
    (RESEARCH / "Notes" / "reading-notes.md").write_text(
        "# Reading notes (sample)\n\n- Humidity correction matters for low-cost sensors.\n"
        "- Try a persistence baseline before any machine learning model.\n", encoding="utf-8")
    (RESEARCH / "Notes" / "meeting-prep.txt").write_text(
        "Questions for the supervisor: which stations to use for validation? How many weeks of data are enough?\n",
        encoding="utf-8")
    rows = ["timestamp,station,pm25,humidity,temperature"]
    rng = random.Random(7)
    for h in range(48):
        for s in ("A", "B"):
            rows.append(f"2025-03-01T{h % 24:02d}:00,Station {s},{rng.uniform(8, 60):.1f},{rng.uniform(40, 95):.0f},"
                        f"{rng.uniform(22, 33):.1f}")
    (RESEARCH / "Data" / "sensor_readings_sample.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main():
    create_app()  # creates the database and runs migrations in the demo folder
    conn = db.connect(config.DB_PATH)
    if conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]:
        print("Sample data already loaded.")
        return
    today = date.today()
    now = datetime.now().replace(microsecond=0)
    start = today - timedelta(weeks=9, days=today.weekday())
    make_files()

    st.save(conn, {
        "project_title": TITLE, "student_name": "Sample Student", "reg_no": "SAMPLE/001",
        "supervisor_name": "Dr. Example Supervisor", "project_start_date": start.isoformat(),
        "semester1_start": start.isoformat(), "semester1_end": (start + timedelta(weeks=17)).isoformat(),
        "semester2_start": (start + timedelta(weeks=19)).isoformat(),
        "semester2_end": (start + timedelta(weeks=34)).isoformat(),
        "research_roots": str(RESEARCH),
    })
    timeline.recompute_due_dates(conn, start)
    s = st.get_all(conn)

    # References (fictional) with literature-matrix columns.
    sample_refs = [
        dict(title="Calibrating low-cost PM2.5 sensors with machine learning", year=2021, container="Journal of Sample Studies",
             volume="12", issue="3", pages="101-115", authors=[{"given": "Alex", "family": "Example"}, {"given": "Sam", "family": "Placeholder"}],
             status="cited", rating=5, lm_country="Example City", lm_dataset="12 sensors, 1 year", lm_method="Random forest",
             lm_metrics="RMSE, R2", lm_key_result="RF cut error by a third", lm_limitations="One city only", lm_relevance="High",
             notes="Key paper for the calibration step."),
        dict(title="Short-term air quality forecasting with gradient boosting", year=2023, container="Proceedings of the Sample Conference",
             ref_type="conference", pages="45-52", authors=[{"given": "Jordan", "family": "Sample"}],
             status="read", rating=4, lm_country="Sampleland", lm_dataset="Government monitors", lm_method="XGBoost",
             lm_metrics="MAE", lm_key_result="Beats persistence by 18%", lm_limitations="No sensor data", lm_relevance="High"),
        dict(title="A survey of missing-data handling for environmental time series", year=2020, container="Example Reviews",
             volume="4", pages="1-30", authors=[{"given": "Riley", "family": "Dummy"}, {"given": "Casey", "family": "Mock"}],
             status="reading", rating=3, lm_method="Survey", lm_relevance="Medium"),
        dict(title="Deep learning for urban pollution mapping", year=2024, container="arXiv", ref_type="preprint",
             arxiv_id="2401.00001", authors=[{"given": "Taylor", "family": "Fictional"}], status="to_read",
             lm_method="CNN + LSTM", lm_relevance="Medium"),
    ]
    ref_ids = [refs.save(conn, r) for r in sample_refs]

    # Supervisor diary: three meetings, two signed; action rows become tasks.
    meetings = [
        (start + timedelta(weeks=1, days=2), True, "Agree the topic and scope", "Chose air-quality forecasting with low-cost sensors.",
         [("Write a one-page outline", (start + timedelta(weeks=2)).isoformat())]),
        (start + timedelta(weeks=4, days=2), True, "Review the proposal draft", "Narrow the study to two stations.",
         [("Collect three months of sensor data", (start + timedelta(weeks=8)).isoformat()), ("Read the calibration papers", "")]),
        (start + timedelta(weeks=8, days=2), False, "Discuss the first baseline results", "Persistence baseline is strong; try gradient boosting.",
         [("Train a gradient boosting model", (today + timedelta(days=10)).isoformat())]),
    ]
    for d, signed, agenda, discussion, actions in meetings:
        eid, _, _ = diary.save_entry(conn, {"meeting_date": d.isoformat(), "mode": "in_person", "attendees": s["supervisor_name"],
                                            "agenda": agenda, "discussion": discussion,
                                            "reflection": "Useful meeting; clear next steps."}, actions, s)
        if signed:
            with conn:
                conn.execute("UPDATE diary_entries SET signed = 1, signed_date = ? WHERE id = ?", (d.isoformat(), eid))
    refs.link(conn, "diary", 2, "ref", ref_ids[0])

    # Extra tasks across the board.
    tasks.save(conn, {"title": "Clean the sensor CSV and fix time zones", "priority": 1, "due_date": (today + timedelta(days=3)).isoformat()}, now, status="doing")
    tasks.save(conn, {"title": "Draft the literature review outline", "priority": 2, "due_date": (today + timedelta(days=14)).isoformat()}, now)
    tasks.save(conn, {"title": "Book the next supervisor meeting", "priority": 2}, now, status="done")
    with conn:
        conn.execute("UPDATE tasks SET status = 'done', completed_at = ? WHERE title = 'Write a one-page outline'", (now.isoformat(),))

    # About 60 hours of logged time over the past weeks.
    rng = random.Random(42)
    cats = ["reading", "coding", "data", "writing", "meeting", "experiments"]
    for i in range((today - start).days):
        day = start + timedelta(days=i)
        if day.weekday() < 5 and rng.random() < 0.7:
            timer.add_manual(conn, day, rng.choice([45, 60, 90, 120]), rng.choice(cats), note="Sample entry")

    # Dataset labels: entity x period x source.
    labels.ensure_rules(conn)
    version = labels.current_rules(conn)["version"]
    for entity, code, group, period, source, lab, strength in [
        ("Station A", "ST-A", "Urban", "2024", "PRIMARY", 1, "strong"),
        ("Station A", "ST-A", "Urban", "2025", "PRIMARY", 0, ""),
        ("Station B", "ST-B", "Suburban", "2024", "PUBLISHED", 1, "moderate"),
        ("Station B", "ST-B", "Suburban", "2024", "EXPERT", 0, "weak"),
        ("Station C", "ST-C", "Rural", "2024", "RULE", 1, "not_counted"),
    ]:
        values, errors = labels.clean({"entity": entity, "entity_code": code, "entity_group": group, "period": period,
                                       "source": source, "label": str(lab), "evidence_strength": strength,
                                       "notes": "Sample row"}, version)
        assert not errors, errors
        labels.save(conn, values)

    # Experiment runs.
    for name, approach, model, params, metrics, star in [
        ("persistence_v1", "baseline", "Persistence", {}, {"accuracy": 0.71, "f1": 0.64}, False),
        ("rf_baseline_v1", "baseline", "RandomForest", {"n_estimators": 200}, {"accuracy": 0.82, "f1": 0.77}, False),
        ("xgb_proposed_v2", "proposed", "XGBoost", {"max_depth": 4, "eta": 0.1}, {"accuracy": 0.86, "f1": 0.81}, True),
        ("xgb_no_humidity", "ablation", "XGBoost", {"max_depth": 4}, {"accuracy": 0.80, "f1": 0.74}, False),
    ]:
        experiments.save(conn, experiments.clean({"run_name": name, "approach": approach, "model": model, "params": params,
                                                  "metrics": metrics, "starred": star, "data_version": "sample-v1",
                                                  "split_desc": "Time-based 80/20"}, now))

    # Viva questions and inbox ideas.
    with conn:
        conn.executemany("INSERT INTO viva_questions (question, answer, category, confidence) VALUES (?, ?, ?, ?)", [
            ("Why did you choose low-cost sensors?", "They give dense coverage at a fraction of the cost.", "method", 3),
            ("How did you handle missing readings?", "Linear interpolation for gaps under 3 hours; longer gaps dropped.", "data", 2),
            ("What is the main limitation?", "Only two stations in one city.", "results", 1),
        ])
        conn.executemany("INSERT INTO inbox (text) VALUES (?)", [
            ("Idea: add traffic counts as a feature",), ("Ask the librarian about thesis formatting",),
            ("Check if the sensor vendor publishes calibration data",)])
        conn.execute("UPDATE chapters SET status = 'drafting' WHERE ordinal IN (1, 2)")
    conn.close()
    print(f"Sample data loaded into {config.DATA_DIR}")


if __name__ == "__main__":
    main()
