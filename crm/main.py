import datetime as dt

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   session, url_for)

from . import constants as C
from . import plan as P
from . import stats as S
from .access import (branch_ids, can_manage, children_map, direct_children, get_person,
                     has_team, person_options, tree_rows, visible_ids, visible_persons)
from .auth import admin_required, create_invite, login_required
from .db import execute, query
from .util import (clean, month_bounds, monday, parse_date, parse_float, parse_int,
                   safe_next, today)

bp = Blueprint("main", __name__)


# ---------------------------------------------------------------- helpers

def _pid_arg(name="person"):
    pid = parse_int(request.values.get(name))
    return pid if pid is not None else g.user["id"]


def get_contact(cid):
    c = query("SELECT * FROM contacts WHERE id = ?", (cid,), one=True)
    if c is None or c["owner_id"] not in visible_ids():
        abort(404)
    return c


def get_meeting(mid):
    m = query("SELECT * FROM meetings WHERE id = ?", (mid,), one=True)
    if m is None or m["owner_id"] not in visible_ids():
        abort(404)
    return m


def _choice(value, options, default):
    return value if value in C.keys(options) else default


# ---------------------------------------------------------------- сегодня

@bp.route("/")
@login_required
def dashboard():
    me = g.user
    t = today()
    ms, me_ = month_bounds(t)
    metrics = S.compute([me], ms, me_)[me["id"]]

    today_meetings = query(
        """SELECT m.*, c.first_name cf, c.last_name cl, c.phone cphone FROM meetings m
           LEFT JOIN contacts c ON c.id = m.contact_id
           WHERE m.owner_id = ? AND m.date = ? ORDER BY COALESCE(m.time, '99')""",
        (me["id"], t.isoformat()))
    upcoming = query(
        """SELECT m.*, c.first_name cf, c.last_name cl FROM meetings m
           LEFT JOIN contacts c ON c.id = m.contact_id
           WHERE m.owner_id = ? AND m.date BETWEEN ? AND ? AND m.status = 'planned'
           ORDER BY m.date, COALESCE(m.time, '99') LIMIT 12""",
        (me["id"], (t + dt.timedelta(days=1)).isoformat(), (t + dt.timedelta(days=7)).isoformat()))
    stale = query(
        """SELECT m.*, c.first_name cf, c.last_name cl FROM meetings m
           LEFT JOIN contacts c ON c.id = m.contact_id
           WHERE m.owner_id = ? AND m.date < ? AND m.status = 'planned' AND m.format != 'private'
           ORDER BY m.date DESC LIMIT 10""", (me["id"], t.isoformat()))
    followups = query(
        """SELECT * FROM contacts WHERE owner_id = ? AND next_action_date IS NOT NULL
           AND next_action_date <= ? AND status != 'no_chance'
           ORDER BY next_action_date LIMIT 15""",
        (me["id"], (t + dt.timedelta(days=3)).isoformat()))

    # Команда: прямые партнёры, итог по их веткам за месяц
    team = []
    kids = direct_children(me["id"])
    if kids:
        all_ids = [i for k in kids for i in branch_ids(k["id"])]
        vp = visible_persons()
        per = S.compute([vp[i] for i in all_ids], ms, me_)
        sig = S.signals([vp[i] for i in all_ids])
        for k in kids:
            b = branch_ids(k["id"])
            team.append({"p": k, "m": S.combine(per[i] for i in b),
                         "signals": sig.get(k["id"], []), "size": len(b)})

    # Дни рождения в структуре на ближайшие 14 дней
    birthdays = []
    for p in visible_persons().values():
        bd = parse_date(p["birth_date"])
        if not bd or p["id"] == me["id"] or not p["active"]:
            continue
        for year in (t.year, t.year + 1):
            try:
                nxt = bd.replace(year=year)
            except ValueError:            # 29 февраля
                nxt = dt.date(year, 3, 1)
            if 0 <= (nxt - t).days <= 14:
                birthdays.append({"p": p, "date": nxt, "age": year - bd.year})
                break
    birthdays.sort(key=lambda x: x["date"])

    wk = [monday(t)]
    week_grid = P.grids([me["id"]], wk)[me["id"]]
    week_view = P.view(week_grid, wk)
    has_week_plan = any(c["soll"] is not None for c in week_grid[wk[0].isoformat()].values())

    return render_template("dashboard.html", m=metrics, today_meetings=today_meetings,
                           week_summary=week_view["summary"], has_week_plan=has_week_plan,
                           upcoming=upcoming, stale=stale, followups=followups, team=team,
                           birthdays=birthdays, month_label=S.period_from_args({})[3])


