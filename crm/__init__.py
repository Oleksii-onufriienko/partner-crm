import datetime as dt
import os
import secrets

from flask import Flask, render_template

__version__ = "0.1.0"


def _secret_key(instance_path):
    env = os.environ.get("CRM_SECRET_KEY")
    if env:
        return env
    path = os.path.join(instance_path, "secret_key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True,
                instance_path=os.environ.get("CRM_INSTANCE") or None)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.update(
        SECRET_KEY=_secret_key(app.instance_path),
        DATABASE=os.environ.get("CRM_DB") or os.path.join(app.instance_path, "crm.sqlite3"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("CRM_SECURE_COOKIES") == "1",
        PERMANENT_SESSION_LIFETIME=dt.timedelta(days=14),
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
    )
    if os.environ.get("CRM_BEHIND_PROXY") == "1":
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    if test_config:
        app.config.update(test_config)

    from . import db
    db.init_app(app)

    from . import auth, main
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)

    from . import constants as C
    from . import util as U
    app.jinja_env.globals.update(
        C=C, csrf_token=auth.csrf_token, plural=U.plural, today=U.today, version=__version__,
        WEEKDAYS=U.WEEKDAYS, safe_next=U.safe_next,
        month_name=lambda d: f"{U.MONTHS_NOM[d.month - 1].capitalize()} {d.year}")
    app.jinja_env.filters.update(
        d=U.fmt_date, num=U.fmt_num, eur=U.fmt_eur, label=lambda k, opts: C.label(opts, k),
        age=U.age_from,
        stage_short=lambda k: next((s[2] for s in C.STAGES if s[0] == k), k))
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    @app.template_filter("fullname")
    def fullname(p):
        if p is None:
            return ""
        return f"{p['first_name']} {p['last_name'] or ''}".strip()

    @app.template_filter("initials")
    def initials(p):
        return ((p["first_name"] or " ")[0] + ((p["last_name"] or " ")[0])).strip().upper()

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    def _error(code, title, text):
        def handler(e):
            msg = getattr(e, "description", None) if code == 400 else None
            return render_template("error.html", code=code, title=title, text=msg or text), code
        return handler

    app.register_error_handler(400, _error(400, "Запрос не принят", "Обновите страницу и попробуйте ещё раз."))
    app.register_error_handler(403, _error(403, "Нет доступа", "У вас нет прав на это действие."))
    app.register_error_handler(404, _error(404, "Не найдено",
                                           "Такой страницы нет, или она относится к чужой структуре."))
    return app
