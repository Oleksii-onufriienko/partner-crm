"""Ежедневная работа (пункт В): режим обзвона (Tages-Statistik), калькулятор дохода
(«Erstellen Sie Ihren persönlichen Plan», AK1), цели (Zukunftsplanung) и Musterwoche.
Маршруты регистрируются в блюпринте «main»."""
import datetime as dt
import json
import math

from flask import abort, flash, g, redirect, render_template, request, url_for

from . import constants as C
from . import plan as P
from .access import get_person, visible_ids
from .auth import login_required
from .db import execute, get_db, query
from .main import _pid_arg, bp, get_contact
from .util import clean, monday, parse_date, parse_float, parse_int, safe_next, today

# ================================================================= Режим обзвона

TEMP_ORDER = "CASE c.temperature WHEN 'very_hot' THEN 0 WHEN 'hot' THEN 1 WHEN 'warm' THEN 2 " \
             "WHEN 'lukewarm' THEN 3 ELSE 4 END"
CALL_MODES = [("due", "Напоминания на сегодня"), ("new", "Ещё не звонил"), ("all", "Все, кроме «нет шансов»")]


def call_queue(pid, mode):
    """Кому звонить: без тех, кому уже звонили сегодня."""
    t = today().isoformat()
    where = ["c.owner_id = ?", "c.status != 'no_chance'",
             "NOT EXISTS (SELECT 1 FROM calls k WHERE k.contact_id = c.id AND k.date = ?)"]
    args = [pid, t]
    if mode == "due":
        where.append("c.next_action_date IS NOT NULL AND c.next_action_date <= ?")
        args.append(t)
        order = f"c.next_action_date, {TEMP_ORDER}"
    elif mode == "new":
        where.append("NOT EXISTS (SELECT 1 FROM calls k WHERE k.contact_id = c.id)")
        where.append("NOT EXISTS (SELECT 1 FROM meetings m WHERE m.contact_id = c.id)")
        where.append("c.kind = 'prospect'")
        order = f"{TEMP_ORDER}, c.created_at"
    else:
        order = f"COALESCE(c.next_action_date, '9999'), {TEMP_ORDER}, c.created_at"
    return query(f"""SELECT c.*,
                       (SELECT COALESCE(SUM(ke), 0) FROM potentials WHERE contact_id = c.id) pot,
                       (SELECT COUNT(*) FROM calls k WHERE k.contact_id = c.id) calls_n,
                       (SELECT MAX(date) FROM calls k WHERE k.contact_id = c.id) last_call
                     FROM contacts c WHERE {' AND '.join(where)} ORDER BY {order}""", args)


def calls_today(pid):
    t = today().isoformat()
    rows = query("SELECT result, COUNT(*) n FROM calls WHERE owner_id = ? AND date = ? GROUP BY result", (pid, t))
    by = {r["result"]: r["n"] for r in rows}
    return {"total": sum(by.values()), "reached": sum(by.get(k, 0) for k in C.CALL_REACHED),
            "appointments": by.get("appointment", 0), "by": by}


@bp.route("/calls")
@login_required
def calls():
    pid = _pid_arg()
    p = get_person(pid)
    mode = request.args.get("mode") if request.args.get("mode") in C.keys(CALL_MODES) else None
    counts = {m: len(call_queue(pid, m)) for m, _ in CALL_MODES}
    if mode is None:
        mode = "due" if counts["due"] else ("new" if counts["new"] else "all")
    queue = call_queue(pid, mode)
    skip = parse_int(request.args.get("skip")) or 0
    skip = skip % len(queue) if queue else 0
    current = queue[skip] if queue else None
    meetings = []
    if current:
        meetings = query("""SELECT * FROM meetings WHERE contact_id = ? ORDER BY date DESC LIMIT 3""", (current["id"],))
    log = query("""SELECT k.*, c.first_name, c.last_name FROM calls k LEFT JOIN contacts c ON c.id = k.contact_id
                   WHERE k.owner_id = ? AND k.date = ? ORDER BY k.time DESC, k.id DESC""", (pid, today().isoformat()))
    t = today()
    return render_template("calls.html", p=p, mode=mode, modes=CALL_MODES, counts=counts, queue=queue,
                           current=current, skip=skip, nxt=queue[skip + 1:skip + 6] if queue else [],
                           stats=calls_today(pid), log=log, meetings=meetings,
                           tomorrow=t + dt.timedelta(days=1), in3=t + dt.timedelta(days=3))


