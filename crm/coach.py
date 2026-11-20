"""Работа наставника с партнёром (пункт Б):
подготовка к ORGA (ORGA Checkliste), Reflexionsgespräche (AK1), старт новичка (Ausbildungsplanung).
Маршруты регистрируются в блюпринте «main»."""
import datetime as dt
import json

from flask import abort, flash, g, redirect, render_template, request, url_for

from . import career as K
from . import constants as C
from . import plan as P
from .access import branch_ids, children_map, direct_children, get_person, visible_ids, visible_persons
from .auth import login_required
from .db import execute, get_db, query
from .main import _pid_arg, _set_view, bp
from .util import clean, monday, parse_date, parse_int, safe_next, today

# ================================================================= ORGA

def orga_default_week(t=None):
    """О какой неделе готовимся рассказать: с понедельника по среду — о прошлой, с четверга — о текущей."""
    t = t or today()
    w = monday(t)
    return w - dt.timedelta(days=7) if t.weekday() < 3 else w


def get_orga(pid, week):
    return query("SELECT * FROM orga_checks WHERE person_id = ? AND week = ?", (pid, week.isoformat()), one=True)


def skills_of(row):
    if not row or not row["skills"]:
        return {}
    try:
        data = json.loads(row["skills"])
    except ValueError:
        return {}
    return {k: v for k, v in data.items() if k in C.ORGA_SKILL_KEYS and isinstance(v, int)}


ORGA_TEXT = ["next_stufe", "insight", "went_well", "why_well", "improve", "measures", "controller",
             "prev_why", "reward", "reward_for"]


def save_orga(pid, week, form, user_id):
    data = {k: clean(form.get(k), 2000) for k in ORGA_TEXT}
    if data["next_stufe"] not in C.STUFE_CODES:
        data["next_stufe"] = None
    for k in ("next_stufe_date", "measures_when"):
        d = parse_date(form.get(k))
        data[k] = d.isoformat() if d else None
    data["prev_done"] = {"1": 1, "0": 0}.get(form.get("prev_done"))
    for k in ("tables_ready", "next_plan_ready", "potential_ready"):
        data[k] = 1 if form.get(k) else 0
    skills = {}
    for key in C.ORGA_SKILL_KEYS:
        v = parse_int(form.get(f"skill_{key}"))
        if v is not None and 0 <= v <= 10:
            skills[key] = v
    data["skills"] = json.dumps(skills) if skills else None
    cols = list(data)
    db = get_db()
    db.execute(f"""INSERT INTO orga_checks (person_id, week, {', '.join(cols)}, updated_at)
                   VALUES (?, ?, {', '.join('?' * len(cols))}, datetime('now'))
                   ON CONFLICT(person_id, week) DO UPDATE SET
                   {', '.join(f'{c} = excluded.{c}' for c in cols)}, updated_at = datetime('now')""",
               [pid, week.isoformat(), *data.values()])
    db.commit()


def orga_history(pid, limit=12):
    return query("SELECT * FROM orga_checks WHERE person_id = ? ORDER BY week DESC LIMIT ?", (pid, limit))


def week_summary(pid, week):
    """Короткая сводка план/факт недели — подсказка к вопросу «вывод из плана и факта»."""
    grid = P.grids([pid], [week])[pid][week.isoformat()]
    out = []
    for key, label in C.PLAN_SUMMARY:
        c = grid.get(key) or {}
        out.append({"label": label, "soll": c.get("soll"), "ist": c.get("ist")})
    return out


