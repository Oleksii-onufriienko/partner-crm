"""Расчёт статистики. Все суммы в € считаются по коэффициенту каждого человека
(KE × коэффициент его ступени) и только потом складываются по структуре."""

import datetime as dt

from . import constants as C
from .db import query
from .util import MONTHS_NOM, fmt_date, month_bounds, monday, parse_date, plural, today

PERIODS = [
    ("week", "Эта неделя"),
    ("month", "Этот месяц"),
    ("prev_month", "Прошлый месяц"),
    ("next6w", "Следующие 6 недель"),
    ("quarter", "Квартал"),
    ("year", "Год"),
    ("custom", "Свой период"),
]

SUM_KEYS = ["contacts", "clients", "partner_interest", "new_contacts", "potential_ke",
            "planned", "done", "cancelled", "expected_ke", "deals", "deal_ke",
            "eur_deals", "eur_expected", "eur_potential", "coef_missing", "people"]


def period_from_args(args):
    key = args.get("period") or "month"
    t = today()
    if key == "week":
        start = monday(t)
        end = start + dt.timedelta(days=6)
    elif key == "prev_month":
        start, end = month_bounds(t.replace(day=1) - dt.timedelta(days=1))
    elif key == "next6w":
        start = monday(t)
        end = start + dt.timedelta(days=41)
    elif key == "quarter":
        q0 = (t.month - 1) // 3 * 3 + 1
        start = t.replace(month=q0, day=1)
        end = month_bounds(t.replace(month=q0 + 2, day=1))[1]
    elif key == "year":
        start, end = t.replace(month=1, day=1), t.replace(month=12, day=31)
    elif key == "custom":
        start = parse_date(args.get("from")) or t.replace(day=1)
        end = parse_date(args.get("to")) or t
        if end < start:
            start, end = end, start
    else:
        key = "month"
        start, end = month_bounds(t)

    if key == "month" or key == "prev_month":
        label = f"{MONTHS_NOM[start.month - 1].capitalize()} {start.year}"
    else:
        label = f"{fmt_date(start, 'dmy')} – {fmt_date(end, 'dmy')}"
    return key, start, end, label


def _empty():
    m = {k: 0 for k in SUM_KEYS}
    m["stage_done"] = {s[0]: 0 for s in C.STAGES}
    m["temps"] = {t[0]: 0 for t in C.TEMPERATURES}
    return m


