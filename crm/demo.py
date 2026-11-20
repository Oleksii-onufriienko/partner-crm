"""Помощники для демо- и тестовых данных (используются seed_demo.py и seed_test_structure.py)."""
import datetime as dt

from .plan import AUTO, month_weeks

# Типичный план на неделю для бетроера (для VM масштабируется вниз)
WEEK_SOLL = {
    "fa_contacts": (12, 30), "fa_agreed": (3, 8), "fa_held": (2, 6), "fa_created": (1, 4),
    "fa_referrals": (4, 12), "fa_recruit": (0, 2), "fa_interest": (0, 2),
    "br_agreed": (2, 4), "br_held": (1, 3), "br_clients": (1, 2), "br_ke": (20, 60),
    "br_referrals": (2, 5), "br_recruit": (0, 1), "br_interest": (0, 1),
    "st_agreed": (1, 2), "st_held": (1, 2), "st_ke": (8, 20),
    "st_referrals": (1, 3), "st_recruit": (0, 1), "st_interest": (0, 1),
    "aw_contacts": (3, 8), "aw_interest": (1, 3),
}


def add_week_plans(db, person_id, rnd, scale=1.0, today=None):
    """План (одинаковый на все недели месяца) на прошлый, текущий и следующий месяц
    и ручной факт по прошедшим неделям для показателей, которые не считаются сами."""
    today = today or dt.date.today()
    first = today.replace(day=1)
    months = [(first - dt.timedelta(days=1)).replace(day=1), first,
              (first + dt.timedelta(days=32)).replace(day=1)]
    for m in months:
        soll = {}
        for key, (lo, hi) in WEEK_SOLL.items():
            v = round(rnd.uniform(lo, hi) * scale)
            if key.endswith("_ke"):
                v = round(rnd.uniform(lo, hi) * scale / 5) * 5
            soll[key] = v
        for w in month_weeks(m.year, m.month):
            ended = w + dt.timedelta(days=6) < today
            for key, s in soll.items():
                ist = None
                if ended and key not in AUTO:
                    ist = max(0, round(s * rnd.uniform(0.3, 1.4)))
                db.execute("""INSERT OR REPLACE INTO week_plan (person_id, week, metric, soll, ist)
                              VALUES (?, ?, ?, ?, ?)""", (person_id, w.isoformat(), key, s, ist))