@bp.route("/plan/orga", methods=["GET", "POST"])
@login_required
def orga():
    pid = _pid_arg()
    p = get_person(pid)
    week = monday(parse_date(request.values.get("week")) or orga_default_week())
    if request.method == "POST":
        save_orga(pid, week, request.form, g.user["id"])
        flash("Подготовка к ORGA сохранена.", "ok")
        return redirect(url_for("main.orga", person=pid, week=week.isoformat()))
    row = get_orga(pid, week)
    prev = get_orga(pid, week - dt.timedelta(days=7))
    nxt_week = week + dt.timedelta(days=7)
    has_next_plan = query("""SELECT 1 FROM week_plan WHERE person_id = ? AND week = ? AND soll IS NOT NULL LIMIT 1""",
                          (pid, nxt_week.isoformat()), one=True) is not None
    targets = K.next_targets(p["stufe"])
    history = list(reversed(orga_history(pid)))
    return render_template("orga.html", p=p, week=week, row=row, prev=prev, skills=skills_of(row),
                           prev_skills=skills_of(prev), summary=week_summary(pid, week),
                           has_next_plan=has_next_plan, targets=targets, history=history,
                           history_skills=[(h, skills_of(h)) for h in history],
                           prev_week=week - dt.timedelta(days=7), next_week=nxt_week,
                           default_week=orga_default_week(), goals=_future_goal_stufe(pid))


def _future_goal_stufe(pid):
    """Карьерная цель из «Целей» — подсказка к вопросу «моя следующая цель»."""
    r = query("SELECT data FROM future_goals WHERE person_id = ?", (pid,), one=True)
    if not r:
        return {}
    try:
        d = json.loads(r["data"])
    except ValueError:
        return {}
    return {"stufe": d.get("career_stufe"), "date": d.get("career_date")}


# ================================================================= Reflexionsgespräche

def reflections_of(pid):
    return query("""SELECT r.*, p.first_name cf, p.last_name cl FROM reflections r
                    LEFT JOIN persons p ON p.id = r.created_by
                    WHERE r.person_id = ? ORDER BY r.date DESC, r.id DESC""", (pid,))


def results_between(pid, start, end):
    """Итоги человека за период — для блока «чего достигли» в разговоре."""
    s, e = start.isoformat(), end.isoformat()
    out = {k: 0 for k in C.keys(C.REFLECTION_RESULTS)}
    for r in query("""SELECT stage, COUNT(*) n FROM meetings WHERE owner_id = ? AND status = 'done'
                      AND date BETWEEN ? AND ? GROUP BY stage""", (pid, s, e)):
        if r["stage"] == "analysis":
            out["analyses"] += r["n"]
        elif r["stage"] in ("consult", "closing"):
            out["consults"] += r["n"]
    weeks = []
    w = monday(start)
    while w <= end:
        weeks.append(w)
        w += dt.timedelta(days=7)
    grid = P.grids([pid], weeks)[pid] if weeks else {}
    for wk in grid.values():
        for key in ("fa_referrals", "br_referrals", "st_referrals"):
            out["referrals"] += (wk.get(key) or {}).get("ist") or 0
    r = query("""SELECT COUNT(*) n FROM (SELECT d.contact_id, MIN(d.date) f FROM deals d JOIN contacts c ON c.id = d.contact_id
                 WHERE c.owner_id = ? GROUP BY d.contact_id) WHERE f BETWEEN ? AND ?""", (pid, s, e), one=True)
    out["clients"] = r["n"]
    r = query("""SELECT COALESCE(SUM(d.ke), 0) u FROM deals d JOIN contacts c ON c.id = d.contact_id
                 WHERE c.owner_id = ? AND d.date BETWEEN ? AND ?""", (pid, s, e), one=True)
    out["units"] = round(r["u"] or 0, 1)
    r = query("""SELECT COUNT(DISTINCT l.contact_id) n FROM recruit_log l JOIN contacts c ON c.id = l.contact_id
                 WHERE c.owner_id = ? AND l.stage = 'attended' AND l.date BETWEEN ? AND ?""", (pid, s, e), one=True)
    out["info"] = r["n"]
    r = query("""SELECT COUNT(*) n FROM persons WHERE parent_id = ? AND start_date BETWEEN ? AND ?""",
              (pid, s, e), one=True)
    out["vm"] = r["n"]
    out["partners"] = out["vm"]
    return out


def _reflection_period(pid, before=None):
    p = visible_persons()[pid]
    last = query("""SELECT MAX(date) d FROM reflections WHERE person_id = ?""" +
                 (" AND date < ?" if before else ""), (pid, before) if before else (pid,), one=True)
    start = parse_date(last["d"]) if last and last["d"] else None
    if start is None:
        start = parse_date(p["start_date"]) or (today() - dt.timedelta(days=30))
    return start


