"""Воронка партнёров: кандидаты из Marktpotenzial и их этапы до входа в структуру."""
from . import constants as C
from .db import execute, query
from .util import today


def set_stage(contact, stage, user_id, when=None, info_date=None, joined_person_id=None):
    """Переводит контакт на этап воронки и пишет это в журнал."""
    if stage not in C.keys(C.RECRUIT_STAGES):
        return
    when = (when or today()).isoformat()
    sets, args = ["recruit_stage = ?", "partner_interest = 1", "updated_at = datetime('now')"], [stage]
    if info_date is not None:
        sets.append("recruit_info_date = ?")
        args.append(info_date or None)
    if joined_person_id is not None:
        sets.append("joined_person_id = ?")
        args.append(joined_person_id)
    if stage != contact["recruit_stage"]:
        execute("INSERT INTO recruit_log (contact_id, stage, date, created_by) VALUES (?, ?, ?, ?)",
                (contact["id"], stage, when, user_id))
    execute(f"UPDATE contacts SET {', '.join(sets)} WHERE id = ?", [*args, contact["id"]])


def candidates(owner_ids):
    """Все кандидаты этих людей с датой входа в текущий этап."""
    if not owner_ids:
        return []
    marks = ",".join("?" * len(owner_ids))
    return query(
        f"""SELECT c.*, p.first_name of, p.last_name ol,
               (SELECT MAX(date) FROM recruit_log l WHERE l.contact_id = c.id AND l.stage = c.recruit_stage) since,
               (SELECT MIN(date) FROM recruit_log l WHERE l.contact_id = c.id) first_seen
            FROM contacts c JOIN persons p ON p.id = c.owner_id
            WHERE c.owner_id IN ({marks}) AND c.recruit_stage IS NOT NULL
            ORDER BY since DESC, c.last_name COLLATE NOCASE""", owner_ids)


def period_counts(owner_ids, start, end):
    """Сколько кандидатов вошло в каждый этап за период (по журналу)."""
    out = {k: 0 for k in C.keys(C.RECRUIT_STAGES)}
    if not owner_ids:
        return out
    marks = ",".join("?" * len(owner_ids))
    for r in query(f"""SELECT l.stage, COUNT(DISTINCT l.contact_id) n FROM recruit_log l
                       JOIN contacts c ON c.id = l.contact_id
                       WHERE c.owner_id IN ({marks}) AND l.date BETWEEN ? AND ?
                       GROUP BY l.stage""", [*owner_ids, start.isoformat(), end.isoformat()]):
        out[r["stage"]] = r["n"]
    return out


def reached_counts(owner_ids):
    """Сколько кандидатов когда-либо дошло до каждого этапа (для конверсии воронки)."""
    order = ["interest", "invited", "attended", "talk", "joined"]
    out = {k: 0 for k in order}
    if not owner_ids:
        return out
    marks = ",".join("?" * len(owner_ids))
    rows = query(f"""SELECT c.id, c.recruit_stage, GROUP_CONCAT(l.stage) stages FROM contacts c
                     LEFT JOIN recruit_log l ON l.contact_id = c.id
                     WHERE c.owner_id IN ({marks}) AND c.recruit_stage IS NOT NULL
                     GROUP BY c.id""", owner_ids)
    for r in rows:
        stages = set((r["stages"] or "").split(",")) | {r["recruit_stage"]}
        top = max((order.index(s) for s in stages if s in order), default=0)
        for i in range(top + 1):
            out[order[i]] += 1
    return out