# ---------------------------------------------------------------- структура

@bp.route("/team")
@login_required
def team():
    t = today()
    ms, me_ = month_bounds(t)
    rows = tree_rows()
    show_inactive = request.args.get("all") == "1"
    if not show_inactive:
        rows = [(p, d) for p, d in rows if p["active"]]
    per = S.compute([p for p, _ in rows], ms, me_)
    sig = S.signals([p for p, _ in rows])
    cmap = children_map()
    return render_template("team.html", rows=rows, per=per, sig=sig, cmap=cmap,
                           show_inactive=show_inactive)


def _person_form_data(form, person=None):
    """Проверка формы человека. Возвращает (data, error)."""
    first, last = clean(form.get("first_name"), 80), clean(form.get("last_name"), 80)
    if not first or not last:
        return None, "Укажите имя и фамилию."
    stufe = _choice(form.get("stufe"), C.STUFEN, "VM")
    coef = parse_float(form.get("coef"))
    if coef is None and form.get("coef", "").strip() == "":
        coef = C.STUFE_DEFAULT_COEF.get(stufe)
    for fld in ("birth_date", "start_date"):
        if form.get(fld) and not parse_date(form.get(fld)):
            return None, "Дата в неверном формате."
    email = (form.get("email") or "").strip().lower() or None
    if email:
        other = query("SELECT id FROM persons WHERE email = ?", (email,), one=True)
        if other and (person is None or other["id"] != person["id"]):
            return None, "Этот e-mail уже используется другим кабинетом."

    parent_raw = form.get("parent_id", "")
    parent_id = parse_int(parent_raw)
    if parent_id is None:
        if not g.user["is_admin"]:
            return None, "Выберите наставника."
    else:
        if parent_id not in visible_ids():
            return None, "Наставник не найден."
        if person is not None and parent_id in branch_ids(person["id"]):
            return None, "Нельзя поставить человека под его же партнёра."
    data = {
        "first_name": first, "last_name": last, "stufe": stufe, "coef": coef,
        "birth_date": (parse_date(form.get("birth_date")) or None) and form.get("birth_date"),
        "start_date": (parse_date(form.get("start_date")) or None) and form.get("start_date"),
        "phone": clean(form.get("phone"), 40), "email": email,
        "goal_ke_month": parse_float(form.get("goal_ke_month")),
        "note": clean(form.get("note"), 2000), "parent_id": parent_id,
    }
    if g.user["is_admin"]:
        data["is_admin"] = 1 if form.get("is_admin") else 0
    return data, None


@bp.route("/people/new", methods=["GET", "POST"])
@login_required
def person_new():
    form = request.form
    if request.method == "POST":
        data, err = _person_form_data(form)
        if err:
            flash(err, "error")
        else:
            data["created_by"] = g.user["id"]
            cols = ", ".join(data)
            pid = execute(f"INSERT INTO persons ({cols}) VALUES ({', '.join('?' * len(data))})",
                          list(data.values()))
            flash(f"{data['first_name']} {data['last_name']} добавлен(а) в структуру.", "ok")
            if form.get("invite"):
                link, exp = create_invite(pid)
                session["invite_link"] = {"pid": pid, "link": link, "expires": exp}
            return redirect(url_for("main.person", pid=pid))
    parent = parse_int(request.args.get("parent")) or g.user["id"]
    return render_template("person_form.html", person=None, form=form,
                           parent_id=parent if parent in visible_ids() else g.user["id"],
                           options=person_options())