@bp.route("/people/<int:pid>/reflection", methods=["GET", "POST"])
@bp.route("/people/<int:pid>/reflection/<int:rid>", methods=["GET", "POST"])
@login_required
def reflection(pid, rid=None):
    p = get_person(pid)
    _set_view(pid)
    row = None
    if rid:
        row = query("SELECT * FROM reflections WHERE id = ? AND person_id = ?", (rid, pid), one=True)
        if row is None:
            abort(404)
    form = request.form
    if request.method == "POST":
        d = parse_date(form.get("date"))
        if not d:
            flash("Укажите дату разговора.", "error")
        else:
            results = {}
            for key in C.keys(C.REFLECTION_RESULTS):
                v = form.get(f"res_{key}", "").replace(",", ".").strip()
                try:
                    results[key] = float(v) if v else 0
                except ValueError:
                    results[key] = 0
            nd = parse_date(form.get("next_date"))
            tm = (form.get("next_time") or "").strip()[:5]
            if tm and not (len(tm) == 5 and tm[2] == ":"):
                tm = ""
            people = [k for k in C.keys(C.REFLECTION_PEOPLE) if form.get(f"people_{k}")]
            sat = parse_int(form.get("satisfaction"))
            data = {
                "date": d.isoformat(), "place": clean(form.get("place"), 120), "people": ",".join(people),
                "satisfaction": sat if sat and 1 <= sat <= 5 else None,
                "goals_reached": clean(form.get("goals_reached"), 2000), "improve": clean(form.get("improve"), 2000),
                "results": json.dumps(results), "period_from": (parse_date(form.get("period_from")) or d).isoformat(),
                "cp_clients": parse_int(form.get("cp_clients")), "cp_clients_goal": parse_int(form.get("cp_clients_goal")),
                "cp_partners": parse_int(form.get("cp_partners")),
                "cp_partners_goal": parse_int(form.get("cp_partners_goal")),
                "goal1": clean(form.get("goal1"), 300), "goal2": clean(form.get("goal2"), 300),
                "goal3": clean(form.get("goal3"), 300), "work_plan": clean(form.get("work_plan"), 3000),
                "intent": form.get("intent") if form.get("intent") in C.keys(C.CAREER_INTENTS) else None,
                "next_date": nd.isoformat() if nd else None, "next_time": tm or None,
            }
            if row:
                execute(f"UPDATE reflections SET {', '.join(f'{k} = ?' for k in data)} WHERE id = ?",
                        [*data.values(), row["id"]])
                rid, meeting_id = row["id"], row["meeting_id"]
            else:
                data["created_by"] = g.user["id"]
                data["person_id"] = pid
                rid = execute(f"INSERT INTO reflections ({', '.join(data)}) VALUES ({', '.join('?' * len(data))})",
                              list(data.values()))
                meeting_id = None
            _sync_reflection_meeting(rid, p, data, meeting_id)
            flash("Reflexionsgespräch сохранён." + (" Следующий разговор — в планере." if nd else ""), "ok")
            return redirect(url_for("main.person", pid=pid) + "#reflections")
    # Новая запись: итоги считаются сами за период с прошлого разговора
    if row:
        start = parse_date(row["period_from"]) or parse_date(row["date"])
        results = json.loads(row["results"] or "{}")
        values = dict(row)
    else:
        start = _reflection_period(pid)
        results = results_between(pid, start, today())
        cp = query("""SELECT COUNT(*) n, SUM(CASE WHEN recruit_stage IS NOT NULL THEN 1 ELSE 0 END) r
                      FROM contacts WHERE owner_id = ?""", (pid,), one=True)
        last = query("SELECT * FROM reflections WHERE person_id = ? ORDER BY date DESC LIMIT 1", (pid,), one=True)
        values = {"date": today().isoformat(), "people": "coach", "cp_clients": cp["n"], "cp_partners": cp["r"] or 0,
                  "intent": last["intent"] if last else None,
                  "period_from": start.isoformat()}
    number = query("SELECT COUNT(*) n FROM reflections WHERE person_id = ? AND (? IS NULL OR id <= ?)",
                   (pid, rid, rid), one=True)["n"] + (0 if row else 1)
    prev = None
    q = "SELECT * FROM reflections WHERE person_id = ?" + (" AND id < ?" if row else "") + " ORDER BY date DESC, id DESC LIMIT 1"
    prev = query(q, (pid, row["id"]) if row else (pid,), one=True)
    return render_template("reflection.html", p=p, row=row, v=form if request.method == "POST" else values,
                           results=results, start=start, number=number, prev=prev)


