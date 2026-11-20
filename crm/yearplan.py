"""Годовой план — как Jahresplanung в Erfolgsjournal: цели по месяцам и факт из CRM.

Факт:
  единицы Eigen   — KE сделок самого человека за месяц;
  единицы Gruppe  — KE сделок всех людей ниже него в структуре;
  кандидаты       — контакты, ставшие кандидатами (этап «Интерес») в этом месяце: лично / у людей ниже;
  новые VM        — люди, вошедшие в структуру в этом месяце (дата входа): напрямую / в глубине;
  повышения       — записи в истории ступеней: до VBAK/VBAS и до AL, напрямую / в глубине.
"""
import datetime as dt

from .db import get_db, query
from .util import parse_date, parse_float

BLOCKS = [
    ("units", "Оборот, единицы"),
    ("direct", "Построение структуры: напрямую"),
    ("indirect", "Построение структуры: в глубину"),
]
# ключ, блок, подпись, термин из Erfolgsjournal, цель вводится вручную (False — считается из других строк)
METRICS = [
    ("eigen", "units", "Единицы лично", "Einheiten (Eigen)", True),
    ("gruppe", "units", "Единицы группы", "Einheiten (Gruppe)", True),
    ("gesamt", "units", "Единицы всего", "Einheiten (Gesamt)", False),
    ("cand_direct", "direct", "Новые кандидаты лично", "Berufsinteressenten", True),
    ("vm_direct", "direct", "Новые VM", "VM-Einstellungen (direkt)", True),
    ("vba_direct", "direct", "Повышения до VBA", "VBA-Beförderungen (direkt)", True),
    ("al_direct", "direct", "Повышения до AL", "AL-Beförderungen (direkt)", True),
    ("cand_indirect", "indirect", "Кандидаты в структуре", "Berufsinteressenten (indirekt)", True),
    ("vm_indirect", "indirect", "Новые VM", "VM-Einstellungen (indirekt)", True),
    ("vba_indirect", "indirect", "Повышения до VBA", "VBA-Beförderungen (indirekt)", True),
    ("al_indirect", "indirect", "Повышения до AL", "AL-Beförderungen (indirekt)", True),
]
KEYS = [m[0] for m in METRICS]
EDITABLE = [m[0] for m in METRICS if m[4]]
UNIT_KEYS = ("eigen", "gruppe", "gesamt")
VBA_STUFEN = ("VBAK", "VBAS")


def _branch(pid, children):
    out, stack = [], [(pid, 0)]
    while stack:
        cur, depth = stack.pop()
        out.append((cur, depth))
        stack.extend((c["id"], depth + 1) for c in children.get(cur, []))
    return out


def facts(pid, year, persons, children):
    """{показатель: [12 значений]} — факт по месяцам года."""
    res = {k: [0.0] * 12 for k in KEYS}
    tree = _branch(pid, children)
    depth = dict(tree)
    ids = [i for i, _ in tree]
    marks = ",".join("?" * len(ids))
    s, e = f"{year}-01-01", f"{year}-12-31"

    def add(key, date_str, value=1):
        d = parse_date(date_str)
        if d and d.year == year:
            res[key][d.month - 1] += value

    for r in query(f"""SELECT c.owner_id, d.date, d.ke FROM deals d JOIN contacts c ON c.id = d.contact_id
                       WHERE c.owner_id IN ({marks}) AND d.date BETWEEN ? AND ?""", [*ids, s, e]):
        add("eigen" if r["owner_id"] == pid else "gruppe", r["date"], r["ke"] or 0)
    for r in query(f"""SELECT c.owner_id, l.date FROM recruit_log l JOIN contacts c ON c.id = l.contact_id
                       WHERE c.owner_id IN ({marks}) AND l.stage = 'interest' AND l.date BETWEEN ? AND ?""",
                   [*ids, s, e]):
        add("cand_direct" if r["owner_id"] == pid else "cand_indirect", r["date"])
    for i in ids:
        if i == pid:
            continue
        p = persons.get(i)
        if p is None:
            continue
        joined = p["start_date"] or (p["created_at"] or "")[:10]
        add("vm_direct" if depth[i] == 1 else "vm_indirect", joined)
    for r in query(f"""SELECT person_id, stufe, date FROM stufe_history
                       WHERE person_id IN ({marks}) AND kind = 'promotion' AND date BETWEEN ? AND ?""",
                   [*ids, s, e]):
        if r["person_id"] == pid:
            continue
        side = "direct" if depth[r["person_id"]] == 1 else "indirect"
        if r["stufe"] in VBA_STUFEN:
            add(f"vba_{side}", r["date"])
        elif r["stufe"] == "AL":
            add(f"al_{side}", r["date"])
    for m in range(12):
        res["gesamt"][m] = res["eigen"][m] + res["gruppe"][m]
    return res


