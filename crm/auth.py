import datetime as dt
import functools
import hashlib
import hmac
import re
import secrets
import time

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from . import constants as C
from .db import execute, query
from .util import clean, parse_date, parse_float, safe_next

bp = Blueprint("auth", __name__)

INVITE_DAYS = 14
MIN_PASSWORD = 8
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Простая защита от перебора паролей: не больше 10 ошибок за 15 минут с одного IP
_FAILS = {}
FAIL_LIMIT, FAIL_WINDOW = 10, 15 * 60


def _too_many_fails(ip):
    now = time.time()
    lst = [t for t in _FAILS.get(ip, []) if now - t < FAIL_WINDOW]
    _FAILS[ip] = lst
    return len(lst) >= FAIL_LIMIT


def _register_fail(ip):
    _FAILS.setdefault(ip, []).append(time.time())


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _pw_version(user):
    return hashlib.sha256((user["password_hash"] or "").encode()).hexdigest()[:16]


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def login_user(user):
    session.clear()
    session.permanent = True
    session["uid"] = user["id"]
    session["pwv"] = _pw_version(user)
    session["csrf"] = secrets.token_urlsafe(32)      # новый токен после входа
    execute("UPDATE persons SET last_login = datetime('now') WHERE id = ?", (user["id"],))


@bp.before_app_request
def load_user_and_check():
    g.user = None
    uid = session.get("uid")
    if uid:
        u = query("SELECT * FROM persons WHERE id = ? AND active = 1 AND password_hash IS NOT NULL",
                  (uid,), one=True)
        if u and hmac.compare_digest(session.get("pwv", ""), _pw_version(u)):
            g.user = u
        else:
            session.pop("uid", None)

    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        if not session.get("csrf") or not hmac.compare_digest(sent, session["csrf"]):
            abort(400, "Форма устарела. Обновите страницу и попробуйте ещё раз.")

    # Пока нет ни одного администратора — отправляем на первичную настройку
    if request.endpoint not in ("auth.setup", "static") and \
            query("SELECT 1 FROM persons WHERE is_admin = 1 LIMIT 1", one=True) is None:
        return redirect(url_for("auth.setup"))


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(**kwargs)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    @login_required
    def wrapped(**kwargs):
        if not g.user["is_admin"]:
            abort(403)
        return view(**kwargs)
    return wrapped


def _validate_password(pw, pw2):
    if len(pw) < MIN_PASSWORD:
        return f"Пароль должен быть не короче {MIN_PASSWORD} символов."
    if pw != pw2:
        return "Пароли не совпадают."
    return None


