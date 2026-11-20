import calendar
import datetime as dt

from flask import request

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]
MONTHS_NOM = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль",
              "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
WEEKDAYS_FULL = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def today():
    return dt.date.today()


def parse_date(s):
    if not s:
        return None
    if isinstance(s, dt.date):
        return s
    try:
        return dt.date.fromisoformat(str(s).strip()[:10])
    except ValueError:
        return None


def parse_float(s):
    if s is None:
        return None
    s = str(s).strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_int(s):
    f = parse_float(s)
    return int(f) if f is not None else None


def clean(s, maxlen=300):
    s = (s or "").strip()
    return s[:maxlen] if s else None


def monday(d):
    return d - dt.timedelta(days=d.weekday())


def month_bounds(d):
    last = calendar.monthrange(d.year, d.month)[1]
    return d.replace(day=1), d.replace(day=last)


def safe_next(default):
    """Возврат на страницу, с которой пришли, — только внутри сайта."""
    nxt = request.values.get("next", "")
    if nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt:
        return nxt
    return default


def plural(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def fmt_date(value, style="short"):
    d = parse_date(value)
    if not d:
        return ""
    if style == "short":          # 20 нояб.
        return f"{d.day} {MONTHS_GEN[d.month - 1][:3]}."
    if style == "long":           # 20 ноября 2026
        return f"{d.day} {MONTHS_GEN[d.month - 1]} {d.year}"
    if style == "dm":             # 20.11.
        return d.strftime("%d.%m.")
    if style == "dmy":            # 20.11.2026
        return d.strftime("%d.%m.%Y")
    if style == "weekday":        # пятница, 20 ноября
        return f"{WEEKDAYS_FULL[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}"
    return d.isoformat()


def fmt_num(value, digits=0):
    """1 234 или 1 234,5 — с узким пробелом между тысячами."""
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if digits == 0 or v == int(v):
        s = f"{round(v):,}".replace(",", " ")
    else:
        s = f"{v:,.{digits}f}".replace(",", " ").replace(".", ",")
    return s


def fmt_eur(value):
    if value is None:
        return "—"
    return f"{fmt_num(value)} €"


def age_from(birth_date, on=None):
    d = parse_date(birth_date)
    if not d:
        return None
    on = on or today()
    return on.year - d.year - ((on.month, on.day) < (d.month, d.day))
