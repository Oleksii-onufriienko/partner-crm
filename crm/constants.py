"""Справочники CRM. Значения хранятся в БД как ключи (левая колонка),
подписи для интерфейса — справа. Порядок в списках = порядок в интерфейсе."""

# Ступени карьеры по «Leistung lohnt sich 2026» (Karrieresystem).
# Третье значение — вознаграждение € за 1 единицу (Vergütung gemäß Provisionsstufe).
# VM получают Zuführungsprovision 1, 2 или 3 € (по Provisionsstufe) — по умолчанию 1 €, меняется вручную.
STUFEN = [
    ("VM", "VM — Vertrauensmitarbeiter", 1.0),
    ("VBAS", "VBAS — Vermögensberater-Assistent Service", 4.0),
    ("VBAK", "VBAK — Vermögensberater-Assistent Karriere", 6.0),
    ("AL", "AL — Agenturleiter", 9.0),
    ("RGS", "RGS — Regionalgeschäftsstellenleiter", 10.0),
    ("GS", "GS — Geschäftsstellenleiter", 11.0),
    ("HGS", "HGS — Hauptgeschäftsstellenleiter", 12.0),
    ("RD1", "RD1 — Regionaldirektionsleiter 1", 12.6),
    ("RD2", "RD2 — Regionaldirektionsleiter 2", 13.2),
    ("D", "D — Direktionsleiter", 14.0),
    ("P2", "P2 — Praxis 2", 10.0),
    ("P3", "P3 — Praxis 3", 11.0),
    ("P4", "P4 — Praxis 4", 12.0),
    ("P5", "P5 — Praxis 5", 12.6),
    ("P6", "P6 — Praxis 6", 13.2),
    ("P7", "P7 — Praxis 7", 13.6),
]
STUFE_CODES = [s[0] for s in STUFEN]
STUFE_DEFAULT_COEF = {s[0]: s[2] for s in STUFEN}
# Старшинство ступени (по ставке) — чтобы отличать повышение от перевода
STUFE_RANK = {s[0]: s[2] for s in STUFEN}
# Старые коды из первой версии → новые
STUFE_RENAMES = {"VBA": "VBAK", "RD": "RD1"}

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
    ("reflection", "Reflexionsgespräch", "Reflexion"),
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

# Воронка партнёров (Potentialliste Partner / «Ihr zukünftiges Team» из AK1)
RECRUIT_STAGES = [
    ("interest", "Интерес", "Berufsinteressent"),
    ("invited", "Приглашён на Info", "Einladung zur Karriere-Info"),
    ("attended", "Был на Info", "Info besucht"),
    ("talk", "Карьерный разговор", "Anwerbegespräch"),
    ("joined", "Стал партнёром", "VM geworden"),
    ("declined", "Отказ", "kein Interesse"),
]
RECRUIT_ACTIVE = ["interest", "invited", "attended", "talk"]

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
    ("no_orga", "Не подготовился к ORGA за прошлую неделю", None, None, None, None,
     "За прошлую неделю не заполнена «Подготовка к ORGA» (вопросы ORGA Checkliste и самооценка)."),
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


# ---------------------------------------------------------------- наставничество (пункт Б)
# Самооценка перед ORGA по шкале 0–10 (ORGA Checkliste, Erfolgsjournal)
ORGA_SKILLS = [
    ("service", "Сервис", "Service"),
    ("lead", "Ведение партнёров", "Partnerführung"),
    ("planning", "Планирование", "Planung"),
    ("contact", "Контакт", "Kontakt"),
    ("evidence", "Доказательства", "Evidenz"),
    ("analysis", "Финанализ", "Finanzanalyse"),
    ("referrals", "Рекомендации", "Empfehlungen"),
    ("recruit", "Привлечение партнёров", "Anwerbung"),
    ("consult", "Бератунг", "Beratung"),
]
ORGA_SKILL_KEYS = [s[0] for s in ORGA_SKILLS]

# Участники Reflexionsgespräch (AK1, с. 37 и 41)
REFLECTION_PEOPLE = [("partner", "Супруг(а)", "Lebenspartner/-in"), ("coach", "Наставник", "Coach"),
                     ("teamlead", "Руководитель команды", "Teamleiter"), ("dleiter", "D-Leiter", "D-Leiter")]