def compute(persons, start, end):
    """persons: iterable строк persons. Возвращает {person_id: метрики} — лично по каждому."""
    persons = list(persons)
    if not persons:
        return {}
    ids = [p["id"] for p in persons]
    marks = ",".join("?" * len(ids))
    s, e = start.isoformat(), end.isoformat()
    res = {pid: _empty() for pid in ids}

    for r in query(f"""SELECT owner_id, COUNT(*) n,
                              SUM(kind = 'client') clients,
                              SUM(partner_interest) pi,
                              SUM(date(created_at) BETWEEN ? AND ?) new_n
                       FROM contacts WHERE owner_id IN ({marks}) GROUP BY owner_id""", [s, e, *ids]):
        m = res[r["owner_id"]]
        m["contacts"], m["clients"] = r["n"], r["clients"] or 0
        m["partner_interest"], m["new_contacts"] = r["pi"] or 0, r["new_n"] or 0

    for r in query(f"""SELECT owner_id, temperature, COUNT(*) n FROM contacts
                       WHERE owner_id IN ({marks}) GROUP BY owner_id, temperature""", ids):
        if r["temperature"] in res[r["owner_id"]]["temps"]:
            res[r["owner_id"]]["temps"][r["temperature"]] = r["n"]

    # Потенциал — только по тем, кто ещё не «нет шансов»
    for r in query(f"""SELECT c.owner_id, SUM(p.ke) ke FROM potentials p
                       JOIN contacts c ON c.id = p.contact_id
                       WHERE c.owner_id IN ({marks}) AND c.status != 'no_chance'
                       GROUP BY c.owner_id""", ids):
        res[r["owner_id"]]["potential_ke"] = r["ke"] or 0

    for r in query(f"""SELECT owner_id,
                              SUM(status != 'cancelled') planned,
                              SUM(status = 'done') done,
                              SUM(status = 'cancelled') cancelled,
                              SUM(CASE WHEN status != 'cancelled' THEN COALESCE(expected_ke, 0) END) exp_ke
                       FROM meetings
                       WHERE owner_id IN ({marks}) AND date BETWEEN ? AND ? AND format != 'private'
                       GROUP BY owner_id""", [*ids, s, e]):
        m = res[r["owner_id"]]
        m["planned"], m["done"], m["cancelled"] = r["planned"] or 0, r["done"] or 0, r["cancelled"] or 0
        m["expected_ke"] = r["exp_ke"] or 0

    for r in query(f"""SELECT owner_id, stage, COUNT(*) n FROM meetings
                       WHERE owner_id IN ({marks}) AND date BETWEEN ? AND ?
                             AND status = 'done' AND format != 'private'
                       GROUP BY owner_id, stage""", [*ids, s, e]):
        if r["stage"] in res[r["owner_id"]]["stage_done"]:
            res[r["owner_id"]]["stage_done"][r["stage"]] = r["n"]

    for r in query(f"""SELECT c.owner_id, COUNT(*) n, SUM(d.ke) ke FROM deals d
                       JOIN contacts c ON c.id = d.contact_id
                       WHERE c.owner_id IN ({marks}) AND d.date BETWEEN ? AND ?
                       GROUP BY c.owner_id""", [*ids, s, e]):
        res[r["owner_id"]]["deals"], res[r["owner_id"]]["deal_ke"] = r["n"], r["ke"] or 0

    for p in persons:
        m = res[p["id"]]
        m["people"] = 1
        coef = p["coef"]
        if coef is None:
            m["coef_missing"] = 1
            coef = 0
        m["eur_deals"] = m["deal_ke"] * coef
        m["eur_expected"] = m["expected_ke"] * coef
        m["eur_potential"] = m["potential_ke"] * coef
    return res


def combine(metric_dicts):
    total = _empty()
    for m in metric_dicts:
        for k in SUM_KEYS:
            total[k] += m[k]
        for k, v in m["stage_done"].items():
            total["stage_done"][k] += v
        for k, v in m["temps"].items():
            total["temps"][k] += v
    return total


def rate(part, whole):
    return round(100 * part / whole) if whole else None


def signals(persons):
    """Слабые места на сегодня: {person_id: [текст, ...]}."""
    persons = list(persons)
    if not persons:
        return {}
    ids = [p["id"] for p in persons]
    marks = ",".join("?" * len(ids))
    t = today()
    past = (t - dt.timedelta(days=C.NO_ACTIVITY_DAYS)).isoformat()
    future = (t + dt.timedelta(days=C.EMPTY_PLAN_DAYS)).isoformat()
    done_recent = {r["owner_id"]: r["n"] for r in query(
        f"""SELECT owner_id, COUNT(*) n FROM meetings WHERE owner_id IN ({marks})
            AND status = 'done' AND format != 'private' AND date BETWEEN ? AND ?
            GROUP BY owner_id""", [*ids, past, t.isoformat()])}
    planned_ahead = {r["owner_id"]: r["n"] for r in query(
        f"""SELECT owner_id, COUNT(*) n FROM meetings WHERE owner_id IN ({marks})
            AND status = 'planned' AND format != 'private' AND date BETWEEN ? AND ?
            GROUP BY owner_id""", [*ids, t.isoformat(), future])}
    contacts_n = {r["owner_id"]: r["n"] for r in query(
        f"SELECT owner_id, COUNT(*) n FROM contacts WHERE owner_id IN ({marks}) GROUP BY owner_id", ids)}
    overdue = {r["owner_id"]: r["n"] for r in query(
        f"""SELECT owner_id, COUNT(*) n FROM contacts WHERE owner_id IN ({marks})
            AND next_action_date IS NOT NULL AND next_action_date < ? AND status != 'no_chance'
            GROUP BY owner_id""", [*ids, t.isoformat()])}
    stale_planned = {r["owner_id"]: r["n"] for r in query(
        f"""SELECT owner_id, COUNT(*) n FROM meetings WHERE owner_id IN ({marks})
            AND status = 'planned' AND format != 'private' AND date < ?
            GROUP BY owner_id""", [*ids, t.isoformat()])}

    out = {}
    for p in persons:
        pid, lst = p["id"], []
        if not p["active"]:
            out[pid] = lst
            continue
        if not done_recent.get(pid):
            lst.append(f"Нет проведённых встреч за {C.NO_ACTIVITY_DAYS} дней")
        if not planned_ahead.get(pid):
            lst.append(f"Пустой план на {C.EMPTY_PLAN_DAYS} дней вперёд")
        n = contacts_n.get(pid, 0)
        if n < C.MIN_MARKTPOTENZIAL:
            lst.append(f"В Marktpotenzial {n} {plural(n, 'человек', 'человека', 'человек')} — "
                       f"меньше минимума ({C.MIN_MARKTPOTENZIAL})")
        if overdue.get(pid):
            lst.append(f"Просрочено напоминаний: {overdue[pid]}")
        if stale_planned.get(pid):
            lst.append(f"Не отмечен итог прошедших встреч: {stale_planned[pid]}")
        if p["coef"] is None:
            lst.append("Не указан коэффициент €/KE")
        out[pid] = lst
    return out


