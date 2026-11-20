"""План/факт (Soll/Ist) по неделям — как Wochenplanung в Erfolgsjournal.

Факт по встречам и сделкам считается автоматически:
  контакты для первого термина = проведённые встречи этапа «Холодный контакт» / «Контактный разговор»
    и звонки из режима обзвона, где разговор состоялся (термин, перезвонить, нет шансов);
  договорено … = встречи этого этапа, созданные (назначенные) на этой неделе;
  проведено … = встречи этого этапа со статусом «Проведена» и датой на этой неделе;
  финанализы = проведённые встречи этапа «Анализ»;
  бератунги = этапы «Бератунг» и «Заключение сделки»;
  новые клиенты = контакты, у которых первая сделка пришлась на эту неделю;
  KE из бератунгов / сервиса = сделки недели по источнику.
Остальное (рекомендации, карьерные разговоры, интерес к профессии) вносится вручную.
Автоматический факт можно поправить вручную — тогда используется ручное значение.
"""
import datetime as dt

from . import constants as C
from .db import get_db, query
from .util import MONTHS_GEN, parse_date, today

AUTO = {m[0] for m in C.PLAN_METRICS if m[4]}
HELD_STAGE = {"cold": "fa_contacts", "contact": "fa_contacts", "first": "fa_held",
              "analysis": "fa_created", "consult": "br_held", "closing": "br_held", "service": "st_held"}
AGREED_STAGE = {"first": "fa_agreed", "consult": "br_agreed", "closing": "br_agreed", "service": "st_agreed"}


def week_of(d):
    return d - dt.timedelta(days=d.weekday())


def month_weeks(year, month):
    """Недели месяца — те, чей понедельник приходится на этот месяц (4 или 5 недель)."""
    d = dt.date(year, month, 1)
    w = d + dt.timedelta(days=(7 - d.weekday()) % 7)
    weeks = []
    while w.month == month:
        weeks.append(w)
        w += dt.timedelta(days=7)
    return weeks


def week_label(w):
    e = w + dt.timedelta(days=6)
    m1, m2 = MONTHS_GEN[w.month - 1][:3] + ".", MONTHS_GEN[e.month - 1][:3] + "."
    return f"{w.day}–{e.day} {m2}" if w.month == e.month else f"{w.day} {m1} – {e.day} {m2}"


def _marks(ids):
    return ",".join("?" * len(ids))


def auto_facts(ids, weeks):
    """{pid: {неделя: {показатель: значение}}} — факт из встреч и сделок."""
    res = {pid: {w.isoformat(): {k: 0 for k in AUTO} for w in weeks} for pid in ids}
    if not ids or not weeks:
        return res
    s, e = weeks[0].isoformat(), (weeks[-1] + dt.timedelta(days=6)).isoformat()
    mk = _marks(ids)

    def add(pid, date_str, metric, value=1):
        d = parse_date(date_str)
        if d is None:
            return
        wk = week_of(d).isoformat()
        if wk in res[pid]:
            res[pid][wk][metric] += value

    for r in query(f"""SELECT owner_id, stage, date FROM meetings
                       WHERE owner_id IN ({mk}) AND status = 'done' AND format != 'private'
                             AND date BETWEEN ? AND ?""", [*ids, s, e]):
        if r["stage"] in HELD_STAGE:
            add(r["owner_id"], r["date"], HELD_STAGE[r["stage"]])
    for r in query(f"""SELECT owner_id, stage, date(created_at) d FROM meetings
                       WHERE owner_id IN ({mk}) AND format != 'private'
                             AND date(created_at) BETWEEN ? AND ?""", [*ids, s, e]):
        if r["stage"] in AGREED_STAGE:
            add(r["owner_id"], r["d"], AGREED_STAGE[r["stage"]])
    # Звонки из режима обзвона, где разговор состоялся, — тоже контакты для первого термина
    reached = ",".join(f"'{k}'" for k in C.CALL_REACHED)
    for r in query(f"""SELECT owner_id, date FROM calls WHERE owner_id IN ({mk}) AND result IN ({reached})
                       AND date BETWEEN ? AND ?""", [*ids, s, e]):
        add(r["owner_id"], r["date"], "fa_contacts")
    for r in query(f"""SELECT c.owner_id, d.date, d.ke, d.source FROM deals d
                       JOIN contacts c ON c.id = d.contact_id
                       WHERE c.owner_id IN ({mk}) AND d.date BETWEEN ? AND ?""", [*ids, s, e]):
        add(r["owner_id"], r["date"], "st_ke" if r["source"] == "service" else "br_ke", r["ke"] or 0)
    for r in query(f"""SELECT c.owner_id, MIN(d.date) first_date FROM deals d
                       JOIN contacts c ON c.id = d.contact_id
                       WHERE c.owner_id IN ({mk})
                       GROUP BY d.contact_id HAVING first_date BETWEEN ? AND ?""", [*ids, s, e]):
        add(r["owner_id"], r["first_date"], "br_clients")
    return res