def _validate_email(email, exclude_id=None):
    if not email or not EMAIL_RE.match(email):
        return "Укажите корректный e-mail."
    other = query("SELECT id FROM persons WHERE email = ?", (email,), one=True)
    if other and other["id"] != exclude_id:
        return "Этот e-mail уже используется другим кабинетом."
    return None


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if query("SELECT 1 FROM persons WHERE is_admin = 1 LIMIT 1", one=True):
        return redirect(url_for("main.dashboard"))
    form = request.form
    if request.method == "POST":
        email = (form.get("email") or "").strip().lower()
        err = (None if clean(form.get("first_name")) and clean(form.get("last_name"))
               else "Укажите имя и фамилию.")
        err = err or _validate_email(email) or _validate_password(form.get("password", ""),
                                                                  form.get("password2", ""))
        stufe = form.get("stufe") if form.get("stufe") in C.STUFE_CODES else "VM"
        if err:
            flash(err, "error")
        else:
            pid = execute(
                """INSERT INTO persons (first_name, last_name, email, stufe, coef, phone,
                                        is_admin, password_hash, start_date)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (clean(form.get("first_name"), 80), clean(form.get("last_name"), 80), email, stufe,
                 parse_float(form.get("coef")), clean(form.get("phone"), 40),
                 generate_password_hash(form["password"]), dt.date.today().isoformat()))
            login_user(query("SELECT * FROM persons WHERE id = ?", (pid,), one=True))
            flash("Кабинет администратора создан. Добавьте людей в структуру.", "ok")
            return redirect(url_for("main.team"))
    return render_template("auth/setup.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("main.dashboard"))
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    if request.method == "POST":
        if _too_many_fails(ip):
            flash("Слишком много неудачных попыток. Подождите 15 минут.", "error")
            return render_template("auth/login.html"), 429
        email = (request.form.get("email") or "").strip().lower()
        user = query("SELECT * FROM persons WHERE email = ? AND active = 1", (email,), one=True)
        if user and user["password_hash"] and check_password_hash(user["password_hash"],
                                                                   request.form.get("password", "")):
            login_user(user)
            return redirect(safe_next(url_for("main.dashboard")))
        _register_fail(ip)
        flash("Неверный e-mail или пароль.", "error")
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


def create_invite(person_id):
    """Создаёт новую ссылку-приглашение. Старая ссылка перестаёт работать."""
    token = secrets.token_urlsafe(24)
    expires = (dt.datetime.now() + dt.timedelta(days=INVITE_DAYS)).isoformat(timespec="minutes")
    execute("UPDATE persons SET invite_hash = ?, invite_expires = ? WHERE id = ?",
            (hash_token(token), expires, person_id))
    return url_for("auth.accept_invite", token=token, _external=True), expires


@bp.route("/invite/<token>", methods=["GET", "POST"])
def accept_invite(token):
    person = query("SELECT * FROM persons WHERE invite_hash = ? AND active = 1",
                   (hash_token(token),), one=True)
    if not person or (person["invite_expires"] or "") < dt.datetime.now().isoformat(timespec="minutes"):
        return render_template("auth/invite_invalid.html"), 404
    form = request.form
    if request.method == "POST":
        email = (form.get("email") or "").strip().lower()
        err = _validate_email(email, exclude_id=person["id"]) or \
            _validate_password(form.get("password", ""), form.get("password2", ""))
        if err:
            flash(err, "error")
        else:
            execute("""UPDATE persons SET email = ?, password_hash = ?, invite_hash = NULL,
                       invite_expires = NULL, phone = COALESCE(?, phone),
                       birth_date = COALESCE(?, birth_date) WHERE id = ?""",
                    (email, generate_password_hash(form["password"]), clean(form.get("phone"), 40),
                     (parse_date(form.get("birth_date")) or None) and form.get("birth_date"),
                     person["id"]))
            login_user(query("SELECT * FROM persons WHERE id = ?", (person["id"],), one=True))
            flash("Добро пожаловать! Кабинет готов.", "ok")
            return redirect(url_for("main.dashboard"))
    return render_template("auth/invite.html", person=person, form=form)


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    u = g.user
    form = request.form
    if request.method == "POST":
        action = form.get("action")
        if action == "profile":
            email = (form.get("email") or "").strip().lower()
            err = _validate_email(email, exclude_id=u["id"])
            bd = form.get("birth_date")
            if bd and not parse_date(bd):
                err = err or "Дата рождения в неверном формате."
            if err:
                flash(err, "error")
            else:
                execute("UPDATE persons SET email = ?, phone = ?, birth_date = ? WHERE id = ?",
                        (email, clean(form.get("phone"), 40), parse_date(bd) and bd, u["id"]))
                flash("Данные сохранены.", "ok")
                return redirect(url_for("auth.account"))
        elif action == "password":
            if not check_password_hash(u["password_hash"], form.get("current", "")):
                flash("Текущий пароль указан неверно.", "error")
            else:
                err = _validate_password(form.get("password", ""), form.get("password2", ""))
                if err:
                    flash(err, "error")
                else:
                    execute("UPDATE persons SET password_hash = ? WHERE id = ?",
                            (generate_password_hash(form["password"]), u["id"]))
                    login_user(query("SELECT * FROM persons WHERE id = ?", (u["id"],), one=True))
                    flash("Пароль изменён.", "ok")
                    return redirect(url_for("auth.account"))
    return render_template("account.html", form=form)
