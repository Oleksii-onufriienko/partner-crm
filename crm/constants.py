"""Справочники CRM. Значения хранятся в БД как ключи (левая колонка),
подписи для интерфейса — справа. Порядок в списках = порядок в интерфейсе."""

# Ступени карьеры (Stufen) по брошюре AK1 «Ihr Karriereweg bei uns».
# Третье значение — коэффициент € за 1 KE по умолчанию (Provision je Einheit).
# Для ступеней выше RGS в брошюре значений нет — их вводит наставник вручную.
STUFEN = [
    ("VM", "VM — Vermögensmitarbeiter", 1.0),   # в AK1: 1–3 € за единицу
    ("VBA", "VBA — Vermögensberater-Assistent", 6.0),
    ("AL", "AL — Agenturleiter", 9.0),
    ("RGS", "RGS — Regionalgeschäftsstellenleiter", 10.0),
    ("GS", "GS — Geschäftsstellenleiter", None),
    ("HGS", "HGS — Hauptgeschäftsstellenleiter", None),
    ("RD", "RD — Regionaldirektor", None),
    ("D", "D — Direktor", None),
]
STUFE_CODES = [s[0] for s in STUFEN]
STUFE_DEFAULT_COEF = {s[0]: s[2] for s in STUFEN}

# Канал привлечения контакта
CHANNELS = [
    ("warm", "Тёплый круг"),
    ("recommendation", "Рекомендация"),
    ("other", "Другое"),
]

# Тип контакта
KINDS = [
    ("prospect", "Потенциальный клиент"),
    ("client", "Клиент"),
]

# Kontaktpyramide из AK1: от самых близких к незнакомым.
# Подсказка — кто обычно относится к уровню.
TEMPERATURES = [
    ("very_hot", "Очень горячий", "sehr heiß", "родители, братья и сёстры, лучшие друзья"),
    ("hot", "Горячий", "heiß", "хорошие друзья, коллеги по работе, родственники"),
    ("warm", "Тёплый", "warm", "соседи, коллеги, товарищи по команде"),
    ("lukewarm", "Прохладный", "lauwarm", "одноклассники, знакомые из отпуска"),
    ("cold", "Холодный", "kalt", "незнакомые люди"),
]

# Статус работы с контактом (как в Tages-Statistik из Erfolgsjournal)
CONTACT_STATUSES = [
    ("new", "Не контактирован"),
    ("appointment", "Термин назначен"),
    ("in_work", "В работе"),
    ("followup", "Перезвонить позже"),
    ("no_chance", "Нет шансов"),
]

# Формат встречи
FORMATS = [
    ("offline", "Лично"),
    ("online", "Онлайн"),
    ("call", "Звонок"),
    ("private", "Личное время"),  # блок в календаре: семья, хобби, основная работа
]

# Этапы (структура) встречи — от первого контакта до сделки и дальше.
# Третье значение — короткая подпись для планера.
STAGES = [
    ("cold", "Холодный контакт", "Холодн."),
    ("contact", "Контактный разговор", "Контакт"),
    ("advocate", "Fürsprechergespräch", "Fürspr."),
    ("first", "Первый термин (Ersttermin)", "1-й термин"),
    ("analysis", "Анализ (Finanzanalyse)", "Анализ"),
    ("consult", "Бератунг (Beratung)", "Бератунг"),
    ("closing", "Заключение сделки", "Сделка"),
    ("service", "Сервис-термин", "Сервис"),
    ("seminar", "Приглашение на семинар / Info", "Семинар"),
    ("recruiting", "Карьерный разговор", "Карьера"),
    ("training", "Обучение / тим-митинг", "Обучение"),
    ("other", "Другое", "Другое"),
]
# Этапы, которые показываем в воронке статистики
FUNNEL_STAGES = ["first", "analysis", "consult", "closing"]

MEETING_STATUSES = [
    ("planned", "Запланирована"),
    ("done", "Проведена"),
    ("cancelled", "Отменена"),
]

# Подсказки для поля «продукт» (можно ввести и свой вариант)
PRODUCTS = [
    "Altersvorsorge (privat)", "Basisrente", "Riester-Rente", "bAV (betriebliche Vorsorge)",
    "Berufsunfähigkeit (BU)", "Risikolebensversicherung", "Krankenversicherung (PKV)",
    "KV-Zusatzversicherung", "Pflegeversicherung", "Unfallversicherung",
    "Haftpflicht / Hausrat", "KFZ-Versicherung", "Rechtsschutz", "Bausparvertrag",
    "Baufinanzierung", "Ratenkredit / Umschuldung", "Investment / Fonds",
    "Sparplan / Zinskonto", "Konto & Kreditkarte", "Strom / Gas",
    "Vermögenswirksame Leistungen (VL)", "Staatliche Förderungen",
]

# Откуда сделка: из бератунга (новый бизнес) или из сервис-термина (действующий клиент)
DEAL_SOURCES = [
    ("consult", "Бератунг"),
    ("service", "Сервис-термин"),
]