@bp.route("/calls/<int:cid>", methods=["POST"])
@login_required
def call_result(cid):
    c = get_contact(cid)
    result = request.form.get("result")
    if result not in C.keys(C.CALL_RESULTS):
        abort(400)
    t = today()
    back = safe_next(url_for("main.calls", person=c["owner_id"]))
    now = dt.datetime.now().strftime("%H:%M")
    if result == "appointment":
        d = parse_date(request.form.get("date"))
        if not d:
            flash("Укажите дату термина.", "error")
            return redirect(back)
        tm = (request.form.get("time") or "").strip()[:5]
        if tm and not (len(tm) == 5 and tm[2] == ":"):
            tm = ""
        stage = request.form.get("stage") if request.form.get("stage") in ("first", "advocate", "analysis", "consult",
                                                                            "service", "recruiting") else "first"
        fmt = request.form.get("format") if request.form.get("format") in C.keys(C.FORMATS) else "offline"
        execute("""INSERT INTO meetings (owner_id, contact_id, date, time, duration_min, format, stage, status, created_by)
                   VALUES (?, ?, ?, ?, 60, ?, ?, 'planned', ?)""",
                (c["owner_id"], cid, d.isoformat(), tm or None, fmt, stage, g.user["id"]))
        execute("""UPDATE contacts SET status = 'appointment', next_action = NULL, next_action_date = NULL,
                   updated_at = datetime('now') WHERE id = ?""", (cid,))
        msg = f"Термин с {c['first_name']} {d.strftime('%d.%m.')}{' в ' + tm if tm else ''} — в планере."
    elif result == "callback":
        d = parse_date(request.form.get("callback_date")) or (t + dt.timedelta(days=3))
        note = clean(request.form.get("note"), 200) or "Перезвонить"
        execute("""UPDATE contacts SET status = 'followup', next_action = ?, next_action_date = ?,
                   updated_at = datetime('now') WHERE id = ?""", (note, d.isoformat(), cid))
        msg = f"{c['first_name']}: перезвонить {d.strftime('%d.%m.')}."
    elif result == "no_answer":
        nad = parse_date(c["next_action_date"])
        if nad is None or nad <= t:
            execute("""UPDATE contacts SET next_action = COALESCE(next_action, 'Позвонить ещё раз'), next_action_date = ?,
                       updated_at = datetime('now') WHERE id = ?""", ((t + dt.timedelta(days=1)).isoformat(), cid))
        msg = f"{c['first_name']}: не дозвонился, напомню завтра."
    else:
        execute("""UPDATE contacts SET status = 'no_chance', next_action = NULL, next_action_date = NULL,
                   updated_at = datetime('now') WHERE id = ?""", (cid,))
        msg = f"{c['first_name']}: нет шансов."
    note = clean(request.form.get("comment"), 500)
    if note:
        stamp = t.strftime("%d.%m.")
        execute("""UPDATE contacts SET comment = TRIM(COALESCE(comment, '') || char(10) || ?) WHERE id = ?""",
                (f"{stamp} звонок: {note}", cid))
    execute("INSERT INTO calls (owner_id, contact_id, date, time, result, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (c["owner_id"], cid, t.isoformat(), now, result, g.user["id"]))
    flash(msg, "ok")
    return redirect(back)


# ================================================================= Калькулятор дохода

# Квоты по умолчанию, если своих данных мало: (ключ, подпись, значение, числитель, знаменатель в план/факте)
CALC_QUOTAS = [
    ("ke_client", "единиц в среднем с одного нового клиента", 25, "br_ke", "br_clients"),
    ("br_client", "бератунгов на одного нового клиента", 1.5, "br_held", "br_clients"),
    ("fa_br", "финанализов на один бератунг", 1.3, "fa_created", "br_held"),
    ("held_fa", "проведённых первых терминов на один финанализ", 1.5, "fa_held", "fa_created"),
    ("agreed_held", "договорённых первых терминов на один проведённый", 1.3, "fa_agreed", "fa_held"),
    ("contacts_agreed", "контактов на один договорённый первый термин", 3.3, "fa_contacts", "fa_agreed"),
]
CALC_WEEKS = 12            # квоты считаются по последним 12 неделям
CALC_MIN = 3               # меньше 3 событий в знаменателе — берём значение по умолчанию
WEEKS_IN_MONTH = 52 / 12


def own_quotas(pid):
    end = monday(today())
    weeks = [end - dt.timedelta(days=7 * i) for i in range(CALC_WEEKS, 0, -1)]
    grid = P.grids([pid], weeks)[pid]
    tot = {}
    for wk in grid.values():
        for k, v in wk.items():
            tot[k] = tot.get(k, 0) + (v["ist"] or 0)
    out = {}
    for key, label, dflt, num, den in CALC_QUOTAS:
        n, d = tot.get(num, 0), tot.get(den, 0)
        if d >= CALC_MIN and n > 0 and (key == "ke_client" or n >= d):
            out[key] = {"value": round(n / d, 2), "own": True, "num": n, "den": d, "why": None}
        else:
            # Меньше единицы быть не может (на одного клиента — хотя бы один бератунг и т. д.):
            # значит, часть встреч не внесена в планер — берём значение по умолчанию
            why = "мало данных" if d < CALC_MIN or n == 0 else "встречи внесены не полностью"
            out[key] = {"value": dflt, "own": False, "num": n, "den": d, "why": why}
    return out


def calculate(income, rate, q):
    """Цепочка AK1: доход → единицы → клиенты → бератунги → финанализы → термины → контакты (в месяц)."""
    units = income / rate if rate else 0
    clients = units / q["ke_client"] if q["ke_client"] else 0
    consults = clients * q["br_client"]
    analyses = consults * q["fa_br"]
    held = analyses * q["held_fa"]
    agreed = held * q["agreed_held"]
    contacts = agreed * q["contacts_agreed"]
    rows = [
        ("units", "Единицы", "br_ke", units),
        ("clients", "Новые клиенты", "br_clients", clients),
        ("consults", "Бератунги", "br_held", consults),
        ("analyses", "Финанализы", "fa_created", analyses),
        ("held", "Проведённые первые термины", "fa_held", held),
        ("agreed", "Договорённые первые термины", "fa_agreed", agreed),
        ("contacts", "Контакты для первого термина", "fa_contacts", contacts),
    ]
    return [{"key": k, "label": lbl, "metric": m, "month": v, "week": v / WEEKS_IN_MONTH} for k, lbl, m, v in rows]


def _calc_inputs(pid, p, args):
    goals = load_goals(pid)
    q = own_quotas(pid)
    income = parse_float(args.get("income"))
    if income is None:
        income = parse_float(goals.get("fin_month_this")) or 3000
    rate = parse_float(args.get("rate")) or p["coef"] or C.STUFE_DEFAULT_COEF.get(p["stufe"], 1)
    hours = parse_float(args.get("hours"))
    used = {}
    for key, label, dflt, *_ in CALC_QUOTAS:
        v = parse_float(args.get(f"q_{key}"))
        used[key] = v if v and v > 0 else q[key]["value"]
    return income, rate, hours, q, used


@bp.route("/plan/calculator")
@login_required
def calculator():
    pid = _pid_arg()
    p = get_person(pid)
    income, rate, hours, q, used = _calc_inputs(pid, p, request.args)
    rows = calculate(income, rate, used)
    t = today()
    months = [t.replace(day=1), (t.replace(day=28) + dt.timedelta(days=4)).replace(day=1)]
    return render_template("calculator.html", p=p, income=income, rate=rate, hours=hours, q=q, used=used,
                           quotas=CALC_QUOTAS, rows=rows, months=months, weeks_n=CALC_WEEKS,
                           goals=load_goals(pid))


@bp.route("/plan/calculator/apply", methods=["POST"])
@login_required
def calculator_apply():
    pid = _pid_arg()
    p = get_person(pid)
    income, rate, hours, q, used = _calc_inputs(pid, p, request.form)
    month = parse_date((request.form.get("month") or "") + "-01")
    if not month:
        abort(400)
    rows = calculate(income, rate, used)
    weeks = P.month_weeks(month.year, month.month)
    db = get_db()
    for r in rows:
        v = r["week"]
        soll = round(v / 5) * 5 if r["metric"] == "br_ke" else math.ceil(v - 0.05)
        for w in weeks:
            db.execute("""INSERT INTO week_plan (person_id, week, metric, soll, updated_by, updated_at)
                          VALUES (?, ?, ?, ?, ?, datetime('now'))
                          ON CONFLICT(person_id, week, metric) DO UPDATE SET soll = excluded.soll,
                          updated_by = excluded.updated_by, updated_at = excluded.updated_at""",
                       (pid, w.isoformat(), r["metric"], soll, g.user["id"]))
    # договорённые бератунги ≈ проведённые
    br = next(r for r in rows if r["key"] == "consults")
    for w in weeks:
        db.execute("""INSERT INTO week_plan (person_id, week, metric, soll, updated_by, updated_at)
                      VALUES (?, ?, 'br_agreed', ?, ?, datetime('now'))
                      ON CONFLICT(person_id, week, metric) DO UPDATE SET soll = excluded.soll,
                      updated_by = excluded.updated_by, updated_at = excluded.updated_at""",
                   (pid, w.isoformat(), math.ceil(br["week"] - 0.05), g.user["id"]))
    db.commit()
    flash(f"План на {len(weeks)} {'недели' if len(weeks) < 5 else 'недель'} заполнен из калькулятора. "
          f"Факт и остальные строки не тронуты.", "ok")
    return redirect(url_for("main.plan", person=pid, month=month.strftime("%Y-%m")))


# ================================================================= Цели (Zukunftsplanung)

GOAL_PERIODS = [("this", "Этот год", "Dieses Jahr"), ("next", "Следующий год", "Nächstes Jahr"),
                ("five", "Через 5 лет", "in 5 Jahren")]
COMPETITIONS = [("gruppe", "Группа", "Gruppe"), ("direktion", "Дирекция", "Direktion"),
                ("bereich", "Direktionsbereich", "Direktionsbereich"),
                ("lls", "DVAG «Leistung lohnt sich»", "DVAG Leistung lohnt sich"), ("dvag", "DVAG", "DVAG")]
REWARDS = 6


def load_goals(pid):
    r = query("SELECT data FROM future_goals WHERE person_id = ?", (pid,), one=True)
    if not r:
        return {}
    try:
        d = json.loads(r["data"])
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def save_goals(pid, form, user_id):
    d = {}
    for per, *_ in GOAL_PERIODS:
        for k in (f"fin_month_{per}", f"fin_year_{per}"):
            v = parse_float(form.get(k))
            d[k] = v if v is not None and v >= 0 else None
        for k in (f"mat_{per}", f"pers_{per}"):
            d[k] = clean(form.get(k), 500)
    for key, *_ in COMPETITIONS:
        d[f"comp_{key}"] = {"goal": clean(form.get(f"comp_{key}_goal"), 200),
                            "target": clean(form.get(f"comp_{key}_target"), 200),
                            "prize": clean(form.get(f"comp_{key}_prize"), 200)}
    rewards = []
    for i in range(REWARDS):
        what = clean(form.get(f"rw_{i}_what"), 200)
        if what:
            when = parse_date(form.get(f"rw_{i}_when"))
            rewards.append({"what": what, "when": when.isoformat() if when else None,
                            "why": clean(form.get(f"rw_{i}_why"), 200)})
    d["rewards"] = rewards
    d["motto"] = clean(form.get("motto"), 300)
    stufe = form.get("career_stufe")
    d["career_stufe"] = stufe if stufe in C.STUFE_CODES else None
    cd = parse_date(form.get("career_date"))
    d["career_date"] = cd.isoformat() if cd else None
    db = get_db()
    db.execute("""INSERT INTO future_goals (person_id, data, updated_by, updated_at) VALUES (?, ?, ?, datetime('now'))
                  ON CONFLICT(person_id) DO UPDATE SET data = excluded.data, updated_by = excluded.updated_by,
                  updated_at = excluded.updated_at""", (pid, json.dumps(d, ensure_ascii=False), user_id))
    db.commit()


@bp.route("/plan/goals", methods=["GET", "POST"])
@login_required
def goals():
    pid = _pid_arg()
    p = get_person(pid)
    if request.method == "POST":
        save_goals(pid, request.form, g.user["id"])
        flash("Цели сохранены.", "ok")
        return redirect(url_for("main.goals", person=pid))
    from . import career as K
    return render_template("goals.html", p=p, d=load_goals(pid), periods=GOAL_PERIODS, comps=COMPETITIONS,
                           rewards_n=REWARDS, year=today().year, targets=K.next_targets(p["stufe"]))


# ================================================================= Musterwoche

def muster_blocks(pid):
    return query("SELECT * FROM muster_blocks WHERE person_id = ? ORDER BY weekday, start", (pid,))


def _hm(s):
    s = (s or "").strip()[:5]
    if len(s) == 5 and s[2] == ":" and s[:2].isdigit() and s[3:].isdigit() and int(s[:2]) < 24 and int(s[3:]) < 60:
        return s
    return None


def _minutes(s):
    return int(s[:2]) * 60 + int(s[3:])


@bp.route("/plan/muster", methods=["GET", "POST"])
@login_required
def muster():
    pid = _pid_arg()
    p = get_person(pid)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "delete":
            execute("DELETE FROM muster_blocks WHERE id = ? AND person_id = ?",
                    (parse_int(request.form.get("id")), pid))
            flash("Блок удалён.", "ok")
        else:
            days = [d for d in range(7) if request.form.get(f"wd_{d}")]
            start, end = _hm(request.form.get("start")), _hm(request.form.get("end"))
            kind = request.form.get("kind") if request.form.get("kind") in C.keys(C.MUSTER_KINDS) else "vb"
            if not days or not start or not end or _minutes(end) <= _minutes(start):
                flash("Выберите дни и время: «до» позже, чем «с».", "error")
            else:
                for d in days:
                    execute("""INSERT INTO muster_blocks (person_id, weekday, start, end, kind, title)
                               VALUES (?, ?, ?, ?, ?, ?)""", (pid, d, start, end, kind, clean(request.form.get("title"), 80)))
                flash("Добавлено в Musterwoche.", "ok")
        return redirect(url_for("main.muster", person=pid))
    blocks = muster_blocks(pid)
    hours = {}
    for b in blocks:
        hours[b["kind"]] = hours.get(b["kind"], 0) + (_minutes(b["end"]) - _minutes(b["start"])) / 60
    first = min([_minutes(b["start"]) for b in blocks] + [8 * 60]) // 60
    last = max([_minutes(b["end"]) for b in blocks] + [21 * 60])
    last = math.ceil(last / 60)
    by_day = {d: [] for d in range(7)}
    for b in blocks:
        by_day[b["weekday"]].append(b)
    return render_template("muster.html", p=p, blocks=blocks, by_day=by_day, hours=hours, first=first, last=last,
                           minutes=_minutes)