def _sync_reflection_meeting(rid, p, data, meeting_id):
    """Следующий разговор — встреча в планере того, кто ведёт разговор."""
    title = f"Reflexionsgespräch: {p['first_name']} {p['last_name'] or ''}".strip()
    if data["next_date"]:
        if meeting_id and query("SELECT 1 FROM meetings WHERE id = ?", (meeting_id,), one=True):
            execute("UPDATE meetings SET date = ?, time = ?, title = ? WHERE id = ?",
                    (data["next_date"], data["next_time"], title, meeting_id))
        else:
            mid = execute("""INSERT INTO meetings (owner_id, title, date, time, duration_min, format, stage, status,
                                                   note, created_by)
                             VALUES (?, ?, ?, ?, 60, 'offline', 'reflection', 'planned', ?, ?)""",
                          (g.user["id"], title, data["next_date"], data["next_time"],
                           "Цели: " + "; ".join(x for x in (data["goal1"], data["goal2"], data["goal3"]) if x),
                           g.user["id"]))
            execute("UPDATE reflections SET meeting_id = ? WHERE id = ?", (mid, rid))
    elif meeting_id:
        execute("DELETE FROM meetings WHERE id = ? AND status = 'planned'", (meeting_id,))
        execute("UPDATE reflections SET meeting_id = NULL WHERE id = ?", (rid,))


@bp.route("/people/<int:pid>/reflection/<int:rid>/delete", methods=["POST"])
@login_required
def reflection_delete(pid, rid):
    get_person(pid)
    row = query("SELECT * FROM reflections WHERE id = ? AND person_id = ?", (rid, pid), one=True)
    if row is None:
        abort(404)
    if row["meeting_id"]:
        execute("DELETE FROM meetings WHERE id = ? AND status = 'planned'", (row["meeting_id"],))
    execute("DELETE FROM reflections WHERE id = ?", (rid,))
    flash("Разговор удалён.", "ok")
    return redirect(url_for("main.person", pid=pid) + "#reflections")


# ================================================================= Старт новичка

def _nth_date(rows, n):
    """Дата n-го события (rows отсортированы по дате)."""
    return parse_date(rows[n - 1]["d"]) if len(rows) >= n else None


