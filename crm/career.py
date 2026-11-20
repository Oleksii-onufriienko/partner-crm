"""Путь до следующей ступени по «Leistung lohnt sich 2026» (Beförderungsbedingungen).

Что берём из CRM:
  единицы = KE оформленных сделок (сторно пока не учитывается, поэтому Netto ≈ сумма сделок);
  Eigen   = сделки самого человека; Gruppe = сделки всех людей ниже него в структуре;
  Gesamt  = Eigen (не больше лимита «Netto Eigen max») + Gruppe;
  neue Partner (36/12) = единицы за 12 месяцев людей ниже, которые вошли в бизнес не раньше 36 месяцев назад;
  «с последнего повышения» — по истории ступеней.
Периоды всегда последние: 3 / 12 / 36 месяцев назад от сегодняшней даты.
"""
import datetime as dt

from . import constants as C
from .db import query
from .util import parse_date, today

# Karriereweg Team (Hauptberuf): цель → условия (единицы за последние 12 месяцев)
TEAM_RULES = {
    "RGS": {"gesamt": 4000, "eigen_max": 2400, "np": 1600, "eigen_min": 1800},
    "GS": {"gesamt": 8000, "eigen_max": 4000, "np": 3000, "eigen_min": 1800},
    "HGS": {"gesamt": 16000, "eigen_max": 4000, "np": 3500, "eigen_min": 1800},
    "RD1": {"gesamt": 32000, "eigen_max": 5000, "np": 4000},
    "RD2": {"gesamt": 48000, "eigen_max": 6000, "np": 5000},
    "D": {"gesamt": 68000, "eigen_max": 8000, "np": 9000},
}
TEAM_PATH = ["AL", "RGS", "GS", "HGS", "RD1", "RD2", "D"]
# Karriereweg Praxis: Netto Neu Eigen за 12 месяцев и с последнего повышения
PRAXIS_RULES = {"P2": (2400, 4800), "P3": (3000, 6000), "P4": (3600, 7200),
                "P5": (4200, 8400), "P6": (4800, 12000), "P7": (5400, 15000)}
PRAXIS_PATH = ["AL", "P2", "P3", "P4", "P5", "P6", "P7"]
AL_UNITS = 600                          # Netto Gesamt за последние 3 месяца
VBAK_UNITS, VBAK_UNITS_VM, VBAK_VM = 450, 300, 2
NEW_PARTNER_MONTHS = 36


def next_targets(stufe):
    if stufe in ("VM", "VBAS"):
        return ["VBAK"]
    if stufe == "VBAK":
        return ["AL"]
    if stufe == "AL":
        return ["RGS", "P2"]
    if stufe in TEAM_PATH[1:-1]:
        return [TEAM_PATH[TEAM_PATH.index(stufe) + 1]]
    if stufe in PRAXIS_PATH[1:-1]:
        return [PRAXIS_PATH[PRAXIS_PATH.index(stufe) + 1]]
    return []


def months_ago(t, n):
    """Та же дата n месяцев назад (31-е → последний день короткого месяца)."""
    y, m = divmod(t.year * 12 + t.month - 1 - n, 12)
    m += 1
    for day in (t.day, 30, 29, 28):
        try:
            return dt.date(y, m, day)
        except ValueError:
            continue