# Ряды для графика активности: (ключ, подпись)
SERIES = [
    ("new_contacts", "Новые контакты"),
    ("first", "Первый термин"),
    ("analysis", "Анализ"),
    ("consult", "Бератунг"),
    ("closing", "Заключение сделки"),
    ("deals", "Оформленные сделки"),
]


def _bucket_key(d, mode):
    if mode == "day":
        return d
    if mode == "week":
        return d - dt.timedelta(days=d.weekday())
    return d.replace(day=1)


def activity_series(ids, start, end):
    """Активность по дням (до 3 месяцев), по неделям (до ~13 месяцев) или по месяцам.
    Возвращает {"mode", "labels": [iso], "series": [{"key", "label", "values"}]}."""
    days = (end - start).days + 1
    mode = "day" if days <= 92 else ("week" if days <= 400 else "month")
    buckets = []
    d = _bucket_key(start, mode)
    while d <= end:
        buckets.append(d)
        if mode == "day":
            d += dt.timedelta(days=1)
        elif mode == "week":
            d += dt.timedelta(days=7)
        else:
            d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    index = {b: i for i, b in enumerate(buckets)}
    values = {k: [0] * len(buckets) for k, _ in SERIES}

    def add(key, date_str):
        dd = parse_date(date_str)
        if dd is None or dd < start or dd > end:
            return
        i = index.get(_bucket_key(dd, mode))
        if i is not None:
            values[key][i] += 1

    if ids:
        marks = ",".join("?" * len(ids))
        s, e = start.isoformat(), end.isoformat()
        for r in query(f"""SELECT date(created_at) d FROM contacts
                           WHERE owner_id IN ({marks}) AND date(created_at) BETWEEN ? AND ?""", [*ids, s, e]):
            add("new_contacts", r["d"])
        for r in query(f"""SELECT stage, date FROM meetings
                           WHERE owner_id IN ({marks}) AND status = 'done' AND format != 'private'
                                 AND stage IN ('first', 'analysis', 'consult', 'closing')
                                 AND date BETWEEN ? AND ?""", [*ids, s, e]):
            add(r["stage"], r["date"])
        for r in query(f"""SELECT d.date FROM deals d JOIN contacts c ON c.id = d.contact_id
                           WHERE c.owner_id IN ({marks}) AND d.date BETWEEN ? AND ?""", [*ids, s, e]):
            add("deals", r["date"])

    # Дни, которые ещё не наступили, — без значения: линия обрывается на сегодняшнем дне
    t = today()
    for k in values:
        values[k] = [None if b > t else v for b, v in zip(buckets, values[k])]
    return {"mode": mode, "labels": [b.isoformat() for b in buckets],
            "series": [{"key": k, "label": lbl, "values": values[k],
                        "total": sum(v for v in values[k] if v)} for k, lbl in SERIES]}