def stored(ids, weeks):
    out = {}
    if not ids or not weeks:
        return out
    wk = [w.isoformat() for w in weeks]
    for r in query(f"""SELECT person_id, week, metric, soll, ist FROM week_plan
                       WHERE person_id IN ({_marks(ids)}) AND week IN ({_marks(wk)})""", [*ids, *wk]):
        out.setdefault(r["person_id"], {}).setdefault(r["week"], {})[r["metric"]] = (r["soll"], r["ist"])
    return out


def grids(ids, weeks):
    """{pid: {неделя: {показатель: {soll, ist, auto, manual}}}}."""
    auto, st = auto_facts(ids, weeks), stored(ids, weeks)
    out = {}
    for pid in ids:
        out[pid] = {}
        for w in weeks:
            wk = w.isoformat()
            row = {}
            for key in C.PLAN_METRIC_KEYS:
                soll, ist_manual = st.get(pid, {}).get(wk, {}).get(key, (None, None))
                auto_v = auto[pid][wk][key] if key in AUTO else None
                ist = ist_manual if ist_manual is not None else auto_v
                row[key] = {"soll": soll, "ist": ist, "auto": auto_v, "manual": ist_manual is not None}
            out[pid][wk] = row
    return out


def _add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return a + b


def combine(grid_list, weeks):
    """Сумма нескольких людей (для ветки)."""
    total = {w.isoformat(): {k: {"soll": None, "ist": None, "auto": None, "manual": False}
                             for k in C.PLAN_METRIC_KEYS} for w in weeks}
    for g in grid_list:
        for wk, row in g.items():
            for k, cell in row.items():
                t = total[wk][k]
                t["soll"] = _add(t["soll"], cell["soll"])
                t["ist"] = _add(t["ist"], cell["ist"])
                t["manual"] = t["manual"] or cell["manual"]
    return total


def month_totals(grid, weeks):
    tot = {}
    for k in C.PLAN_METRIC_KEYS:
        soll = ist = None
        for w in weeks:
            c = grid[w.isoformat()][k]
            soll, ist = _add(soll, c["soll"]), _add(ist, c["ist"])
        tot[k] = {"soll": soll, "ist": ist}
    tot["ke"] = {"soll": _add(tot["br_ke"]["soll"], tot["st_ke"]["soll"]),
                 "ist": _add(tot["br_ke"]["ist"], tot["st_ke"]["ist"])}
    return tot


def pct(ist, soll):
    if not soll:
        return None
    return round(100 * (ist or 0) / soll)


def euros(person_grids, persons, weeks):
    """€ = KE × коэффициент каждого человека, затем сумма."""
    soll = ist = 0.0
    for pid, g in person_grids.items():
        coef = persons[pid]["coef"] or 0
        t = month_totals(g, weeks)["ke"]
        soll += (t["soll"] or 0) * coef
        ist += (t["ist"] or 0) * coef
    return {"soll": soll, "ist": ist}


