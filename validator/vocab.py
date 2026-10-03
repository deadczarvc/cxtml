#!/usr/bin/env python3
"""XTML vocabulary: the ONE source of every profile's words, value dictionaries and man pages.

    python vocab.py --check     # config/card-format.json == projection of this module (exit 1 on drift)
    python vocab.py --write     # regenerate the projection
    python validate.py --man [tag] [--profile p]    # read an article (this module renders it)

WHY CODE (user 2026-10-02, R11-I): «в .md файле хранить man кащунство … md мутирует», «json то же запрещено», «можно
в .py скрипте, т.к. код сам по себе агентами охотно читается, имеет высший приоритет перед текстовыми доками».
The words lived in four places that drifted apart: literals in validate.py, the message / doc blocks of
card-format.json, the vocabulary blocks of the skill's SKILL.md and references/doc-profile-man.md. Now lists and
articles are Python literals here, and import fails when they disagree (selfcheck) — a drift is an exception.

ADDING A WORD: the tag in its profile tuple AND a Man(...) record in MAN — one file. Only words from real documents,
¬ wildcard (R11, user: «можно добавлять в словарь слово и к нему документацию, man»). Articles are a tuple of records,
¬ a dict literal: a dict silently keeps the last of two equal keys.

card-format.json is a GENERATED projection for consumers that are not Python (cxtml mirror, touchstone copy, exports,
people reading the routing contract); test_vocab.py runs --check, so a hand-edited projection goes red. Stdlib only,
Python ≥ 3.9: hooks load this file directly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NamedTuple


class VocabError(ValueError):
    """The vocabulary contradicts itself: import fails loudly instead of handing out half a vocabulary."""


class Man(NamedTuple):
    profile: str
    tag: str
    purpose: str
    when: str
    attrs: str
    example: str


SCHEMA = "card-format/v1"
# History (was card-format.json "why" / "notes", moved here R11-I). 2026-09-11: one owner of the card format — the
# validator, the requirements parser and the matrix behind the gate read these lists, ¬ frozen copies (found: key
# mechanical required by the matrix ∧ rejected by the validator). 2026-09-22: phase arbitrate (sigma ∧ evidence_router
# had it, the format lagged). 2026-09-26 W1a-K2: loop-class moved here. A section outside mandatory ∪ known_extra is a
# signal, ¬ an error (repeats ⇒ KNOWN_EXTRA); an unknown capability key IS an error (the requirement vanishes).
# Consumers 2026-10-02: tools/xtml/validate.py ∧ check_vocab_sync.py (import); hooks/evidence_router.py,
# hooks/preflight-gate.py, sigma/sigma/compiler.py, scripts/card-format-check.py, tests/test_preflight_matrix_gate.py
# (load this file by path); the projection — cxtml mirror, touchstone copy, exports.

# === delegation: the card a delegate receives ======================================================================
CORE = ("task", "mission", "invariants", "source-of-truth", "acceptance", "write-scope", "stop-conditions",
        "report-path")
OPTIONAL = ("role", "context", "input", "constraints", "forbid", "require", "response-format", "queries", "q",
            "targets", "t", "steps", "step", "note", "handoff", "budget", "routing", "prior", "channel", "deviation",
            "counter-example", "escalate", "peer", "sync", "depends-on", "evidence", "timebox")
# Canon v2 §4 (2026-08-15, card DSH-IMPL-XTML t_20fea199): optional sections with value dictionaries, checked only
# when present (validate.V2_SECTIONS); was references/canon-v2-sections.md of the skill until R11-I.
V2 = ("loop-class", "capability-requirements", "context-budget", "report-schema", "seed-policy")
KNOWN_EXTRA = ("routing", "role", "capability-requirements", "steps", "handoff", "context", "note", "constraints",
               "reporting-contract", "forbid", "design-options", "architecture-decision")  # card-format-check.py
ENFORCED_COUNT = {"routing": 1}
LOOP_CLASSES = ("one-shot", "continuable", "ralph-round")
CAPABILITY_KEYS = ("terminal", "vision", "reasoning", "long-context", "mechanical")
MATRIX_FLAGS = ("vision", "reasoning", "mechanical")  # flags the preflight matrix checker accepts
CONTEXT_BUDGET_KEYS = ("max-input-tokens", "report-inline-max")
SEED_POLICIES = ("none", "context-inline")
VERDICT_MARKER = "VERDICT"
ROUTING_FIELDS = ("phase", "role", "risk", "scope", "contract", "evidence", "acceptance", "localized", "mechanical",
                  "failure", "previous_tier", "escalations", "specialist")
ROUTING_OPTIONAL = ("requirements",)
PHASES = ("collect", "diagnose", "implement", "verify", "arbitrate")
ROUTING_ENUMS = {"risk": ("low", "elevated", "critical", "unknown"), "scope": ("local", "cross_system", "unknown"),
                 "contract": ("clear", "ambiguous", "unknown"), "failure": ("none", "quality", "infrastructure")}
TIERS = ("luna", "terra", "sol", "astra")

# === kimi: grammar of the source (layer T, Kimi K3 chat template, arXiv 2607.24653 App. F) ==========================
KIMI = ("message", "think", "response", "tools", "call", "argument")

# === message: peer card agent↔agent (W65 2026-10-01, aligned W68 to encoding_k3.py — the code of the source is the
# truth; App. F roles system | user | tool | assistant). Root message role="peer" (cXTML extension [X]); a request MAY
# carry call tool= index= with argument key= type= (name= is a deprecated alias of key=, warning); a reply to a call
# carries tool= index= of that call, like an App. F tool result; [end_of_msg] allowed at the end. Consumers:
# validate.py (profile message), codec.py, peer-bus (send --xtml, messages.jsonl).
MSG = {"root": "message", "role": "peer", "attrs": ["role", "id", "from", "to", "type", "re"],
       "optional_attrs": ["tool", "index"],
       "types": ["REQ", "ACK", "NACK", "INFO", "CLAIM", "CONFLICT", "HANDOFF", "ESCALATE"],
       "sections": ["subject", "body", "evidence", "needs", "until"], "until_required": ["REQ", "CLAIM", "CONFLICT"],
       "needs_none_ok": ["INFO", "ACK"], "re_required": ["ACK", "NACK"], "closing_types": ["ACK", "NACK", "HANDOFF"],
       "call": {"tag": "call", "attrs": ["tool", "index"], "argument": "argument", "argument_attrs": ["key", "type"],
                "argument_alias": {"name": "key"}, "types": ["REQ", "CLAIM", "CONFLICT"]}}

# === doc: a document (program, plan, summary, track handoff), ¬ an assignment ∧ ¬ a message (W73 2026-10-01 X11.1;
# R11 2026-10-02: + root handoff ∧ 8 track-handoff sections from the inventory of the station's *.xtml, ¬ wildcard).
DOC = {"roots": ["doc", "handoff", "task"],
       "elements": ["done-this-wave", "evidence", "git-blocker", "invariants", "item", "items", "mission",
                    "next-action", "note", "peers", "remaining", "section", "status", "step", "steps", "t",
                    "targets", "track-dir", "verify"]}

PROFILES = {
    "delegation": CORE + OPTIONAL + V2,
    "kimi": KIMI,
    "message": (MSG["root"], *MSG["sections"], MSG["call"]["tag"], MSG["call"]["argument"]),
    "doc": (*DOC["roots"], *DOC["elements"]),
}
# What validate.py checks tags against. delegation without V2: the validator adds V2_SECTIONS itself (unchanged
# semantics — under --profile any the v2 names stay outside the union, as before R11-I).
VOCAB = {"kimi": KIMI, "delegation": CORE + OPTIONAL, "message": PROFILES["message"], "doc": PROFILES["doc"]}

INTRO = (
    ("delegation", "карточка постановки делегату: корень task + ядро из 8 разделов + обязательный routing; "
                   "остальное по надобности; 5 разделов канона v2 — после ядра. Тег вне словаря — предупреждение, "
                   "под --strict rc 1. Атрибут — только name=\"value\" (иначе rc 2); имена ∧ значения ¬ сверяются."),
    ("kimi", "грамматика первоисточника — слой T, шаблон чата Kimi K3 (прил. F): чужой формат, исход совещательный "
             "(rc 1); текст прямо в корне — норма; [end_of_msg] законен; глубина ≤ 4."),
    ("message", "горизонтальная карта агент↔агент (peer-bus), ¬ постановка: закрытый словарь — неизвестный раздел ∨ "
                "атрибут ⇒ rc 2, непроверенный текст соседу ¬ доставляется."),
    ("doc", "документ ≠ поручение: программа, план, сводка, передача трека (handoff). Грамматика + закрытый словарь "
            "(тег вне словаря ⇒ rc 2), корень из roots, ядра карточки нет, [end_of_msg] ⇒ rc 2. Атрибуты профиль ¬ "
            "сверяет (как у t ∧ step с W73) — в статьях их конвенции, ¬ закон валидатора. Полный документ-образец — "
            "<tracks>/<трек>/HANDOFF.xtml (rc 0)."),
)

_ROUTING_WHEN = (
    "обязателен у карточки delegation: нет ∨ битый ⇒ rc 2 (исторический корпус — флаг --allow-no-routing). Поля: "
    + ", ".join(ROUTING_FIELDS) + "; необязательное — " + ", ".join(ROUTING_OPTIONAL) + ". phase ∈ "
    + " | ".join(PHASES) + "; " + "; ".join(f"{k} ∈ {' | '.join(v)}" for k, v in ROUTING_ENUMS.items())
    + "; previous_tier ∈ " + " | ".join(TIERS) + " ∨ null (обязателен при failure=quality); evidence — непустой "
    "список строк; localized ∧ mechanical — bool; escalations — int; nullable-поля — JSON null, ¬ строка «none». "
    "role ∈ base_profiles флота — иначе evidence_router вернёт STOP (битый пакет) ∨ STOP_CONFIG "
    "(нет профиля под тир)")

MAN = (
    # --- delegation: core (purpose = the reason printed when the section is missing) ---
    Man("delegation", "task", "корень: без него это не карточка",
        "корень постановки делегату; идентификатор сквозной с реестром; один на файл, последняя строка карточки — "
        "`[close]task[sep]`.", "`id` — сквозной с реестром; `lane` — полоса волны; значения только в двойных "
        "кавычках (без кавычек ⇒ rc 2).", '`[open]task id="R-01" lane="wave-r"[sep]…[close]task[sep]`'),
    Man("delegation", "mission", "единственная задача; без неё делегат выберет её сам",
        "∀ карточка; одна задача, а не список пожеланий; заглушка (TODO, TBD, «—») ⇒ rc 2.", "нет.",
        "`[open]mission[sep]Перенести словарь в vocab.py ∧ доказать перенос каждой статьи.[close]mission[sep]`"),
    Man("delegation", "invariants", "что обязано остаться правдой; голая цель решается занулением",
        "∀ карточка: вердикты, тесты, чужие файлы — то, что правка ¬ вправе сдвинуть.", "нет.",
        "`[open]invariants[sep]Вердикты валидатора на корпусе ¬ меняются.[close]invariants[sep]`"),
    Man("delegation", "source-of-truth", "факты и пути; без них «не нашёл» неотличимо от «не искал»",
        "делегат не имеет твоего контекста: пути, строки кода, отчёты, на которые опираться.", "нет.",
        "`[open]source-of-truth[sep]<ops-root>/tools/xtml/validate.py[close]source-of-truth[sep]`"),
    Man("delegation", "acceptance", "команда приёмки; единственное место, где отчёт опровержим",
        "КОМАНДА и ожидаемый вывод, а не «проверить что работает»: проза ⇒ rc 2; проба содержания отчёта, а не его "
        "существования (Test-Path / exists() без пробы содержимого ⇒ предупреждение); разрушительная команда ⇒ "
        "предупреждение.", "нет.",
        "`[open]acceptance[sep]python -B tools/xtml/test_validate.py — ожидается код 0[close]acceptance[sep]`"),
    Man("delegation", "write-scope", "границы записи; делает «не тронул» проверяемым",
        "что делегату можно трогать; путь отчёта обязан лежать в области: область — один путь без прозы ∧ отчёт вне "
        "неё ⇒ rc 2, область прозой ⇒ предупреждение.", "нет.",
        "`[open]write-scope[sep]Только tools/xtml/ ∧ отчёт reports/x.md.[close]write-scope[sep]`"),
    Man("delegation", "stop-conditions", "когда доложить, а не дожимать любой ценой",
        "∀ карточка: чужой lock, красная сьюта, исчерпанный бюджет — условие ⇒ доклад вместо обхода.", "нет.",
        "`[open]stop-conditions[sep]Чужой lock ⇒ стоп ∧ доклад.[close]stop-conditions[sep]`"),
    Man("delegation", "report-path", "куда класть результат",
        "иначе результат потеряется в финальном сообщении; один путь файла: относительный без «..» ∨ полный DOS-путь "
        "внутри домашнего контура; без переменных окружения ∧ потоков NTFS (иначе rc 2).", "нет.",
        "`[open]report-path[sep]reports/r11-report.md[close]report-path[sep]`"),
    # --- delegation: optional ---
    Man("delegation", "role", "кто исполнитель и какая квалификация",
        "исполнитель ¬ очевиден из задачи ∨ нужна узкая квалификация.", "нет.",
        "`[open]role[sep]Python-инженер: валидаторы ∧ мутационные тесты.[close]role[sep]`"),
    Man("delegation", "context", "фон, не являющийся источником истины",
        "предыстория ∧ мотив; факты ∧ пути — в source-of-truth, ¬ здесь.", "нет.",
        "`[open]context[sep]Пользователь запретил хранить man в md.[close]context[sep]`"),
    Man("delegation", "input", "что дано и где лежит", "делегату передаются данные ∨ файлы для обработки.",
        "нет.", "`[open]input[sep]Корпус *.xtml: es ext:xtml.[close]input[sep]`"),
    Man("delegation", "constraints", "контейнер ограничений",
        "ограничений больше одного — элементами forbid ∧ require внутри.", "нет.",
        "`[open]constraints[sep][open]forbid[sep]коммиты[close]forbid[sep][close]constraints[sep]`"),
    Man("delegation", "forbid", "запрет; живёт внутри constraints", "одно действие, которое делегату нельзя.",
        "нет.", "`[open]forbid[sep]обходить чужой lock записью через shell[close]forbid[sep]`"),
    Man("delegation", "require", "положительное требование, когда запретов мало",
        "внутри constraints, если правило проще сказать «делай», чем «не делай».", "нет.",
        "`[open]require[sep]бэкап рядом с каждым изменённым файлом[close]require[sep]`"),
    Man("delegation", "response-format", "форма ответа с ограничениями",
        "ответ читает машина ∨ нужен строгий шаблон: поля, порядок, лимит строк.", "нет.",
        "`[open]response-format[sep]Первая строка «# », итог ≤ 8 строк.[close]response-format[sep]`"),
    Man("delegation", "queries", "контейнер запросов для разведки",
        "делегат ищет ответы, а ¬ правит; вопросы — элементами q.", "нет.",
        "`[open]queries[sep][open]q[sep]Кто читает card-format.json?[close]q[sep][close]queries[sep]`"),
    Man("delegation", "q", "запрос; живёт внутри queries", "один вопрос разведки с проверяемым ответом.",
        "`id` по желанию (атрибуты ¬ сверяются).", "`[open]q[sep]Q1 кто читает файл?[close]q[sep]`"),
    Man("delegation", "targets", "контейнер целей обхода", "несколько однородных целей — элементами t.", "нет.",
        "`[open]targets[sep][open]t[sep]validate.py[close]t[sep][close]targets[sep]`"),
    Man("delegation", "t", "цель; живёт внутри targets", "одна цель обхода: файл, хост, профиль.",
        "`id` по желанию.", '`[open]t id="a"[sep]<ops-root>/hooks/evidence_router.py[close]t[sep]`'),
    Man("delegation", "steps", "контейнер явной последовательности", "порядок работ значим; шаги — элементами step.",
        "нет.", "`[open]steps[sep][open]step[sep]бэкап[close]step[sep][close]steps[sep]`"),
    Man("delegation", "step", "шаг; живёт внутри steps", "один шаг; порядок элементов = порядок исполнения.",
        "`id` по желанию.", '`[open]step id="1"[sep]снять бэкапы[close]step[sep]`'),
    Man("delegation", "note", "оговорка, не меняющая задачу",
        "пояснение, полезное делегату, но ¬ новое поручение; повтор раздела законен (предупреждение).", "нет.",
        "`[open]note[sep]Зеркало cxtml ¬ трогать.[close]note[sep]`"),
    Man("delegation", "handoff", "кому и что передать после завершения",
        "результат продолжает другой исполнитель ∨ очередь.", "нет.",
        "`[open]handoff[sep]Отчёт ⇒ родителю; хвосты ⇒ kanban куратора.[close]handoff[sep]`"),
    Man("delegation", "budget", "потолок вызовов инструментов или объёма",
        "работа может расползтись: предел вызовов, токенов ∨ денег.", "нет.",
        "`[open]budget[sep]≤ 60 вызовов инструментов[close]budget[sep]`"),
    Man("delegation", "routing", "пакет маршрутизации канона v2: строгий JSON 13 полей; без него отказ",
        _ROUTING_WHEN, "нет; содержимое — один JSON-объект.",
        '`[open]routing[sep]{"phase": "implement", "role": "worker-coder", "risk": "low", …, "previous_tier": null}'
        '[close]routing[sep]`'),
    Man("delegation", "prior", "что уже найдено — чтобы делегат не переоткрывал",
        "продолжение ∨ повтор работы: прошлые находки, отчёты, отвергнутые гипотезы.", "нет.",
        "`[open]prior[sep]R11/F-report.md: словарь doc 22 тега.[close]prior[sep]`"),
    Man("delegation", "channel", "каким каналом работать; недоступный называть, ¬подменять",
        "результат зависит от инструмента ∨ провайдера (MCP, CLI, модель).", "нет.",
        "`[open]channel[sep]mcpc @<lexical-index>; недоступен ⇒ назвать, ¬ подменять.[close]channel[sep]`"),
    Man("delegation", "deviation", "известные отклонения и ловушки предметной области",
        "домен с подвохами, о которых делегат иначе узнает ценой ошибки.", "нет.",
        "`[open]deviation[sep]dict-литерал молча берёт последний дубль ключа.[close]deviation[sep]`"),
    Man("delegation", "counter-example", "как выглядит негодный ответ",
        "есть типичный неверный результат, похожий на верный.", "нет.",
        "`[open]counter-example[sep]«тесты зелёные» без вывода прогона.[close]counter-example[sep]`"),
    Man("delegation", "escalate", "когда углублять уровень, а когда остановиться",
        "задача может потребовать более сильного исполнителя ∨ решения владельца.", "нет.",
        "`[open]escalate[sep]Сьюта красная ∧ ¬ чинится ⇒ откат ∧ доклад.[close]escalate[sep]`"),
    Man("delegation", "peer", "кто ещё работает рядом и над чем",
        "рядом живые сессии ∨ чужие lock'и; один сосед (список соседей документа — peers профиля doc).", "нет.",
        "`[open]peer[sep]claude:a1b2c3d4 — git-resync <config-repo>.[close]peer[sep]`"),
    Man("delegation", "sync", "что передать соседям по контуру и когда",
        "результат меняет то, на что опираются соседи.", "нет.",
        "`[open]sync[sep]После правки validate.py — владельцу cxtml команда resync.[close]sync[sep]`"),
    Man("delegation", "depends-on", "связь с задачей реестра", "карточка — часть цепочки задач (kanban ∨ ledger).",
        "нет.", "`[open]depends-on[sep]t_a9d8073e[close]depends-on[sep]`"),
    Man("delegation", "evidence", "требуемые пометки провенанса в ответе",
        "утверждения отчёта обязаны нести путь ∨ команду ∨ вывод.", "нет.",
        "`[open]evidence[sep]∀ утверждение: путь ∧ команда ∧ вывод.[close]evidence[sep]`"),
    Man("delegation", "timebox", "потолок времени либо числа вызовов",
        "работа ограничена временем; исчерпан ⇒ сдать частичное.", "нет.",
        "`[open]timebox[sep]30 min[close]timebox[sep]`"),
    # --- delegation: canon v2 §4 (after the core; checked only when present, distortion ⇒ rc 2) ---
    Man("delegation", "loop-class", "класс порождения субагента (канон v2 §1)",
        f"после ядра; значения {' | '.join(LOOP_CLASSES)}, дефолт one-shot, вне словаря ⇒ rc 2. MATRIX-GATE в "
        "preflight-gate читает loop-class / capability-requirements / temperature: / effort: из карты ∧ блокирует "
        "несовместимое назначение.", "нет.", "`[open]loop-class[sep]one-shot[close]loop-class[sep]`"),
    Man("delegation", "capability-requirements", "требования к возможностям модели — пары ключ:true|false",
        f"после ядра; ключи {', '.join(CAPABILITY_KEYS)}; запись ¬ вида ключ:true|false ∨ ключ вне словаря ∨ пусто ⇒ "
        f"rc 2; матрица (MATRIX-GATE preflight-gate, флаги {', '.join(MATRIX_FLAGS)}) ⇒ BLOCK при несоответствии.",
        "нет.", "`[open]capability-requirements[sep]vision:false reasoning:true[close]capability-requirements[sep]`"),
    Man("delegation", "context-budget", "бюджет контекста: потолок входа ∧ сколько держать инлайн в отчёте",
        f"после ядра; записи «ключ: целое» через «;», нужны оба ключа: {', '.join(CONTEXT_BUDGET_KEYS)}; слово после "
        "числа — пояснение для человека («2000 chars»).", "нет.",
        "`[open]context-budget[sep]max-input-tokens: 120000; report-inline-max: 2000 chars"
        "[close]context-budget[sep]`"),
    Man("delegation", "report-schema", "контракт отчёта: итог, отличимый от сопроводительной прозы",
        f"после ядра; маркер вердикта {VERDICT_MARKER} обязателен (форма «{VERDICT_MARKER}: PASS|FAIL»), без него ⇒ "
        "rc 2.", "нет.", "`[open]report-schema[sep]VERDICT: PASS|FAIL, затем находки[close]report-schema[sep]`"),
    Man("delegation", "seed-policy", "какой контекст получает ребёнок (стабильный сид)",
        f"после ядра; первое слово ∈ {' | '.join(SEED_POLICIES)}; context-inline обязан дальше сказать, что берётся "
        "из родителя ∧ почему — иначе наследование непроверяемо (rc 2).", "нет.",
        "`[open]seed-policy[sep]context-inline только source-of-truth родителя[close]seed-policy[sep]`"),
    # --- kimi ---
    Man("kimi", "message", "верхнеуровневая единица контекста",
        "корень документа слоя T; тело сообщения лежит прямо в корне; [end_of_msg] после корня законен.",
        "`role` — system | user | tool | assistant; у результата инструмента ещё `tool` ∧ `index` вызова.",
        '`[open]message role="user"[sep]Privet[close]message[sep]`'),
    Man("kimi", "think", "канал следа рассуждения", "внутри message роли assistant, до response.", "нет.",
        '`[open]message role="assistant"[sep][open]think[sep]x[close]think[sep][close]message[sep]`'),
    Man("kimi", "response", "канал видимого пользователю ответа", "внутри message роли assistant.", "нет.",
        '`[open]message role="assistant"[sep][open]response[sep]Готово.[close]response[sep][close]message[sep]`'),
    Man("kimi", "tools", "канал вызовов инструментов", "внутри message роли assistant; элементы — call.", "нет.",
        '`[open]tools[sep][open]call tool="search" index="0"[sep]…[close]call[sep][close]tools[sep]`'),
    Man("kimi", "call", "один вызов; несёт tool и index",
        "внутри tools; message > tools > call > argument = 4 уровня — потолок профиля kimi.",
        "`tool` — имя инструмента; `index` — номер вызова.",
        '`[open]call tool="search" index="0"[sep][open]argument key="q" type="string"[sep]x[close]argument[sep]'
        '[close]call[sep]`'),
    Man("kimi", "argument", "типизированный аргумент вызова", "внутри call, элемент на аргумент.",
        "`key` — имя; `type` — тип значения.", '`[open]argument key="q" type="string"[sep]xtml[close]argument[sep]`'),
    # --- message ---
    Man("message", "message", "горизонтальная карта агент↔агент (peer message), ¬ постановка",
        "сообщение соседу через peer-bus (send --xtml, messages.jsonl); все пять разделов обязательны; [end_of_msg] "
        "допустим в конце.",
        f"обязательны {', '.join(MSG['attrs'])}: role=\"{MSG['role']}\" (расширение cXTML; роли прил. F — system | "
        "user | tool | assistant); id — [A-Za-z0-9._-] до 64; from — agent:sid[:agent_id], agent ∈ claude | codex | "
        f"hermes; to — то же ∨ agent:sid:* ∨ lane:<имя>; type ∈ {' | '.join(MSG['types'])}; re — id треда ∨ none "
        f"(у {' | '.join(MSG['re_required'])} обязателен). {' ∧ '.join(MSG['optional_attrs'])} — парой, только у "
        f"ответа ({' | '.join(MSG['closing_types'])}) с re: номер вызова call, на который ответ.",
        '`[open]message role="peer" id="m1" from="claude:a1" to="codex:b2" type="INFO" re="none"[sep]…'
        '[close]message[sep]`'),
    Man("message", "subject", "тема сообщения одной строкой", "обязательный раздел ∀ type.", "нет.",
        "`[open]subject[sep]card-format.json стал проекцией vocab.py[close]subject[sep]`"),
    Man("message", "body", "суть: что сделано ∨ что просят", "обязательный раздел ∀ type; заглушка ⇒ rc 2.", "нет.",
        "`[open]body[sep]Python-потребители читают vocab.py.[close]body[sep]`"),
    Man("message", "evidence", "провенанс утверждений сообщения: пути, команды, вывод",
        "обязательный раздел ∀ type; пусто ∨ заглушка ⇒ rc 2.", "нет.",
        "`[open]evidence[sep]python vocab.py --check ⇒ rc 0[close]evidence[sep]`"),
    Man("message", "needs", "что требуется от получателя",
        f"обязательный раздел; none допустим только у {' | '.join(MSG['needs_none_ok'])}.", "нет.",
        "`[open]needs[sep]ACK до срока until[close]needs[sep]`"),
    Man("message", "until", "срок ответа",
        "обязательный раздел: ISO-8601 с часовым поясом ∨ none; none ¬ допустим у "
        f"{' | '.join(MSG['until_required'])}.",
        "нет.", "`[open]until[sep]2026-10-02T12:00:00+03:00[close]until[sep]`"),
    Man("message", "call", "вызов инструмента на соседе (форма прил. F, encoding_k3.py)",
        f"прямой раздел message, только у {' | '.join(MSG['call']['types'])}; index вызовов уникален — по нему "
        "сопоставляется ответ.", "`tool` — имя [A-Za-z0-9._-]; `index` — целое; иных нет.",
        '`[open]call tool="claim" index="0"[sep][open]argument key="path" type="string"[sep]x.py[close]argument[sep]'
        '[close]call[sep]`'),
    Man("message", "argument", "аргумент вызова call", "только внутри call.",
        "`key` ∧ `type` ([A-Za-z0-9._-]); " + ", ".join(f"`{a}` — устаревший алиас `{k}`" for a, k in
                                                        MSG["call"]["argument_alias"].items()) + " (предупреждение), "
        "вместе ¬ ходят.",
        '`[open]argument key="path" type="string"[sep]x.py[close]argument[sep]`'),
    # --- doc (transferred from references/doc-profile-man.md, R11-F) ---
    Man("doc", "doc",
        "корень документа общего вида — сводка, отчёт-срез, справка.",
        "документ ¬ программа ∧ ¬ передача трека; специального корня нет.", "`id` — slug документа.",
        '`[open]doc id="summary"[sep][open]section id="scope"[sep]…[close]section[sep][close]doc[sep]`'),
    Man("doc", "handoff",
        "корень передачи трека между сессиями ∨ агентами: состояние, сделанное, хвосты, следующий шаг.",
        "трек живёт дольше одной сессии ∧ следующий исполнитель продолжает без контекста. ¬ поручение: работа "
        "делегату = `task` профиля delegation.",
        "`id` — slug трека; `ts` — ISO-дата среза; `from` — actor `agent:sid`, писавший срез.",
        '`[open]handoff id="docs-sync" ts="2026-10-02" from="claude:a1b2c3d4"[sep]…[close]handoff[sep]`'),
    Man("doc", "task",
        "корень документа-программы (программа, план с целями ∧ шагами); форма карточки без её ядра.",
        "документы генератора программы (`program.py validate()`). ⛔ Профиль doc ядро ¬ проверяет: поручение "
        "делегату валидировать `--profile delegation`.", "`id`; `progress` — `сделано/всего` (конвенция program.py).",
        '`[open]task id="PROGRAM decision-layer" '
        'progress="3/4"[sep][open]mission[sep]…[close]mission[sep][close]task[sep]`'),
    Man("doc", "done-this-wave",
        "что закрыто в текущей волне — нумерованный список с доказательством на пункт.",
        "в `handoff` после `status`; один на срез.", "нет.",
        "`[open]done-this-wave[sep]1. resync = e68b339, тесты 3 passed.[close]done-this-wave[sep]`"),
    Man("doc", "evidence",
        "провенанс — прогоны, пути, хэши, на которых стоят утверждения документа.",
        "утверждение без пробы ¬ факт; ∀ документ с выводами.", "нет.",
        "`[open]evidence[sep]- check.py all 75/75 OK, 2026-10-02[close]evidence[sep]`"),
    Man("doc", "git-blocker",
        "что мешает коммиту (чужой staged-набор, вынесенный `.git`) ∧ как его обойти ¬ ломая соседа.",
        'в `handoff`, пока блокер жив ∨ для истории снятого (`state="resolved"`).',
        "`state` — `open` | `resolved` (конвенция).",
        '`[open]git-blocker state="resolved"[sep]СНЯТ 2026-10-02: коммиты по путям идут.[close]git-blocker[sep]`'),
    Man("doc", "invariants",
        "что обязано остаться правдой при любом продолжении.", "∀ документ, по которому кто-то будет действовать.",
        "нет.", "`[open]invariants[sep]Чужой lock ¬ обходить; коммит только по слову user.[close]invariants[sep]`"),
    Man("doc", "item",
        "один пункт перечня.", "только внутри `items`.", "`id`.",
        '`[open]item id="a"[sep]first finding[close]item[sep]`'),
    Man("doc", "items",
        "контейнер пунктов `item`.", "перечень однородных находок ∨ записей.", "нет.",
        '`[open]items[sep][open]item id="a"[sep]…[close]item[sep][close]items[sep]`'),
    Man("doc", "mission",
        "одна цель документа (программы, плана).", "документ-программа под корнем `task`; одна на документ.", "нет.",
        "`[open]mission[sep]Поставить каждый выбор на явную математику.[close]mission[sep]`"),
    Man("doc", "next-action",
        "один следующий шаг, с которого продолжает принявший трек.",
        "в `handoff`; закрытый шаг помечать «СДЕЛАНО <дата>», ¬ удалять до следующего среза.", "`id` — slug шага.",
        '`[open]next-action id="commit-mine"[sep]Коммит только путём: git commit -- '
        "<path>.[close]next-action[sep]`"),
    Man("doc", "note",
        "оговорка, ¬ меняющая смысл документа.", "пояснение, которое читателю полезно, но действий ¬ требует.",
        "нет.", "`[open]note[sep]no outward publishing[close]note[sep]`"),
    Man("doc", "peers",
        "соседи по контуру — кто (actor `agent:sid`) ∧ над чем работает ∧ чего от него ждать.",
        "в `handoff`, если рядом живые сессии ∨ чужие lock'и. ¬ путать с `peer` профиля delegation (один сосед в "
        "карточке).", "нет; одна строка на соседа.",
        "`[open]peers[sep]claude:a1b2c3d4 — ведёт git-resync <config-repo>; ждать «done».[close]peers[sep]`"),
    Man("doc", "remaining",
        "один открытый (∨ закрытый в этом срезе) хвост трека.",
        "в `handoff`, по элементу на хвост; повтор тега законен (валидатор предупреждает «встречается дважды»).",
        "`id` — сквозной номер хвоста; `sev` — `trivial` | `low` | `med` | `high`; `state` — свободная метка "
        "(`open-by-user`, `done-r11`); нет `state` ⇒ открыт.",
        '`[open]remaining id="3" sev="med"[sep]Панель на одной модели — отдельный трек.[close]remaining[sep]`'),
    Man("doc", "section",
        "именованный раздел документа общего вида.", "под корнем `doc`, когда специального тега нет.", "`id`.",
        '`[open]section id="scope"[sep]What this summary covers.[close]section[sep]`'),
    Man("doc", "status",
        "текущее состояние трека одним абзацем: что сведено, что проверено после рестарта, что открыто.",
        "в `handoff` первым разделом; один на срез.", "нет.",
        "`[open]status[sep]Цикл сведён; check.py all = 75/75 OK.[close]status[sep]`"),
    Man("doc", "step",
        "один шаг программы.", "только внутри `steps`.",
        "`id`; `status` — `done` | `planned` (конвенция program.py); `item` — id цели `t`.",
        '`[open]step id="X1.1" status="done" item="X1"[sep]evidence: 12/12[close]step[sep]`'),
    Man("doc", "steps",
        "контейнер шагов `step`.", "явная последовательность работ в документе-программе.", "нет.",
        '`[open]steps[sep][open]step id="X1.1"[sep]…[close]step[sep][close]steps[sep]`'),
    Man("doc", "t",
        "одна цель программы.", "только внутри `targets`.",
        "`id`; `progress` — `сделано/всего`; `doc` — путь документа цели.",
        '`[open]t id="X1" progress="2/2" doc="items/X1.xtml"[sep]intervals[close]t[sep]`'),
    Man("doc", "targets",
        "контейнер целей `t`.", "документ-программа с несколькими целями.", "нет.",
        '`[open]targets[sep][open]t id="X1"[sep]…[close]t[sep][close]targets[sep]`'),
    Man("doc", "track-dir",
        "каталог трека ∧ ключевые файлы в нём (план, проверка, отчёт, ledger).",
        "в `handoff`, чтобы принявший нашёл артефакты без поиска.", "нет; абсолютный путь первым.",
        "`[open]track-dir[sep]<tracks>/<трек> — plan.yaml, check.py, "
        "REPORT.md.[close]track-dir[sep]`"),
    Man("doc", "verify",
        "команды перепроверки состояния с ожидаемым выводом — чем принявший убеждается, что срез правдив.",
        "в `handoff`; ∀ утверждение `status` ⇒ команда здесь.", "нет.",
        "`[open]verify[sep]python -B check.py all (ожидание 75/75 OK)[close]verify[sep]`"),
)


def selfcheck(profiles: dict[str, tuple[str, ...]], man: tuple[Man, ...]) -> list[str]:
    """Every way the lists and the articles can disagree. Pure: the suite feeds it broken inputs directly."""
    bad: list[str] = []
    for p, tags in profiles.items():
        twice = sorted({t for t in tags if tags.count(t) > 1})
        if twice:
            bad.append(f"{p}: тег повторяется в словаре — " + ", ".join(twice))
    keys = [(m.profile, m.tag) for m in man]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        bad.append("статья повторяется: " + ", ".join(f"{p}/{t}" for p, t in dupes))
    for m in man:
        empty = [f for f in ("purpose", "when", "attrs", "example") if not str(getattr(m, f)).strip()]
        if empty:
            bad.append(f"{m.profile}/{m.tag}: пустые поля статьи — " + ", ".join(empty))
    stray = sorted({m.profile for m in man} - set(profiles))
    if stray:
        bad.append("статьи профиля, которого нет: " + ", ".join(stray))
    for p, tags in profiles.items():
        arts = {m.tag for m in man if m.profile == p}
        if set(tags) - arts:
            bad.append(f"{p}: тег без статьи — " + ", ".join(sorted(set(tags) - arts)))
        if arts - set(tags):
            bad.append(f"{p}: статья-сирота (тега нет в словаре) — " + ", ".join(sorted(arts - set(tags))))
    return bad


_bad = selfcheck(PROFILES, MAN)
if _bad:
    raise VocabError("vocab.py противоречит сам себе: " + " · ".join(_bad))
# tag -> reason printed when the section is missing; order of CORE = order of the report
MANDATORY = {t: next(m.purpose for m in MAN if m.profile == "delegation" and m.tag == t) for t in CORE}


def articles(tag: str | None = None, profile: str | None = None) -> list[Man]:
    return [m for m in MAN if (tag is None or m.tag == tag) and (profile in (None, "any") or m.profile == profile)]


def render(m: Man) -> str:
    return (f"{m.tag} — профиль {m.profile}\n  назначение: {m.purpose}\n  когда:      {m.when}\n"
            f"  атрибуты:   {m.attrs}\n  пример:     {m.example}")


def index(profile: str | None = None) -> str:
    out = []
    for p, text in INTRO:
        if profile in (None, "any", p):
            out.append(f"профиль {p}: {text}")
            out += [f"  {m.tag:24} {m.purpose}" for m in articles(profile=p)]
    return "\n".join(out)


def card_format() -> dict:
    """The JSON projection: data only (the prose "why"/"notes" of the old file live above as comments)."""
    return {"_generated_from": "tools/xtml/vocab.py", "schema": SCHEMA,
            "sections": {"mandatory": list(CORE), "known_extra": list(KNOWN_EXTRA),
                         "enforced_count": dict(ENFORCED_COUNT)},
            "capability_keys": list(CAPABILITY_KEYS), "matrix_flags": list(MATRIX_FLAGS),
            "routing_fields": list(ROUTING_FIELDS), "routing_optional": list(ROUTING_OPTIONAL),
            "phases": list(PHASES), "loop_classes": list(LOOP_CLASSES),
            "message": json.loads(json.dumps(MSG)), "doc": json.loads(json.dumps(DOC))}


def projection_path() -> Path:
    """ops tree: <root>/config/card-format.json; portable skill copy: scripts/card-format.json next to this file."""
    here = Path(__file__).resolve()
    ops = here.parents[2] / "config"
    return ops / "card-format.json" if ops.is_dir() else here.with_name("card-format.json")


def main(argv: list[str]) -> int:
    path, want = projection_path(), json.dumps(card_format(), ensure_ascii=False, indent=1) + "\n"
    if "--write" in argv:
        path.write_text(want, encoding="utf-8", newline="\n")
        print(f"записано: {path}")
        return 0
    if "--check" not in argv:
        print(__doc__.split("\n\n")[0])
        return 2
    have = path.read_text(encoding="utf-8").replace("\r\n", "\n") if path.is_file() else ""
    if have == want:
        print(f"проекция совпадает: {path}")
        return 0
    print(f"ДРЕЙФ: {path} ≠ проекция vocab.py ({len(have)} против {len(want)} знаков) — правят vocab.py, затем "
          "python vocab.py --write; правка JSON руками ∨ пропавший файл = дрейф")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