# Куда человек хочет прийти (AK1: Nebenberuf → Hauptberuf → VB → Unternehmer im Unternehmen)
CAREER_INTENTS = [("side", "Побочная деятельность", "Nebenberuf"), ("main", "Основная работа", "Hauptberuf"),
                  ("vb", "Vermögensberater", "VB"),
                  ("entrepreneur", "Предприниматель в компании", "Unternehmer im Unternehmen")]
# Итоги, которые сверяются в разговоре (AK1: Aktivitäten / Ergebnis / Ziele)
REFLECTION_RESULTS = [
    ("analyses", "Финанализы", "Analysen"), ("consults", "Бератунги", "Beratungen"),
    ("referrals", "Рекомендации", "Empfehlungen"), ("clients", "Новые клиенты", "Kunden"),
    ("partners", "Новые партнёры", "Partner"), ("info", "Участники Info", "Info-Teilnehmer"),
    ("vm", "Новые VM", "VM"), ("units", "Единицы", "Einheiten"),
]

# Старт новичка (AK1: Ausbildungsplanung, Marktpotenziale, Reflexionsgespräche).
# ключ, подпись, термин, как отмечается: manual — вручную с датой; exam — дата и результат;
# auto — считается сам из CRM (можно отметить и вручную).
ONBOARDING_STEPS = [
    ("info", "Был на Karriere-Info", "Info besucht", "manual"),
    ("starter", "Был на Startertreffen", "Startertreffen besucht", "manual"),
    ("ak1", "Проработал AK1", "AK 1 ausgearbeitet", "manual"),
    ("mp20", "Marktpotenzial: 20 человек", "Marktpotenzial", "auto"),
    ("fuersprecher", "Записал 6 Fürsprecher", "Ihre Fürsprecher", "auto"),
    ("fs_talks", "Провёл 3 Fürsprechergespräche", "Fürsprechergespräche", "auto"),
    ("first_analysis", "Первый финанализ", "erste Analyse", "auto"),
    ("first_client", "Первый клиент", "erster Kunde", "auto"),
    ("refl1", "Reflexionsgespräch 1", "Reflexionsgespräch 1", "auto"),
    ("vm_exam", "Экзамен VM", "VM-Prüfung", "exam"),
    ("refl2", "Reflexionsgespräch 2", "Reflexionsgespräch 2", "auto"),
    ("vba_exam", "Экзамен VBA (IDD)", "VBA-Prüfung", "exam"),
]
ONBOARDING_KEYS = [s[0] for s in ONBOARDING_STEPS]
ONBOARDING_TOPICS = 7          # «Themen 1.–7.» в Ausbildungsplanung
ONBOARDING_STUCK_DAYS = 21     # нет нового шага столько дней — новичок «застрял»
NEWCOMER_STUFEN = ("VM", "VBAS", "VBAK")

# ---------------------------------------------------------------- ежедневная работа (пункт В)
# Результат звонка в режиме обзвона (Tages-Statistik: Telefongespräche / Termine)
CALL_RESULTS = [
    ("no_answer", "Не дозвонился", "nicht erreicht"),
    ("appointment", "Термин", "Termin"),
    ("callback", "Перезвонить", "Rückruf"),
    ("no_chance", "Нет шансов", "kein Interesse"),
]
CALL_REACHED = ("appointment", "callback", "no_chance")   # разговор состоялся
CALLS_PER_DAY = 10             # «Dein minimales Ziel des Tages: 10 neue Kontakte und 3 Termine»
TERMINE_PER_DAY = 3

# Musterwoche (AK1, с. 10): виды блоков
MUSTER_KINDS = [
    ("vb", "VM/VB-работа", "VM/VB-Aktivitäten"),
    ("team", "Тим-митинг", "Teammeeting"),
    ("training", "Обучение", "Schulungen"),
    ("job", "Основная работа", "Arbeitszeiten (Hauptberuf)"),
    ("hobby", "Хобби, спорт", "Hobbys"),
    ("family", "Семья, друзья", "Familie, Freunde"),
]