def onboarding(person_ids):
    """{pid: {"steps": [...], "done": n, "total": n, "current": шаг|None, "last": дата, "stuck": bool,
              "topics": [...]}}"""
    if not person_ids:
        return {}
    vp = visible_persons()
    marks = ",".join("?" * len(person_ids))
    manual = {}
    for r in query(f"SELECT * FROM onboarding WHERE person_id IN ({marks})", list(person_ids)):
        manual.setdefault(r["person_id"], {})[r["step"]] = r
    contacts_by = {}
    for r in query(f"""SELECT owner_id, temperature, created_at d FROM contacts WHERE owner_id IN ({marks})
                       ORDER BY created_at""", list(person_ids)):
        contacts_by.setdefault(r["owner_id"], []).append(r)
    meetings_by = {}
    for r in query(f"""SELECT owner_id, stage, date d FROM meetings WHERE owner_id IN ({marks})
                       AND status = 'done' AND stage IN ('advocate', 'analysis') ORDER BY date""", list(person_ids)):
        meetings_by.setdefault((r["owner_id"], r["stage"]), []).append(r)
    first_deal = {r["owner_id"]: parse_date(r["d"]) for r in query(
        f"""SELECT c.owner_id, MIN(d.date) d FROM deals d JOIN contacts c ON c.id = d.contact_id
            WHERE c.owner_id IN ({marks}) GROUP BY c.owner_id""", list(person_ids))}
    refl_by = {}
    for r in query(f"SELECT person_id, date d FROM reflections WHERE person_id IN ({marks}) ORDER BY date",
                   list(person_ids)):
        refl_by.setdefault(r["person_id"], []).append(r)

    t = today()
    out = {}
    for pid in person_ids:
        p = vp.get(pid)
        if p is None:
            continue
        cs = contacts_by.get(pid, [])
        auto = {
            "mp20": _nth_date(cs, 20),
            "fuersprecher": _nth_date([c for c in cs if c["temperature"] == "very_hot"], 6),
            "fs_talks": _nth_date(meetings_by.get((pid, "advocate"), []), 3),
            "first_analysis": _nth_date(meetings_by.get((pid, "analysis"), []), 1),
            "first_client": first_deal.get(pid),
            "refl1": _nth_date(refl_by.get(pid, []), 1),
            "refl2": _nth_date(refl_by.get(pid, []), 2),
        }
        counts = {"mp20": (len(cs), 20), "fuersprecher": (sum(1 for c in cs if c["temperature"] == "very_hot"), 6),
                  "fs_talks": (len(meetings_by.get((pid, "advocate"), [])), 3)}
        steps, done = [], 0
        for key, label, de, kind in C.ONBOARDING_STEPS:
            m = manual.get(pid, {}).get(key)
            date = parse_date(m["date"]) if m and m["date"] else None
            result = m["result"] if m else None
            if kind == "exam":
                ok = result == "passed"
            else:
                if date is None and kind == "auto":
                    date = auto.get(key)
                ok = date is not None
            done += ok
            steps.append({"key": key, "label": label, "de": de, "kind": kind, "done": ok, "date": date,
                          "result": result, "note": m["note"] if m else None,
                          "auto": kind == "auto" and auto.get(key) is not None and not (m and m["date"]),
                          "count": counts.get(key)})
        topics = []
        for i in range(1, C.ONBOARDING_TOPICS + 1):
            m = manual.get(pid, {}).get(f"topic{i}")
            topics.append({"i": i, "note": m["note"] if m else "", "date": parse_date(m["date"]) if m and m["date"] else None})
        joined = parse_date(p["start_date"]) or parse_date((p["created_at"] or "")[:10]) or t
        dates = [s["date"] for s in steps if s["done"] and s["date"]]
        last = max(dates) if dates else joined
        current = next((s for s in steps if not s["done"]), None)
        out[pid] = {"steps": steps, "done": done, "total": len(steps), "current": current, "last": last,
                    "joined": joined, "days_in": (t - joined).days, "idle": (t - last).days,
                    "stuck": current is not None and (t - last).days > C.ONBOARDING_STUCK_DAYS, "topics": topics}
    return out


@bp.route("/people/<int:pid>/start", methods=["GET", "POST"])
@login_required
def person_start(pid):
    p = get_person(pid)
    _set_view(pid)
    if request.method == "POST":
        db = get_db()
        for key, label, de, kind in C.ONBOARDING_STEPS:
            d = parse_date(request.form.get(f"d_{key}"))
            result = request.form.get(f"r_{key}") if kind == "exam" else None
            result = result if result in ("passed", "failed") else None
            if d or result:
                db.execute("""INSERT INTO onboarding (person_id, step, date, result, updated_by, updated_at)
                              VALUES (?, ?, ?, ?, ?, datetime('now'))
                              ON CONFLICT(person_id, step) DO UPDATE SET date = excluded.date, result = excluded.result,
                              updated_by = excluded.updated_by, updated_at = excluded.updated_at""",
                           (pid, key, d.isoformat() if d else None, result, g.user["id"]))
            else:
                db.execute("DELETE FROM onboarding WHERE person_id = ? AND step = ?", (pid, key))
        for i in range(1, C.ONBOARDING_TOPICS + 1):
            note = clean(request.form.get(f"topic{i}"), 200)
            d = parse_date(request.form.get(f"topic{i}_d"))
            if note or d:
                db.execute("""INSERT INTO onboarding (person_id, step, date, note, updated_by, updated_at)
                              VALUES (?, ?, ?, ?, ?, datetime('now'))
                              ON CONFLICT(person_id, step) DO UPDATE SET date = excluded.date, note = excluded.note,
                              updated_by = excluded.updated_by, updated_at = excluded.updated_at""",
                           (pid, f"topic{i}", d.isoformat() if d else None, note, g.user["id"]))
            else:
                db.execute("DELETE FROM onboarding WHERE person_id = ? AND step = ?", (pid, f"topic{i}"))
        db.commit()
        flash("Старт сохранён.", "ok")
        return redirect(url_for("main.person_start", pid=pid))
    return render_template("person_start.html", p=p, ob=onboarding([pid])[pid])