@bp.route("/people/<int:pid>")
@login_required
def person(pid):
    p = get_person(pid)
    key, start, end, label = S.period_from_args(request.args)
    b = branch_ids(pid)
    vp = visible_persons()
    per = S.compute([vp[i] for i in b], start, end)
    own, total = per[pid], S.combine(per.values())
    sig = S.signals([p])[pid]
    invite = session.pop("invite_link", None)
    if invite and invite.get("pid") != pid:
        invite = None
    parent = vp.get(p["parent_id"]) if p["parent_id"] else None
    return render_template("person.html", p=p, own=own, total=total, sig=sig,
                           kids=direct_children(pid), branch_size=len(b), parent=parent,
                           invite=invite, manage=can_manage(p), period_label=label)


@bp.route("/people/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def person_edit(pid):
    p = get_person(pid)
    if not can_manage(p):
        return redirect(url_for("auth.account"))
    form = request.form
    if request.method == "POST":
        data, err = _person_form_data(form, person=p)
        if err:
            flash(err, "error")
        else:
            if pid == g.user["id"]:
                data.pop("is_admin", None)      # не снимаем права сами с себя
            sets = ", ".join(f"{k} = ?" for k in data)
            execute(f"UPDATE persons SET {sets} WHERE id = ?", [*data.values(), pid])
            flash("Изменения сохранены.", "ok")
            return redirect(url_for("main.person", pid=pid))
    exclude = set(branch_ids(pid))
    opts = [(o, d) for o, d in person_options() if o["id"] not in exclude]
    return render_template("person_form.html", person=p, form=form, parent_id=p["parent_id"],
                           options=opts)


@bp.route("/people/<int:pid>/invite", methods=["POST"])
@login_required
def person_invite(pid):
    p = get_person(pid)
    if not can_manage(p) or not p["active"]:
        abort(403)
    link, exp = create_invite(pid)
    session["invite_link"] = {"pid": pid, "link": link, "expires": exp}
    if p["password_hash"]:
        flash("Ссылка для смены пароля создана. Старый пароль продолжит работать, "
              "пока человек не задаст новый.", "ok")
    return redirect(url_for("main.person", pid=pid))


@bp.route("/people/<int:pid>/active", methods=["POST"])
@login_required
def person_active(pid):
    p = get_person(pid)
    if not can_manage(p) or pid == g.user["id"]:
        abort(403)
    execute("UPDATE persons SET active = ?, invite_hash = NULL WHERE id = ?",
            (0 if p["active"] else 1, pid))
    flash("Доступ закрыт, данные сохранены." if p["active"] else "Человек снова активен.", "ok")
    return redirect(url_for("main.person", pid=pid))


@bp.route("/people/<int:pid>/delete", methods=["POST"])
@login_required
def person_delete(pid):
    p = get_person(pid)
    if not can_manage(p) or pid == g.user["id"]:
        abort(403)
    busy = query("""SELECT (SELECT COUNT(*) FROM persons WHERE parent_id = ?)
                         + (SELECT COUNT(*) FROM contacts WHERE owner_id = ?)
                         + (SELECT COUNT(*) FROM meetings WHERE owner_id = ?) n""",
                 (pid, pid, pid), one=True)["n"]
    if busy:
        flash("У человека есть партнёры, контакты или встречи. Удалить нельзя — "
              "закройте доступ кнопкой «Деактивировать».", "error")
        return redirect(url_for("main.person", pid=pid))
    execute("DELETE FROM persons WHERE id = ?", (pid,))
    flash("Удалено.", "ok")
    return redirect(url_for("main.team"))


# ---------------------------------------------------------------- Marktpotenzial

CONTACT_SORTS = {
    "name": "c.last_name COLLATE NOCASE, c.first_name COLLATE NOCASE",
    "new": "c.created_at DESC",
    "next": "c.next_action_date IS NULL, c.next_action_date",
    "potential": "potential_ke DESC",
    "temp": "CASE c.temperature WHEN 'very_hot' THEN 0 WHEN 'hot' THEN 1 WHEN 'warm' THEN 2 "
            "WHEN 'lukewarm' THEN 3 ELSE 4 END, c.last_name COLLATE NOCASE",
}


@bp.route("/contacts", methods=["GET", "POST"])
@login_required
def contacts():
    pid = _pid_arg()
    owner = get_person(pid)

    if request.method == "POST":           # быстрое добавление строкой
        first = clean(request.form.get("first_name"), 80)
        if not first:
            flash("Укажите хотя бы имя.", "error")
        else:
            execute("""INSERT INTO contacts (owner_id, first_name, last_name, phone, temperature, channel)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (pid, first, clean(request.form.get("last_name"), 80),
                     clean(request.form.get("phone"), 40),
                     _choice(request.form.get("temperature"), C.TEMPERATURES, "warm"),
                     _choice(request.form.get("channel"), C.CHANNELS, "warm")))
            flash(f"{first} добавлен(а) в Marktpotenzial.", "ok")
        return redirect(safe_next(url_for("main.contacts", person=pid)))

    a = request.args
    where, args = ["c.owner_id = ?"], [pid]
    q = (a.get("q") or "").strip()
    if q:
        where.append("(c.first_name LIKE ? OR c.last_name LIKE ? OR c.phone LIKE ? "
                      "OR c.profession LIKE ? OR c.comment LIKE ?)")
        args += [f"%{q}%"] * 5
    for fld, opts in (("kind", C.KINDS), ("status", C.CONTACT_STATUSES),
                      ("temperature", C.TEMPERATURES), ("channel", C.CHANNELS)):
        if a.get(fld) in C.keys(opts):
            where.append(f"c.{fld} = ?")
            args.append(a[fld])
    if a.get("partner") == "1":
        where.append("c.partner_interest = 1")
    sort = a.get("sort") if a.get("sort") in CONTACT_SORTS else "name"
    rows = query(
        f"""SELECT c.*,
               (SELECT COALESCE(SUM(ke), 0) FROM potentials WHERE contact_id = c.id) potential_ke,
               (SELECT COALESCE(SUM(ke), 0) FROM deals WHERE contact_id = c.id) deal_ke
            FROM contacts c WHERE {' AND '.join(where)} ORDER BY {CONTACT_SORTS[sort]}""", args)
    totals = query("""SELECT COUNT(*) n, SUM(kind = 'client') clients FROM contacts
                      WHERE owner_id = ?""", (pid,), one=True)
    temps = {r["temperature"]: r["n"] for r in query(
        "SELECT temperature, COUNT(*) n FROM contacts WHERE owner_id = ? GROUP BY temperature", (pid,))}
    filtered = any(a.get(k) for k in ("q", "kind", "status", "temperature", "channel", "partner"))
    return render_template("contacts.html", owner=owner, rows=rows, totals=totals, temps=temps,
                           sort=sort, filtered=filtered, options=person_options())


CONTACT_FIELDS = ["first_name", "last_name", "phone", "email", "age", "profession", "channel",
                  "recommended_by", "temperature", "kind", "status", "partner_interest",
                  "next_action", "next_action_date", "comment"]


def _contact_form_data(form):
    first = clean(form.get("first_name"), 80)
    if not first:
        return None, "Укажите имя."
    nad = form.get("next_action_date")
    if nad and not parse_date(nad):
        return None, "Дата напоминания в неверном формате."
    owner_id = parse_int(form.get("owner_id"))
    if owner_id not in visible_ids():
        return None, "Выберите, чей это контакт."
    age = parse_int(form.get("age"))
    data = {
        "owner_id": owner_id, "first_name": first,
        "last_name": clean(form.get("last_name"), 80), "phone": clean(form.get("phone"), 40),
        "email": clean(form.get("email"), 120),
        "age": age if age is not None and 0 < age < 120 else None,
        "profession": clean(form.get("profession"), 120),
        "channel": _choice(form.get("channel"), C.CHANNELS, "warm"),
        "recommended_by": clean(form.get("recommended_by"), 120),
        "temperature": _choice(form.get("temperature"), C.TEMPERATURES, "warm"),
        "kind": _choice(form.get("kind"), C.KINDS, "prospect"),
        "status": _choice(form.get("status"), C.CONTACT_STATUSES, "new"),
        "partner_interest": 1 if form.get("partner_interest") else 0,
        "next_action": clean(form.get("next_action"), 200),
        "next_action_date": nad if parse_date(nad) else None,
        "comment": clean(form.get("comment"), 4000),
    }
    return data, None


@bp.route("/contacts/new", methods=["GET", "POST"])
@login_required
def contact_new():
    form = request.form
    if request.method == "POST":
        data, err = _contact_form_data(form)
        if err:
            flash(err, "error")
        else:
            cid = execute(f"INSERT INTO contacts ({', '.join(data)}) VALUES ({', '.join('?' * len(data))})",
                          list(data.values()))
            flash("Контакт сохранён. Теперь можно добавить потенциальные сделки.", "ok")
            return redirect(url_for("main.contact", cid=cid))
    pid = _pid_arg()
    get_person(pid)
    return render_template("contact.html", c=None, form=form, owner_id=pid, options=person_options(),
                           potentials=[], deals=[], meetings=[])


@bp.route("/contacts/<int:cid>", methods=["GET", "POST"])
@login_required
def contact(cid):
    c = get_contact(cid)
    form = request.form
    if request.method == "POST":
        data, err = _contact_form_data(form)
        if err:
            flash(err, "error")
        else:
            sets = ", ".join(f"{k} = ?" for k in data)
            execute(f"UPDATE contacts SET {sets}, updated_at = datetime('now') WHERE id = ?",
                    [*data.values(), cid])
            flash("Контакт сохранён.", "ok")
            return redirect(url_for("main.contact", cid=cid))
    potentials = query("SELECT * FROM potentials WHERE contact_id = ? ORDER BY id", (cid,))
    deals = query("SELECT * FROM deals WHERE contact_id = ? ORDER BY date DESC, id DESC", (cid,))
    meetings = query("SELECT * FROM meetings WHERE contact_id = ? ORDER BY date DESC, time DESC", (cid,))
    owner = visible_persons()[c["owner_id"]]
    return render_template("contact.html", c=c, form=form, owner_id=c["owner_id"], owner=owner,
                           options=person_options(active_only=False), potentials=potentials,
                           deals=deals, meetings=meetings, today=today())


@bp.route("/contacts/<int:cid>/delete", methods=["POST"])
@login_required
def contact_delete(cid):
    c = get_contact(cid)
    execute("DELETE FROM contacts WHERE id = ?", (cid,))
    flash(f"Контакт {c['first_name']} {c['last_name'] or ''} удалён.", "ok")
    return redirect(url_for("main.contacts", person=c["owner_id"]))


@bp.route("/contacts/<int:cid>/potentials", methods=["POST"])
@login_required
def potential_add(cid):
    get_contact(cid)
    product = clean(request.form.get("product"), 120)
    ke = parse_float(request.form.get("ke"))
    if not product:
        flash("Укажите продукт.", "error")
    else:
        execute("INSERT INTO potentials (contact_id, product, ke) VALUES (?, ?, ?)",
                (cid, product, ke or 0))
    return redirect(url_for("main.contact", cid=cid) + "#potentials")


@bp.route("/potentials/<int:item_id>/delete", methods=["POST"])
@login_required
def potential_delete(item_id):
    row = query("SELECT * FROM potentials WHERE id = ?", (item_id,), one=True) or abort(404)
    get_contact(row["contact_id"])
    execute("DELETE FROM potentials WHERE id = ?", (item_id,))
    return redirect(url_for("main.contact", cid=row["contact_id"]) + "#potentials")


@bp.route("/contacts/<int:cid>/deals", methods=["POST"])
@login_required
def deal_add(cid):
    c = get_contact(cid)
    product = clean(request.form.get("product"), 120)
    d = parse_date(request.form.get("date"))
    ke = parse_float(request.form.get("ke"))
    if not product or not d:
        flash("Укажите дату и продукт сделки.", "error")
    else:
        execute("INSERT INTO deals (contact_id, date, product, ke, note, source) VALUES (?, ?, ?, ?, ?, ?)",
                (cid, d.isoformat(), product, ke or 0, clean(request.form.get("note"), 300),
                 _choice(request.form.get("source"), C.DEAL_SOURCES, "consult")))
        # Если оформили то, что было в потенциале, — убираем из потенциала
        pot = parse_int(request.form.get("from_potential"))
        if pot:
            execute("DELETE FROM potentials WHERE id = ? AND contact_id = ?", (pot, cid))
        if c["kind"] != "client":
            execute("UPDATE contacts SET kind = 'client', updated_at = datetime('now') WHERE id = ?", (cid,))
            flash(f"{c['first_name']} теперь клиент.", "ok")
    return redirect(url_for("main.contact", cid=cid) + "#deals")


@bp.route("/deals/<int:item_id>/delete", methods=["POST"])
@login_required
def deal_delete(item_id):
    row = query("SELECT * FROM deals WHERE id = ?", (item_id,), one=True) or abort(404)
    get_contact(row["contact_id"])
    execute("DELETE FROM deals WHERE id = ?", (item_id,))
    return redirect(url_for("main.contact", cid=row["contact_id"]) + "#deals")


# ---------------------------------------------------------------- планер встреч

PLANNER_WEEKS = 6


@bp.route("/planner")
@login_required
def planner():
    pid = _pid_arg()
    p = get_person(pid)
    start = monday(parse_date(request.args.get("start")) or today())
    end = start + dt.timedelta(days=PLANNER_WEEKS * 7 - 1)
    rows = query(
        """SELECT m.*, c.first_name cf, c.last_name cl FROM meetings m
           LEFT JOIN contacts c ON c.id = m.contact_id
           WHERE m.owner_id = ? AND m.date BETWEEN ? AND ?
           ORDER BY m.date, COALESCE(m.time, '99')""",
        (pid, start.isoformat(), end.isoformat()))
    by_day = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r)
    weeks = []
    for w in range(PLANNER_WEEKS):
        days = [start + dt.timedelta(days=w * 7 + i) for i in range(7)]
        items = [m for d in days for m in by_day.get(d.isoformat(), []) if m["format"] != "private"]
        weeks.append({
            "days": days,
            "planned": sum(1 for m in items if m["status"] != "cancelled"),
            "done": sum(1 for m in items if m["status"] == "done"),
            "ke": sum((m["expected_ke"] or 0) for m in items if m["status"] != "cancelled"),
        })
    return render_template("planner.html", p=p, weeks=weeks, by_day=by_day, start=start, end=end,
                           prev=start - dt.timedelta(days=PLANNER_WEEKS * 7),
                           next=start + dt.timedelta(days=PLANNER_WEEKS * 7),
                           today=today(), options=person_options())


def _meeting_form_data(form):
    owner_id = parse_int(form.get("owner_id"))
    if owner_id not in visible_ids():
        return None, "Выберите, чья это встреча."
    d = parse_date(form.get("date"))
    if not d:
        return None, "Укажите дату встречи."
    tm = (form.get("time") or "").strip()[:5]
    if tm and not (len(tm) == 5 and tm[2] == ":" and tm[:2].isdigit() and tm[3:].isdigit()):
        return None, "Время в формате ЧЧ:ММ."
    contact_id = parse_int(form.get("contact_id"))
    if contact_id:
        c = query("SELECT owner_id FROM contacts WHERE id = ?", (contact_id,), one=True)
        if not c or c["owner_id"] != owner_id:
            return None, "Контакт должен быть из Marktpotenzial этого же человека."
    title = clean(form.get("title"), 150)
    fmt = _choice(form.get("format"), C.FORMATS, "offline")
    if not contact_id and not title:
        return None, "Выберите контакт или напишите, с кем/что за встреча."
    data = {
        "owner_id": owner_id, "contact_id": contact_id or None, "title": title,
        "date": d.isoformat(), "time": tm or None,
        "duration_min": parse_int(form.get("duration_min")),
        "format": fmt, "stage": _choice(form.get("stage"), C.STAGES, "first"),
        "status": _choice(form.get("status"), C.MEETING_STATUSES, "planned"),
        "expected_ke": parse_float(form.get("expected_ke")),
        "note": clean(form.get("note"), 2000),
    }
    return data, None


def _meeting_form_context(owner_id):
    contacts_ = query("""SELECT id, first_name, last_name, status FROM contacts WHERE owner_id = ?
                         ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE""", (owner_id,))
    return {"contacts": contacts_, "options": person_options()}


@bp.route("/meetings/new", methods=["GET", "POST"])
@login_required
def meeting_new():
    form = request.form
    if request.method == "POST":
        data, err = _meeting_form_data(form)
        if err:
            flash(err, "error")
            owner_id = parse_int(form.get("owner_id")) if parse_int(form.get("owner_id")) in visible_ids() \
                else g.user["id"]
            return render_template("meeting_form.html", m=None, form=form, owner_id=owner_id,
                                   **_meeting_form_context(owner_id))
        data["created_by"] = g.user["id"]
        execute(f"INSERT INTO meetings ({', '.join(data)}) VALUES ({', '.join('?' * len(data))})",
                list(data.values()))
        if data["contact_id"] and data["status"] == "planned":
            execute("""UPDATE contacts SET status = 'appointment', updated_at = datetime('now')
                       WHERE id = ? AND status IN ('new', 'followup')""", (data["contact_id"],))
        flash("Встреча запланирована.", "ok")
        d = parse_date(data["date"])
        return redirect(safe_next(url_for("main.planner", person=data["owner_id"],
                                          start=monday(d).isoformat())))
    owner_id = _pid_arg()
    get_person(owner_id)
    return render_template("meeting_form.html", m=None, form=request.args, owner_id=owner_id,
                           **_meeting_form_context(owner_id))


@bp.route("/meetings/<int:mid>", methods=["GET", "POST"])
@login_required
def meeting_edit(mid):
    m = get_meeting(mid)
    form = request.form
    if request.method == "POST":
        data, err = _meeting_form_data(form)
        if err:
            flash(err, "error")
        else:
            sets = ", ".join(f"{k} = ?" for k in data)
            execute(f"UPDATE meetings SET {sets} WHERE id = ?", [*data.values(), mid])
            flash("Встреча сохранена.", "ok")
            return redirect(safe_next(url_for("main.planner", person=data["owner_id"],
                                              start=monday(parse_date(data["date"])).isoformat())))
    return render_template("meeting_form.html", m=m, form=form, owner_id=m["owner_id"],
                           **_meeting_form_context(m["owner_id"]))


@bp.route("/meetings/<int:mid>/status", methods=["POST"])
@login_required
def meeting_status(mid):
    m = get_meeting(mid)
    status = _choice(request.form.get("status"), C.MEETING_STATUSES, m["status"])
    execute("UPDATE meetings SET status = ? WHERE id = ?", (status, mid))
    return redirect(safe_next(url_for("main.planner", person=m["owner_id"])))


@bp.route("/meetings/<int:mid>/delete", methods=["POST"])
@login_required
def meeting_delete(mid):
    m = get_meeting(mid)
    execute("DELETE FROM meetings WHERE id = ?", (mid,))
    flash("Встреча удалена.", "ok")
    return redirect(url_for("main.planner", person=m["owner_id"],
                            start=monday(parse_date(m["date"])).isoformat()))


# ---------------------------------------------------------------- статистика

@bp.route("/stats")
@login_required
def stats():
    pid = _pid_arg()
    p = get_person(pid)
    key, start, end, label = S.period_from_args(request.args)
    vp = visible_persons()
    b = branch_ids(pid)
    per = S.compute([vp[i] for i in b], start, end)
    own = per[pid]
    total = S.combine(per.values())
    scope = "team" if request.args.get("scope") == "team" and len(b) > 1 else "me"
    shown = total if scope == "team" else own

    partners = []
    for k in direct_children(pid):
        kb = branch_ids(k["id"])
        partners.append({"p": k, "m": S.combine(per[i] for i in kb), "own": per[k["id"]],
                         "size": len(kb)})
    partners.sort(key=lambda x: (-x["m"]["deal_ke"], -x["m"]["done"]))

    sig = S.signals([vp[i] for i in b])
    weak = [(vp[i], sig[i]) for i in b if sig.get(i) and vp[i]["active"]]

    funnel = [("Новые контакты", shown["new_contacts"])] + \
             [(C.label(C.STAGES, s), shown["stage_done"][s]) for s in C.FUNNEL_STAGES] + \
             [("Оформленные сделки", shown["deals"])]

    return render_template("stats.html", p=p, key=key, start=start, end=end, label=label,
                           own=own, total=total, shown=shown, scope=scope, partners=partners,
                           weak=weak, funnel=funnel, branch_size=len(b), periods=S.PERIODS,
                           options=person_options(), rate=S.rate)


# ---------------------------------------------------------------- план/факт по неделям

def _month_arg():
    raw = request.values.get("month") or ""
    try:
        y, m = (int(x) for x in raw.split("-")[:2])
        return dt.date(y, m, 1)
    except ValueError:
        return today().replace(day=1)


def _shift_month(d, delta):
    m = d.month - 1 + delta
    return dt.date(d.year + m // 12, m % 12 + 1, 1)


@bp.route("/plan")
@login_required
def plan():
    pid = _pid_arg()
    p = get_person(pid)
    month = _month_arg()
    weeks = P.month_weeks(month.year, month.month)
    b = branch_ids(pid)
    scope = "team" if request.args.get("scope") == "team" and len(b) > 1 else "me"
    ids = b if scope == "team" else [pid]
    vp = visible_persons()
    grids = P.grids(ids, weeks)
    combined = P.combine(grids.values(), weeks) if scope == "team" else grids[pid]
    v = P.view(combined, weeks)
    eur = P.euros(grids, vp, weeks)

    partners = []
    if scope == "team":
        for k in direct_children(pid):
            kb = branch_ids(k["id"])
            t = P.month_totals(P.combine([grids[i] for i in kb], weeks), weeks)
            partners.append({"p": k, "size": len(kb),
                             "cells": [{"soll": t[key]["soll"], "ist": t[key]["ist"],
                                        "pct": P.pct(t[key]["ist"], t[key]["soll"])}
                                       for key, _ in C.PLAN_SUMMARY]})
        own_t = P.month_totals(grids[pid], weeks)
        partners.insert(0, {"p": p, "size": 1, "own": True,
                            "cells": [{"soll": own_t[key]["soll"], "ist": own_t[key]["ist"],
                                       "pct": P.pct(own_t[key]["ist"], own_t[key]["soll"])}
                                      for key, _ in C.PLAN_SUMMARY]})

    return render_template("plan.html", p=p, month=month, weeks=weeks, v=v, eur=eur, scope=scope,
                           branch_size=len(b), partners=partners, quotas=P.quotas(v["totals"]),
                           week_label=P.week_label, prev=_shift_month(month, -1),
                           next=_shift_month(month, 1), options=person_options())


@bp.route("/plan/edit", methods=["GET", "POST"])
@login_required
def plan_edit():
    pid = _pid_arg()
    p = get_person(pid)
    month = _month_arg()
    weeks = P.month_weeks(month.year, month.month)
    back = url_for("main.plan", person=pid, month=month.strftime("%Y-%m"))
    if request.method == "POST":
        P.save(pid, weeks, request.form, g.user["id"])
        flash("План и факт сохранены.", "ok")
        return redirect(back)
    grid = P.grids([pid], weeks)[pid]
    return render_template("plan_edit.html", p=p, month=month, weeks=weeks, grid=grid,
                           week_label=P.week_label, back=back)


@bp.route("/plan/copy", methods=["POST"])
@login_required
def plan_copy():
    pid = _pid_arg()
    get_person(pid)
    month = _month_arg()
    weeks = P.month_weeks(month.year, month.month)
    n = P.copy_previous(pid, weeks, g.user["id"])
    flash("План прошлого месяца перенесён в пустые недели." if n
          else "В прошлом месяце плана нет — переносить нечего.", "ok" if n else "error")
    return redirect(url_for("main.plan_edit", person=pid, month=month.strftime("%Y-%m")))