# План/факт по неделям — строки как в Wochenplanung из Erfolgsjournal.
PLAN_BLOCKS = [
    ("fa", "Финансовый анализ (FA)"),
    ("br", "Бератунг"),
    ("st", "Сервис"),
    ("aw", "Карьера (Anwerbung)"),
]
# ключ, блок, подпись, термин из Erfolgsjournal, факт считается сам (True) или вносится вручную (False)
PLAN_METRICS = [
    ("fa_contacts", "fa", "Контакты для первого термина", "Kontakt für FA (tel./pers.)", True),
    ("fa_agreed", "fa", "Договорено первых терминов", "Vereinbart FA-Termin", True),
    ("fa_held", "fa", "Проведено первых терминов", "Wahrgenommen FA-Termin", True),
    ("fa_created", "fa", "Сделано финанализов", "Erstellte FA", True),
    ("fa_referrals", "fa", "Рекомендации", "Empfehlungen aus FA", False),
    ("fa_recruit", "fa", "Карьерные разговоры", "Anw.-Gespräche aus FA", False),
    ("fa_interest", "fa", "Интерес к профессии", "Berufsinteressenten aus FA", False),
    ("br_agreed", "br", "Договорено бератунгов", "Vereinbart Beratungstermin", True),
    ("br_held", "br", "Проведено бератунгов", "Wahrgen. Beratungstermin", True),
    ("br_clients", "br", "Новые клиенты", "Anzahl neue Kunden", True),
    ("br_ke", "br", "KE из бератунгов", "KE aus Beratung", True),
    ("br_referrals", "br", "Рекомендации", "Empfehlungen aus Beratung", False),
    ("br_recruit", "br", "Карьерные разговоры", "Anw.-Gespräche aus Beratung", False),
    ("br_interest", "br", "Интерес к профессии", "Berufsinteressenten aus Beratung", False),
    ("st_agreed", "st", "Договорено сервис-терминов", "Vereinbart Service-Termin", True),
    ("st_held", "st", "Проведено сервис-терминов", "Wahrgen. Service-Termin", True),
    ("st_ke", "st", "KE из сервис-терминов", "KE aus Service-Termin", True),
    ("st_referrals", "st", "Рекомендации", "Empfehlungen aus Service-Termin", False),
    ("st_recruit", "st", "Карьерные разговоры", "Anw.-Gespräche aus Service-Termin", False),
    ("st_interest", "st", "Интерес к профессии", "Berufsinteressenten aus Service-Termin", False),
    ("aw_contacts", "aw", "Контакты для карьерного разговора", "Kontakt für Anwerbung", False),
    ("aw_interest", "aw", "Интерес к профессии", "Berufsinteressenten aus Anwerbung", False),
]
PLAN_METRIC_KEYS = [m[0] for m in PLAN_METRICS]
PLAN_KE_METRICS = ("br_ke", "st_ke")
# Главные показатели для сводки, виджета на «Сегодня» и таблицы по партнёрам
PLAN_SUMMARY = [
    ("fa_held", "Первые термины"),
    ("fa_created", "Финанализы"),
    ("br_held", "Бератунги"),
    ("br_clients", "Новые клиенты"),
    ("ke", "KE всего"),
]

# Пороги для «слабых мест» по умолчанию (каждый пользователь может изменить у себя)
MIN_MARKTPOTENZIAL = 20      # меньше контактов — сигнал
NO_ACTIVITY_DAYS = 14        # нет проведённых встреч за N дней — сигнал
EMPTY_PLAN_DAYS = 14         # нет запланированных встреч на N дней вперёд — сигнал

# Признаки слабых мест: ключ, текст до числа, текст после числа (None — признак без порога),
# порог по умолчанию, допустимый минимум и максимум, как считается.
WEAK_RULES = [
    ("no_activity", "Нет проведённых встреч за", "дней", NO_ACTIVITY_DAYS, 1, 365,
     "В планере нет ни одной встречи со статусом «Проведена» за последние N дней (личное время не считается)."),
    ("empty_plan", "Пустой план на", "дней вперёд", EMPTY_PLAN_DAYS, 1, 90,
     "На ближайшие N дней не запланировано ни одной встречи."),
    ("low_potential", "В Marktpotenzial меньше", "человек", MIN_MARKTPOTENZIAL, 1, 5000,
     "В личном Marktpotenzial человека меньше N контактов (контакты его партнёров не считаются)."),
    ("overdue", "Просроченных напоминаний от", "", 1, 1, 500,
     "У N и более контактов прошла дата «Когда напомнить», а статус не «Нет шансов»."),
    ("stale", "Не отмечен итог прошедших встреч: от", "", 1, 1, 500,
     "N и более встреч уже прошли, но всё ещё стоят как «Запланирована»."),
    ("no_week_plan", "Не заполнен план на эту неделю", None, None, None, None,
     "В «План/факт» на текущую неделю не введено ни одного числа плана."),
    ("no_coef", "Не указан коэффициент €/KE", None, None, None, None,
     "У человека не задан € за 1 KE — его KE не попадают в суммы в евро."),
]
WEAK_RULE_KEYS = [r[0] for r in WEAK_RULES]


def label(options, key):
    """Подпись по ключу для списков вида [(key, label, ...)]."""
    for opt in options:
        if opt[0] == key:
            return opt[1]
    return key or ""


def keys(options):
    return [o[0] for o in options]