def facts(person_ids, persons, children):
    """Факты для расчёта по каждому человеку. persons: {id: row}, children: {id: [row, ...]}."""
    t = today()
    # Всегда последние месяцы, считая назад от сегодня: 12 месяцев, 3 месяца, 36 месяцев
    y1 = months_ago(t, 12)
    m3 = months_ago(t, 3)
    np_since = months_ago(t, NEW_PARTNER_MONTHS)

    # Все сделки людей, которые встречаются в ветках этих людей
    def branch(pid):
        out, stack = [], [pid]
        while stack:
            cur = stack.pop()
            out.append(cur)
            stack.extend(c["id"] for c in children.get(cur, []))
        return out

    branches = {pid: branch(pid) for pid in person_ids}
    all_ids = sorted({i for b in branches.values() for i in b})
    deals = {}
    if all_ids:
        marks = ",".join("?" * len(all_ids))
        for r in query(f"""SELECT c.owner_id, d.date, d.ke FROM deals d JOIN contacts c ON c.id = d.contact_id
                           WHERE c.owner_id IN ({marks})""", all_ids):
            deals.setdefault(r["owner_id"], []).append((parse_date(r["date"]), r["ke"] or 0))
    last_change = {}
    if person_ids:
        marks = ",".join("?" * len(person_ids))
        for r in query(f"""SELECT person_id, MAX(date) d FROM stufe_history
                           WHERE person_id IN ({marks}) AND kind != 'start' GROUP BY person_id""", list(person_ids)):
            last_change[r["person_id"]] = parse_date(r["d"])

    def joined(pid):
        p = persons.get(pid)
        if p is None:
            return None
        return parse_date(p["start_date"]) or parse_date((p["created_at"] or "")[:10])

    out = {}
    for pid in person_ids:
        own = deals.get(pid, [])
        since = last_change.get(pid) or joined(pid) or dt.date(1970, 1, 1)
        f = {
            "eigen_all": sum(k for d, k in own),
            "eigen_12": sum(k for d, k in own if d and d > y1),
            "eigen_since": sum(k for d, k in own if d and d >= since),
            "since": since,
            "gruppe_12": 0.0, "np_12": 0.0,
            "direct_partners": sum(1 for c in children.get(pid, []) if c["active"]),
        }
        f["last3"] = 0.0
        for oid in branches[pid]:
            is_new = oid != pid and (joined(oid) or dt.date(1970, 1, 1)) >= np_since
            for d, k in deals.get(oid, []):
                if d is None:
                    continue
                if oid != pid and d > y1:
                    f["gruppe_12"] += k
                    if is_new:
                        f["np_12"] += k
                if d > m3:
                    f["last3"] += k
        out[pid] = f
    return out


def _crit(label, value, target, unit="ед.", hint=None):
    pct = 100 if target <= 0 else min(100, round(100 * value / target))
    return {"label": label, "value": value, "target": target, "pct": pct, "ok": value >= target,
            "unit": unit, "hint": hint}


def plan_for(person, f):
    """Шаги к следующим ступеням: [{target, title, path, options: [[критерии]], pct, done}]."""
    m3 = months_ago(today(), 3)
    steps = []
    for target in next_targets(person["stufe"]):
        title = C.label(C.STUFEN, target)
        options, note, path = [], None, ""
        if target == "VBAK":
            options = [
                [_crit("Единиц подано всего", f["eigen_all"], VBAK_UNITS)],
                [_crit("Единиц подано всего", f["eigen_all"], VBAK_UNITS_VM),
                 _crit("VM в прямой структуре", f["direct_partners"], VBAK_VM, unit="чел.")],
            ]
            note = "Нужно одно из двух: 450 единиц или 300 единиц и 2 VM."
        elif target == "AL":
            options = [[_crit("Netto Gesamt за последние 3 месяца", f["last3"], AL_UNITS,
                              hint=f"с {(m3 + dt.timedelta(days=1)).strftime('%d.%m.%Y')}")]]
            note = "Переход в Hauptberuf: 600 единиц Netto Gesamt за 3 месяца подряд."
        elif target in TEAM_RULES:
            r = TEAM_RULES[target]
            path = "Team"
            gesamt = min(f["eigen_12"], r["eigen_max"]) + f["gruppe_12"]
            crit = [_crit(f"Netto Gesamt за 12 месяцев (собственные не больше {r['eigen_max']:,})".replace(",", " "),
                          gesamt, r["gesamt"]),
                    _crit("Единицы новых партнёров (36/12)", f["np_12"], r["np"])]
            if r.get("eigen_min"):
                crit.append(_crit("Netto Eigen за 12 месяцев", f["eigen_12"], r["eigen_min"]))
            options = [crit]
        elif target in PRAXIS_RULES:
            y12, since = PRAXIS_RULES[target]
            path = "Praxis"
            options = [[_crit("Netto Neu Eigen за 12 месяцев", f["eigen_12"], y12),
                        _crit("Netto Neu Eigen с последнего повышения", f["eigen_since"], since,
                              hint=f"с {f['since'].strftime('%d.%m.%Y')}")]]
        option_pcts = [min(c["pct"] for c in opt) for opt in options] if options else [0]
        best = max(range(len(options)), key=lambda i: option_pcts[i]) if options else 0
        steps.append({"target": target, "title": title, "path": path, "options": options, "best": best,
                      "pct": max(option_pcts), "done": any(all(c["ok"] for c in o) for o in options),
                      "note": note})
    return steps


def history(person_id):
    return query("SELECT * FROM stufe_history WHERE person_id = ? ORDER BY date DESC, id DESC", (person_id,))