@bp.route("/team/start")
@login_required
def team_start():
    pid = _pid_arg()
    p = get_person(pid)
    vp = visible_persons()
    show_all = request.args.get("all") == "1"
    ids = [i for i in branch_ids(pid) if i != pid and vp[i]["active"]]
    if not show_all:
        ids = [i for i in ids if vp[i]["stufe"] in C.NEWCOMER_STUFEN]
    ob = onboarding(ids)
    rows = [{"p": vp[i], "ob": ob[i]} for i in ids if i in ob]
    if not show_all:
        rows = [r for r in rows if r["ob"]["current"] is not None]
    rows.sort(key=lambda r: (not r["ob"]["stuck"], -r["ob"]["idle"]))
    return render_template("team_start.html", p=p, rows=rows, show_all=show_all)


# ================================================================= Наставничество: сводка по команде

@bp.route("/team/coaching")
@login_required
def team_coaching():
    pid = _pid_arg()
    p = get_person(pid)
    vp = visible_persons()
    scope = "branch" if request.args.get("scope") == "branch" else "direct"
    if scope == "direct":
        ids = [c["id"] for c in direct_children(pid) if c["active"]]
    else:
        ids = [i for i in branch_ids(pid) if i != pid and vp[i]["active"]]
    week = orga_default_week()
    last_week = monday(today()) - dt.timedelta(days=7)
    rows = []
    if ids:
        marks = ",".join("?" * len(ids))
        orga_rows = {}
        for r in query(f"""SELECT * FROM orga_checks WHERE person_id IN ({marks}) ORDER BY week DESC""", ids):
            orga_rows.setdefault(r["person_id"], []).append(r)
        refl = {}
        for r in query(f"""SELECT * FROM reflections WHERE person_id IN ({marks}) ORDER BY date DESC""", ids):
            refl.setdefault(r["person_id"], []).append(r)
        for i in ids:
            o = orga_rows.get(i, [])
            latest = o[0] if o else None
            sk = skills_of(latest)
            before = skills_of(o[1]) if len(o) > 1 else {}
            weakest = sorted(sk.items(), key=lambda kv: kv[1])[:2] if sk else []
            r = refl.get(i, [])
            nxt = next((x for x in r if x["next_date"]), None)
            rows.append({
                "p": vp[i], "orga": latest, "orga_week_done": any(x["week"] in (week.isoformat(), last_week.isoformat()) for x in o),
                "skills": sk, "before": before, "avg": round(sum(sk.values()) / len(sk), 1) if sk else None,
                "weakest": weakest, "refl_last": r[0] if r else None, "refl_count": len(r),
                "refl_next": parse_date(nxt["next_date"]) if nxt else None,
            })
    rows.sort(key=lambda x: (x["orga_week_done"], x["avg"] if x["avg"] is not None else -1))
    # средние оценки команды по навыкам
    team_avg = {}
    for key in C.ORGA_SKILL_KEYS:
        vals = [r["skills"][key] for r in rows if key in r["skills"]]
        team_avg[key] = round(sum(vals) / len(vals), 1) if vals else None
    return render_template("team_coaching.html", p=p, rows=rows, scope=scope, week=week, team_avg=team_avg,
                           has_branch=len(branch_ids(pid)) > len(direct_children(pid)) + 1)
