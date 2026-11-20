"""Расчёт статистики. Все суммы в € считаются по коэффициенту каждого человека
(KE × коэффициент его ступени) и только потом складываются по структуре."""

import datetime as dt
import json

from flask import g

from . import constants as C
from .db import execute, query
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


class Signal(str):
    """Текст сигнала, который помнит, по какому признаку он сработал (.key)."""
    def __new__(cls, key, text):
        obj = str.__new__(cls, text)
        obj.key = key
        return obj


def weak_defaults():
    return {"match": "any",
            "rules": {key: {"on": True, "n": dflt} for key, _, _, dflt, *_ in C.WEAK_RULES}}


def _user_prefs():
    user = getattr(g, "user", None)
    if not user or "prefs" not in user.keys() or not user["prefs"]:
        return {}
    try:
        data = json.loads(user["prefs"])
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def weak_settings():
    """Настройки слабых мест текущего пользователя (с проверкой значений)."""
    s = weak_defaults()
    saved = _user_prefs().get("weak") or {}
    if saved.get("match") in ("any", "all"):
        s["match"] = saved["match"]
    for key, _, after, dflt, lo, hi, _ in C.WEAK_RULES:
        r = (saved.get("rules") or {}).get(key) or {}
        if isinstance(r.get("on"), bool):
            s["rules"][key]["on"] = r["on"]
        if dflt is not None and isinstance(r.get("n"), int) and lo <= r["n"] <= hi:
            s["rules"][key]["n"] = r["n"]
    return s


def save_weak_settings(settings):
    prefs = _user_prefs()
    if settings is None:
        prefs.pop("weak", None)
    else:
        prefs["weak"] = settings
    execute("UPDATE persons SET prefs = ? WHERE id = ?", (json.dumps(prefs, ensure_ascii=False), g.user["id"]))


def weak_settings_from_form(form):
    from .util import parse_int
    s = weak_defaults()
    s["match"] = form.get("match") if form.get("match") in ("any", "all") else "any"
    for key, _, after, dflt, lo, hi, _ in C.WEAK_RULES:
        s["rules"][key]["on"] = form.get(f"w_{key}") == "1"
        if dflt is not None:
            n = parse_int(form.get(f"n_{key}"))
            s["rules"][key]["n"] = min(max(n, lo), hi) if n is not None else dflt
    return s


def signals(persons, settings=None, all_rules=False):
    """Слабые места на сегодня: {person_id: [Signal, ...]}.
    Учитываются только включённые признаки (all_rules=True — все, для счётчиков)."""
    persons = list(persons)
    if not persons:
        return {}
    settings = settings or weak_settings()
    rules = settings["rules"]
    on = {k: (all_rules or rules[k]["on"]) for k in C.WEAK_RULE_KEYS}
    ids = [p["id"] for p in persons]
    marks = ",".join("?" * len(ids))
    t = today()
    past = (t - dt.timedelta(days=rules["no_activity"]["n"])).isoformat()
    future = (t + dt.timedelta(days=rules["empty_plan"]["n"])).isoformat()
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
    week = (t - dt.timedelta(days=t.weekday())).isoformat()
    has_week_plan = {r["person_id"] for r in query(
        f"""SELECT DISTINCT person_id FROM week_plan WHERE person_id IN ({marks})
            AND week = ? AND soll IS NOT NULL""", [*ids, week])}

    last_week = (t - dt.timedelta(days=t.weekday() + 7)).isoformat()
    has_orga = {r["person_id"] for r in query(
        f"""SELECT DISTINCT person_id FROM orga_checks WHERE person_id IN ({marks}) AND week >= ?""",
        [*ids, last_week])}

    out = {}
    for p in persons:
        pid, lst = p["id"], []
        if not p["active"]:
            out[pid] = lst
            continue
        if on["no_activity"] and not done_recent.get(pid):
            lst.append(Signal("no_activity", f"Нет проведённых встреч за {rules['no_activity']['n']} "
                                             f"{plural(rules['no_activity']['n'], 'день', 'дня', 'дней')}"))
        if on["empty_plan"] and not planned_ahead.get(pid):
            lst.append(Signal("empty_plan", f"Пустой план на {rules['empty_plan']['n']} "
                                            f"{plural(rules['empty_plan']['n'], 'день', 'дня', 'дней')} вперёд"))
        n, minimum = contacts_n.get(pid, 0), rules["low_potential"]["n"]
        if on["low_potential"] and n < minimum:
            lst.append(Signal("low_potential", f"В Marktpotenzial {n} {plural(n, 'человек', 'человека', 'человек')}"
                                               f" — меньше минимума ({minimum})"))
        if on["overdue"] and overdue.get(pid, 0) >= rules["overdue"]["n"]:
            lst.append(Signal("overdue", f"Просрочено напоминаний: {overdue[pid]}"))
        if on["stale"] and stale_planned.get(pid, 0) >= rules["stale"]["n"]:
            lst.append(Signal("stale", f"Не отмечен итог прошедших встреч: {stale_planned[pid]}"))
        if on["no_week_plan"] and pid not in has_week_plan:
            lst.append(Signal("no_week_plan", "Не заполнен план на эту неделю"))
        if on["no_orga"] and pid not in has_orga:
            lst.append(Signal("no_orga", "Не подготовился к ORGA за прошлую неделю"))
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
