"""Research Hub entry point: create_app() and the local server."""
import logging
import mimetypes
import secrets
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler

from flask import Flask, redirect, render_template, request, url_for

import config
from hub import db, util
from hub.services import backup, experiments, indexer, labels, semantic, thesis, timeline, viva
from hub.services import settings as st

# Windows' registry often maps .mjs to text/plain, which browsers refuse to run as a module (PDF.js).
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")


def _secret_key() -> str:
    path = config.SECRET_KEY_PATH
    if not path.exists():
        path.write_text(secrets.token_hex(32), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def _logging(app):
    handler = RotatingFileHandler(config.LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)


def init_db(app):
    conn = db.connect(app.config["DB_PATH"])
    try:
        db.migrate(conn, config.MIGRATIONS_DIR)
        st.seed_defaults(conn)
        s = st.get_all(conn)
        timeline.seed_milestones(conn, st.as_date(s, "project_start_date"))
        indexer.mark_stale_jobs(conn)
        thesis.seed(conn)
        viva.seed(conn)
        labels.ensure_rules(conn)
        imported = experiments.import_pending(conn, config.BASE_DIR / "experiments_pending.jsonl", datetime.now())
        if imported:
            app.logger.info("Imported %d queued experiment run(s)", imported)
    finally:
        conn.close()


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    if test_config is None:
        for d in (config.DATA_DIR, config.LIBRARY_DIR, config.EXPORTS_DIR):
            d.mkdir(parents=True, exist_ok=True)
        app.config.update(SECRET_KEY=_secret_key(), DB_PATH=config.DB_PATH, EXPORTS_DIR=config.EXPORTS_DIR,
                          LIBRARY_DIR=config.LIBRARY_DIR, MAX_CONTENT_LENGTH=200 * 1024 * 1024)
        _logging(app)
    else:
        app.config.update(test_config)

    app.teardown_appcontext(db.close_db)
    init_db(app)

    from hub.blueprints import (api, dashboard, diary, experiments, files, inbox, labels, refs, search, settings, tasks,
                                thesis, time, viva)
    for bp in (dashboard.bp, diary.bp, tasks.bp, time.bp, settings.bp, api.bp, inbox.bp, refs.bp, files.bp,
               search.bp, thesis.bp, labels.bp, experiments.bp, viva.bp):
        app.register_blueprint(bp)

    app.jinja_env.filters.update(md=util.markdown, nice_date=util.nice_date, hours=util.hours,
                                 filesize=util.filesize, timestamp=util.timestamp)

    @app.context_processor
    def globals_():
        conn = db.get_db()
        return {"csrf_token": util.csrf_token, "S": st.get_all(conn), "TIME_CATEGORIES": config.TIME_CATEGORIES,
                "today": util.today(), "AUTHOR": config.AUTHOR}

    @app.before_request
    def guards():
        util.check_csrf()
        if request.endpoint in (None, "static", "files.status", "experiments.api_create") or request.blueprint in ("settings", "api"):
            return None
        if not st.get_all(db.get_db()).get("project_start_date"):
            return redirect(url_for("settings.index", setup=1))
        return None

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(400)
    def bad_request(e):
        return render_template("errors/400.html", message=e.description), 400

    @app.errorhandler(500)
    def server_error(e):
        error_id = uuid.uuid4().hex[:8]
        app.logger.error("error_id=%s %s %s", error_id, request.path, getattr(e, "original_exception", e), exc_info=True)
        return render_template("errors/500.html", error_id=error_id), 500

    return app


def auto_backup(app):
    with app.app_context():
        conn = db.connect(app.config["DB_PATH"])
        try:
            now = util.now()
            if backup.due_for_auto(conn, now):
                path = backup.make_backup(conn, st.get_all(conn), now)
                app.logger.info("Automatic backup written to %s", path)
        except Exception:  # never block start-up on a backup problem
            app.logger.exception("Automatic backup failed")
        finally:
            conn.close()


if __name__ == "__main__":
    application = create_app()
    application.config["CAN_QUIT"] = True  # Settings -> Quit stops this process (not the test app)
    auto_backup(application)
    indexer.schedule(application.config["DB_PATH"], application.logger)
    with application.app_context():
        _conn = db.connect(application.config["DB_PATH"])
        semantic.warm_up(st.get_all(_conn), application.logger)
        _conn.close()
    print(f"Research Hub running at http://{config.HOST}:{config.PORT}  (Ctrl+C to stop)", flush=True)
    try:
        from waitress import serve
        serve(application, host=config.HOST, port=config.PORT, threads=8)
    except ImportError:
        application.run(host=config.HOST, port=config.PORT, debug=False)