def goals(pid, year):
    res = {k: [None] * 12 for k in KEYS}
    for r in query("SELECT month, metric, ziel FROM year_goals WHERE person_id = ? AND year = ?", (pid, year)):
        if r["metric"] in res and 1 <= r["month"] <= 12:
            res[r["metric"]][r["month"] - 1] = r["ziel"]
    for m in range(12):
        e, g = res["eigen"][m], res["gruppe"][m]
        res["gesamt"][m] = None if e is None and g is None else (e or 0) + (g or 0)
    return res


def save(pid, year, form, user_id):
    db = get_db()
    for key in EDITABLE:
        for m in range(1, 13):
            v = parse_float(form.get(f"g_{key}_{m}"))
            if v is None or v < 0:
                db.execute("DELETE FROM year_goals WHERE person_id = ? AND year = ? AND month = ? AND metric = ?",
                           (pid, year, m, key))
            else:
                db.execute("""INSERT INTO year_goals (person_id, year, month, metric, ziel, updated_by, updated_at)
                              VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                              ON CONFLICT(person_id, year, month, metric) DO UPDATE SET
                                ziel = excluded.ziel, updated_by = excluded.updated_by, updated_at = excluded.updated_at""",
                           (pid, year, m, key, v, user_id))
    db.commit()


def _sum(values):
    vals = [v for v in values if v is not None]
    return sum(vals) if vals else None


def view(ist, ziel, year, today):
    """Строки таблицы: месяцы с итогами кварталов и года."""
    cols = []
    for q in range(4):
        for m in range(q * 3, q * 3 + 3):
            cols.append({"kind": "month", "m": m})
        cols.append({"kind": "quarter", "q": q})
    cols.append({"kind": "year"})
    cur = (today.year, today.month)
    blocks = []
    for bkey, blabel in BLOCKS:
        rows = []
        for key, block, label, de, editable in METRICS:
            if block != bkey:
                continue
            cells = []
            for c in cols:
                if c["kind"] == "month":
                    idx = [c["m"]]
                elif c["kind"] == "quarter":
                    idx = list(range(c["q"] * 3, c["q"] * 3 + 3))
                else:
                    idx = list(range(12))
                z = _sum(ziel[key][i] for i in idx)
                fact_months = [i for i in idx if (year, i + 1) <= cur]
                v = sum(ist[key][i] for i in idx) if fact_months or (year, idx[0] + 1) <= cur else None
                state = ""
                if z and v is not None:
                    last = idx[-1]
                    ended = (year, last + 1) < cur
                    if v >= z:
                        state = "hit"
                    elif ended:
                        state = "miss"
                cells.append({"kind": c["kind"], "ziel": z, "ist": v, "state": state,
                              "now": c["kind"] == "month" and (year, c["m"] + 1) == cur})
            rows.append({"key": key, "label": label, "de": de, "cells": cells, "units": key in UNIT_KEYS,
                         "editable": editable})
        blocks.append({"key": bkey, "label": blabel, "rows": rows})
    return cols, blocks
