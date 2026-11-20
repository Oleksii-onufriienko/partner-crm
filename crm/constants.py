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

# Пороги для «слабых мест»
MIN_MARKTPOTENZIAL = 20      # меньше контактов — сигнал
NO_ACTIVITY_DAYS = 14        # нет проведённых встреч за N дней — сигнал
EMPTY_PLAN_DAYS = 14         # нет запланированных встреч на N дней вперёд — сигнал


def label(options, key):
    """Подпись по ключу для списков вида [(key, label, ...)]."""
    for opt in options:
        if opt[0] == key:
            return opt[1]
    return key or ""


def keys(options):
    return [o[0] for o in options]