def view(grid, weeks):
    """Строки для таблицы: блоки → показатели → ячейки по неделям + итог месяца."""
    t = today()
    week_state = []
    for w in weeks:
        end = w + dt.timedelta(days=6)
        week_state.append("past" if end < t else ("current" if w <= t else "future"))
    tot = month_totals(grid, weeks)
    blocks = []
    for bkey, blabel in C.PLAN_BLOCKS:
        rows = []
        for key, mblock, label, de, auto in C.PLAN_METRICS:
            if mblock != bkey:
                continue
            cells = []
            for w, state in zip(weeks, week_state):
                c = dict(grid[w.isoformat()][key])
                c["state"] = state
                c["mark"] = ""
                if c["soll"]:
                    if (c["ist"] or 0) >= c["soll"]:
                        c["mark"] = "hit"
                    elif state == "past":
                        c["mark"] = "miss"
                cells.append(c)
            total = dict(tot[key])
            total["pct"] = pct(total["ist"], total["soll"])
            rows.append({"key": key, "label": label, "de": de, "auto": auto, "cells": cells,
                         "total": total, "is_ke": key in C.PLAN_KE_METRICS})
        blocks.append({"key": bkey, "label": blabel, "rows": rows})
    summary = []
    for key, label in C.PLAN_SUMMARY:
        x = tot[key]
        summary.append({"key": key, "label": label, "soll": x["soll"], "ist": x["ist"],
                        "pct": pct(x["ist"], x["soll"])})
    return {"blocks": blocks, "summary": summary, "totals": tot, "week_state": week_state}


def quotas(tot):
    """Квоты как в Quoten-Auswertung Erfolgsjournal — по факту месяца."""
    def ratio(a, b):
        a, b = tot[a]["ist"] or 0, tot[b]["ist"] or 0
        return a / b if b else None

    return [
        ("договорённых первых терминов на один проведённый", ratio("fa_agreed", "fa_held")),
        ("проведённых первых терминов на один финанализ", ratio("fa_held", "fa_created")),
        ("финанализов на один бератунг", ratio("fa_created", "br_held")),
        ("бератунгов на одного нового клиента", ratio("br_held", "br_clients")),
        ("KE в среднем с одного нового клиента", ratio("br_ke", "br_clients")),
        ("рекомендаций с одного первого термина", ratio("fa_referrals", "fa_held")),
        ("рекомендаций с одного бератунга", ratio("br_referrals", "br_held")),
        ("рекомендаций с одного сервис-термина", ratio("st_referrals", "st_held")),
        ("KE с одного сервис-термина", ratio("st_ke", "st_held")),
    ]


def save(person_id, weeks, form, user_id):
    """Сохраняет форму ввода: s_<показатель>_<неделя> — план, i_<показатель>_<неделя> — факт."""
    from .util import parse_float
    db = get_db()
    for w in weeks:
        wk = w.isoformat()
        for key in C.PLAN_METRIC_KEYS:
            soll = parse_float(form.get(f"s_{key}_{wk}"))
            ist = parse_float(form.get(f"i_{key}_{wk}"))
            if soll is not None and soll < 0:
                soll = None
            if ist is not None and ist < 0:
                ist = None
            if soll is None and ist is None:
                db.execute("DELETE FROM week_plan WHERE person_id = ? AND week = ? AND metric = ?",
                           (person_id, wk, key))
            else:
                db.execute("""INSERT INTO week_plan (person_id, week, metric, soll, ist, updated_by, updated_at)
                              VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                              ON CONFLICT(person_id, week, metric) DO UPDATE SET
                                soll = excluded.soll, ist = excluded.ist,
                                updated_by = excluded.updated_by, updated_at = excluded.updated_at""",
                           (person_id, wk, key, soll, ist, user_id))
    db.commit()


def copy_previous(person_id, weeks, user_id):
    """План последней заполненной недели прошлого месяца → во все недели месяца, где плана ещё нет."""
    prev_end = weeks[0].replace(day=1) - dt.timedelta(days=1)
    prev_weeks = month_weeks(prev_end.year, prev_end.month)
    src = stored([person_id], prev_weeks).get(person_id, {})
    base = {}
    for w in reversed(prev_weeks):
        for key, (soll, _) in src.get(w.isoformat(), {}).items():
            if soll is not None and key not in base:
                base[key] = soll
    if not base:
        return 0
    existing = stored([person_id], weeks).get(person_id, {})
    db = get_db()
    n = 0
    for w in weeks:
        wk = w.isoformat()
        for key, soll in base.items():
            cur = existing.get(wk, {}).get(key)
            if cur and cur[0] is not None:
                continue
            db.execute("""INSERT INTO week_plan (person_id, week, metric, soll, ist, updated_by)
                          VALUES (?, ?, ?, ?, NULL, ?)
                          ON CONFLICT(person_id, week, metric) DO UPDATE SET soll = excluded.soll,
                            updated_by = excluded.updated_by, updated_at = datetime('now')""",
                       (person_id, wk, key, soll, user_id))
            n += 1
    db.commit()
    return n
