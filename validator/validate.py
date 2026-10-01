#!/usr/bin/env python3
"""Check that an XTML-notation prompt is well-formed before it is sent anywhere.

    python validate.py <file>                  # report to stdout
    python validate.py <file> --profile kimi   # vocabulary of the K3 chat template
    python validate.py <file> --strict         # unknown tags become a failure too
    python validate.py <file> --profile message  # peer message card agent<->agent (W65, peer-bus)
    python validate.py <file> --profile doc      # document (program, plan): grammar + closed vocabulary, no card core
    python validate.py -                       # read the prompt from stdin

    exit 0  clean
    exit 1  vocabulary complaint only (unknown tags, and --strict was asked for)
    exit 2  structurally malformed

WHY THE CODES ARE ORDERED THAT WAY

    Claude Code hooks treat exit 2 as blocking and exit 1 as advisory. An earlier version
    had it backwards — a broken document exited 1 and a harmless typo exited 2 — so a hook
    built on it would have waved through the malformed card and blocked the cosmetic one.
    Severity now rises with the code.

WHY THIS EXISTS

    XTML (arXiv 2607.24653, appendix F) replaces the angle brackets of XML with three
    reserved tokens, [open] [sep] [close], plus [end_of_msg] as the stop marker. On Kimi K3
    those are real vocabulary entries. Written into a prompt for any other model they are
    ordinary characters, and every guarantee that came from being a token is gone: nothing
    stops an unbalanced element, a stray [close], or a marker smuggled inside an attribute
    value. This file is what puts a floor back under the notation.

WHAT AN EMPTY RESULT MEANS HERE

    A file with no elements is not a valid document, it is a document that was never
    written — most often a card whose author forgot the markup. Reporting "0 elements, all
    good" would be the counting gate that cannot tell "nothing found" from "nothing to
    look at", so zero elements is an error.

WHO CALLS THIS, INCLUDING FROM OUTSIDE THIS CONTOUR

    Inside: no hook runs it since 2026-08-23 (hooks/xtml-card-guard.ps1 retired with the Claude
    contour); the suites next to it (run_suites.py, test_*.py) do, and the skill carries a byte-identical copy.

    Outside: <ops-root>\\scripts\\xtml-validate-hermes.py declares itself a wrapper and
    invokes THIS FILE through a subprocess, closing on its exit code, and
    <ops-root>\\hooks\\preflight-gate.py quotes the invocation form at line 629. That
    contour is not ours and does not track our changes, so the exit-code contract above is
    a published interface, not an internal detail: renumbering the codes or promoting a
    warning to fatal silently changes the verdict of a consumer nobody here will think to
    re-run. Found by inventory 2026-08-05; before that the dependency was recorded nowhere.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path, PureWindowsPath

try:
    import regex
except ImportError:  # pragma: no cover - проверяется отдельным случаем набора
    # Без внятного сообщения отсутствие модуля выглядит как «валидатор сломан»: набор
    # краснеет на ВСЕХ входах, включая обязанные зеленеть, и это ровно та подпись, по
    # которой окружение отличается от логики. Один раз в этом контуре синтаксическая
    # ошибка уже роняла процесс на импорте, а гейт восемь раз отчитался «дефект пойман».
    print("ОШИБКА: не установлен модуль regex — он нужен для юникодных свойств "
          "(\\p{Bidi_Control}, \\p{Default_Ignorable_Code_Point}), которых нет в re. "
          "Установить: python -m pip install regex. Это отказ ИНСТРУМЕНТА, а не вердикт "
          "о карточке: считать её проверенной нельзя.", file=sys.stderr)
    raise SystemExit(2)

OPEN, SEP, CLOSE, EOM = "[open]", "[sep]", "[close]", "[end_of_msg]"

VOCAB = {
    "kimi": {"message", "think", "response", "tools", "call", "argument"},
    "delegation": {
        # Обязательное ядро. Каждый закрывает документированный провал делегирования и
        # совпадает по смыслу с REQUIRED в tools/delegate/validate-card.py.
        "task", "mission", "invariants", "source-of-truth", "acceptance",
        "write-scope", "stop-conditions", "report-path",
        # Остальное — по надобности.
        "role", "context", "input", "constraints", "forbid", "require",
        "response-format", "queries", "q", "targets", "t", "steps", "step",
        "note", "handoff", "budget", "routing",  # routing JSON: strict 13-field check here (_routing_complaint); evidence_router picks the tier.
        "prior", "channel", "deviation", "counter-example", "escalate", "peer", "sync", "depends-on", "evidence", "timebox",
    },
}

# ⛔ Канон v2 §4 добавляет пять опциональных разделов (loop-class, capability-requirements,
# context-budget, report-schema, seed-policy), но в VOCAB им НЕ место: словарь профиля сверен
# check_vocab_sync.py с SKILL.md скилла в обе стороны, а SKILL.md — собственность
# пользователя и этой волной не меняется. Разделы объявлены отдельно в V2_SECTIONS ниже;
# профиль постановки передаёт их сканеру как известные теги, иначе каждая законная
# карточка v2 получала бы пять ложных предупреждений «вне словаря», а под --strict —
# отказ на каноничной форме.

# [end_of_msg] is a layer-T generation stop marker. Inside a K3 chat template it belongs;
# inside a delegation card written as plain text it is the one construct that would change
# behaviour if the card ever reached a K3-family stack. The skill forbids it there, so the
# validator enforces it there — a rule only the prose knows is not a rule.
EOM_ALLOWED = {"kimi", "any", "message"}  # message: W65, прил. F

# Глубина вложенности ограничена: корень + два уровня разделов. Глубже — патология:
# карточка с четырьмя уровнями (адверсарная находка V5) читается машиной, но ни один
# делегат не разбирает её согласованно, и обязательное ядро на глубине не проверяется.
# Три уровня остаются законными (task → steps → step), четвёртый — отказ.
MAX_NEST_DEPTH = 3
# App. F Fig. 16 nests message > tools > call > argument: four levels. The kimi profile checks the
# original notation, so its ceiling is the original one (cXTML/1.0: every App. F document is valid).
KIMI_NEST_DEPTH = 4

# Скобки могут сойтись у карточки, которая ничего не поручает. Замерено адверсарным
# разбором: пять структурно безупречных и семантически мёртвых карточек — пустая приёмка,
# карточка из одного note, приёмка прозой, документ без корня — получали код 0. Проверка,
# зелёная на такой карточке, читается как «карточка годная», а означает «скобки сошлись».
# Состав ядра сведён с REQUIRED в tools/delegate/validate-card.py: там те же провалы
# делегирования закрыты для внешнего контура.
MANDATORY = {
    "task": "корень: без него это не карточка",
    "mission": "единственная задача; без неё делегат выберет её сам",
    "invariants": "что обязано остаться правдой; голая цель решается занулением",
    "source-of-truth": "факты и пути; без них «не нашёл» неотличимо от «не искал»",
    "acceptance": "команда приёмки; единственное место, где отчёт опровержим",
    "write-scope": "границы записи; делает «не тронул» проверяемым",
    "stop-conditions": "когда доложить, а не дожимать любой ценой",
    "report-path": "куда класть результат",
}
# Приёмка обязана быть исполнимой. Само правило живёт в tools/cmdcheck.py: тот же вопрос
# задаёт генератор пояснительной записки, и две копии одного правила разошлись молча —
# здесь оно судило префиксом и принимало «github» под «git», там подстрокой и принимало
# любую фразу со словом «python». Общий модуль делает расхождение невозможным, а не
# маловероятным.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmdcheck  # noqa: E402

# ASCII by construction — NOT \w, which this module treats as Unicode. A tag written
# "rоle" with a Cyrillic "о" is pixel-identical to "role"; with \w it parses, and if both
# tags carry the same homoglyph the document balances while meaning something else.
NAME = r"[A-Za-z][A-Za-z0-9._-]*"
MARKER = regex.compile(r"\[open\]|\[sep\]|\[close\]|\[end_of_msg\]")
OPEN_PAYLOAD = regex.compile(rf'^({NAME})((?:\s+{NAME}="[^"]*")*)\s*$')
CLOSE_PAYLOAD = regex.compile(rf"^({NAME})\s*$")
ATTR = regex.compile(rf'({NAME})="([^"]*)"')
ATTR_LOOSE = regex.compile(r"[\w.-]+\s*=")
NON_ASCII = regex.compile(r"[^\x00-\x7F]")
# Markers hidden in an attribute value. [sep] cannot appear (it would end the header), so
# the smuggling channel is the ones that survive: the bare brackets and the stop marker.
MARKER_IN_VALUE = regex.compile(r"\[open\]|\[close\]|\[end_of_msg\]")
# cXTML/1.0 literal regions (owner rule 2026-10-01). A reserved marker inside a CommonMark code span
# (a run of N backticks ... the next run of exactly N backticks in the same paragraph) or inside a
# fenced block (``` or ~~~ at a line start, closed by a line of the same character, length >= the
# opening run) is TEXT, not markup. An opener without its closer escapes nothing: the marker counts.
# Literal regions exist only in element content: headers and attribute values never carry markers.
LITERAL_OPEN = regex.compile(r"(?m)^ {0,3}(?P<fence>`{3,}(?=[^`\n]*$)|~{3,})|(?P<ticks>`+)")
TICKS = regex.compile(r"`+")
BLANK_LINE = regex.compile(r"\n[ \t]*\n")


def _literal_end(text: str, lo: regex.Match) -> int | None:
    """End offset of the literal region opened by `lo`, or None when it is never closed."""
    if lo.group("fence"):
        run = lo.group("fence")
        close = regex.compile(rf"(?m)^ {{0,3}}{regex.escape(run[0])}{{{len(run)},}}[ \t]*$")
        nl = text.find("\n", lo.end())
        m = close.search(text, nl + 1) if nl != -1 else None
        return m.end() if m else None
    n = len(lo.group("ticks"))
    para = BLANK_LINE.search(text, lo.end())
    for t in TICKS.finditer(text, lo.end(), para.start() if para else len(text)):
        if len(t.group(0)) == n:
            return t.end()
    return None


def _next_marker(text: str, i: int, literal_hits: list[int]) -> regex.Match | None:
    """Next reserved marker at or after i that is not inside a literal region."""
    while True:
        m = MARKER.search(text, i)
        if not m:
            return None
        lo = LITERAL_OPEN.search(text, i)
        if not lo or lo.start() >= m.start():
            return m
        end = _literal_end(text, lo)
        if end is None:
            i = lo.end()            # unclosed opener: plain text, markers after it count
            continue
        if MARKER.search(text, lo.start(), end):
            literal_hits.append(lo.start())
        i = end


# Раньше здесь стоял список из шести кодовых точек. Список этого класса недостижим: Unicode
# определяет его СВОЙСТВОМ Default_Ignorable_Code_Point, и одних только назначенных символов
# класса, отсутствовавших в той шестёрке, — 399 штук (замер разведки по базе UCD 15.1).
# Поэтому вопрос перевёрнут: не «нет ли здесь запрещённого», а «есть ли здесь хоть один
# печатаемый». Печатаемый — это Graphic минус пробелы: категория Zs официально входит в
# Graphic, и без её вычитания строка из неразрывных пробелов читалась бы как заполненная.
# ⛔ Вычитание Default_Ignorable обязательно, и без него правило дырявое ровно там, где
# оно нужно. Замер разведки: U+3164 HANGUL FILLER, U+115F, U+1160 и U+FFA0 имеют
# категорию Lo — формально БУКВЫ, — не входят ни в \p{C}, ни в \p{Z} и при этом не рисуют
# на экране ничего. Раздел из них прошёл бы как заполненный. Готовые \p{Graph} и \p{Print}
# тоже не годятся: в модуле regex они включают и мягкий перенос, и нулевую ширину, и
# приватный диапазон — расхождение с правильным набором больше ста тридцати тысяч точек.
PRINTABLE = regex.compile(r"[^\p{C}\p{Z}\p{Default_Ignorable_Code_Point}]")
# Управляющие символы двунаправленного письма — отдельная ошибка, а не пустота: они не
# делают текст пустым, они делают его означающим не то, что видно на экране. Ровно двенадцать
# кодовых точек, свойство Bidi_Control; класс уязвимостей известен как Trojan Source
# (CVE-2021-42574).
BIDI_CONTROL = regex.compile(r"\p{Bidi_Control}")
# Снимать перед сравнением по-прежнему нужно: раздел, где содержимое разбавлено нулевой
# шириной, не должен считаться отличающимся от того же раздела без неё.
IGNORABLE = regex.compile(r"\p{Default_Ignorable_Code_Point}")


def _meaningful(s: str) -> str:
    """Content with ignorable code points removed.

    `str.strip()` does not touch zero-width space, word joiner or soft hyphen, so a
    section built from them read as filled while carrying nothing.
    """
    return IGNORABLE.sub("", s).strip()


def _has_printable(s: str) -> bool:
    """At least one character that actually shows up on screen."""
    return bool(PRINTABLE.search(s))


# Слова, которыми обозначают «сюда ещё надо написать». Сверяются по НОРМАЛИЗОВАННОЙ форме:
# точное равенство пропускало «TODO.» с точкой, «TBD!» и «— » с обрамляющими пробелами,
# то есть ровно те написания, в которых заглушка и встречается.
# Пустой строки здесь быть НЕ должно, и это не мелочь: раздел, которого в карточке нет,
# приходит сюда как "" через content.get(t, ""), и заглушечное правило начинало отвечать
# за случай отсутствия. Мутационный прогон это и поймал — снятие проверки обязательных
# разделов пережило набор, потому что все три случая продолжали краснеть, но уже по чужой
# причине. Пустоту ловит своя проверка, и подменять её нельзя.
# ⛔ Знака вопроса здесь быть НЕ должно, хотя он и просится: нормализация срезает
# пунктуацию с краёв, и одиночный «?» превращается в пустую строку ДО сверки. Запись в
# списке была мертва — правило, которое нельзя нарушить, потому что оно ни на чём не
# срабатывает. Такие строки ловит проверка ниже, по остатку.
STUB_WORDS = {"TODO", "TBD", "FIXME", "XXX", "NA", "N/A", "WIP",
              "ЗАГЛУШКА", "ПОЗЖЕ", "УТОЧНИТЬ", "СМ. ВЫШЕ", "СМ ВЫШЕ"}
PUNCT_EDGE = regex.compile(r"^[\p{P}\p{S}\s]+|[\p{P}\p{S}\s]+$")
# Пути, упомянутые в области записи. Она пишется прозой («Только tools/xtml/, отчёт
# по пути ниже»), поэтому из неё выуживаются фрагменты, похожие на путь, а не парсится
# структура: строгий разбор прозы отверг бы законные карточки.
SCOPE_PATH = regex.compile(r"[A-Za-z]:[\\/][^\s,;«»]+|[\w.\-]+[\\/][\w.\-\\/]*")
# Формы, стирающие или переписывающие состояние. Список намеренно узкий: он поднимает
# предупреждение, а не отказ, и широкий список превратил бы обычную уборку временного
# каталога в помеху. Ищутся ИСПОЛНЯЕМЫЕ формы, а не упоминания слова.
DESTRUCTIVE = regex.compile(
    r"\brm\s+-[rf]|\bshutil\.rmtree|\bRemove-Item\b[^\n]*-Recurse|\bdel\s+/[sq]|"
    r"\bgit\s+reset\s+--hard|\bgit\s+clean\s+-[fdx]|\bgit\s+push\s+--force|"
    r"\bDROP\s+(?:TABLE|DATABASE)\b|\bformat\s+[A-Za-z]:|\bTRUNCATE\b", regex.I)


def _stub_shape(body: str) -> bool:
    """Is this section a placeholder rather than content?

    Two ways to be one, and the list is only the first. The second is the reason the list
    cannot be completed: a section that is ENTIRELY punctuation — "—", "...", "?", "!!!" —
    normalises to nothing at all. It has printable characters, so the emptiness check
    passes it, and it matches no word, so a word list passes it too. Measured: six such
    spellings went green. The remainder after normalisation is the honest question, the
    same inversion that replaced the list of invisible code points.
    """
    text = _meaningful(body)
    if not text:
        return False                       # отсутствие и пустота — не эта проверка
    core = PUNCT_EDGE.sub("", text).upper()
    return core in STUB_WORDS or not core


def _path_complaint(rp: str) -> str | None:
    """Why this report path is not acceptable, or None if it is.

    Two independent questions, and mixing them is what the previous version did wrong.

    FORM. Windows offers seven categories of path and `is_absolute()` is true for only
    some of them. Measured by recon across 27 shapes: `C:report.md` is drive-RELATIVE and
    lands in the current directory of drive C:, `\\Windows\\x` is rooted on the current
    drive, and both return False from `is_absolute()` while still pointing anywhere. In
    the other direction UNC (`\\\\srv\\share`), the extended prefix (`\\\\?\\C:`) and device
    paths (`\\\\.\\pipe`) all return True. So an absolute path is accepted only in the one
    unambiguous form: a fully-qualified DOS path, drive letter and root both present.

    PLACEMENT. Decided by the filesystem, never by string comparison. `startswith(home)`
    has a live counter-example on this machine right now: `<home>.omx-worktrees`
    is a real directory, is not inside the home directory, and passes that test. Both
    sides are resolved because the contour itself may sit behind a junction.

    A RELATIVE path stays legal — that is the ordinary shape here (`scratchpad/out.md`) —
    provided it climbs nowhere. Rejecting relative paths would repeat the mistake this
    rule already made once in the opposite direction.
    """
    # Обратные кавычки вокруг пути — оформление, а не часть имени: путь в них написан в
    # половине наших же документов. Отвергать их значит отвергать законную карточку.
    rp = rp.strip("`\"' ")
    if not _has_printable(rp):
        return "в пути нет ни одного печатаемого символа"
    if any(ord(c) < 32 for c in rp):
        return "управляющие символы внутри пути"
    # Путь обязан быть путём. Проверялась безопасность строки и не проверялось, что это
    # вообще путь: «куда-нибудь в scratchpad, сам решишь» проходило чисто, потому что не
    # содержит ни диска, ни корня, ни выхода вверх. Делегат в таком случае решает сам, и
    # отчёт оказывается там, где его никто не ищет.
    tokens = rp.split()
    if len(tokens) > 1:
        return ("это не путь, а фраза из нескольких слов — делегат выберет место сам, "
                "и отчёт окажется там, где его никто не ищет")
    if not regex.search(r"[/\\]|\.[A-Za-z0-9]{1,8}$", rp):
        return ("ни разделителя каталогов, ни расширения файла — на путь не похоже; "
                "каталог вместо файла тоже не годится, отчёт пишется в файл")
    # Тильда в начале — не «неразвёрнутая переменная», а общепринятая запись домашнего
    # каталога, которой написана половина команд в наших же правилах. Прежняя редакция
    # валила её вместе с процентами и $env: — ложный отказ на законной форме.
    if regex.search(r"%|\$env:|\$\{|(?<!^)~", rp):
        return ("неразвёрнутая переменная окружения — во что она развернётся, решает "
                "оболочка делегата, и проверяющий этого не видит")

    p = PureWindowsPath(rp)
    if any(part in ("..", ".") for part in p.parts):
        # Компонентом, а не подстрокой: подстрока отвергала законное имя «otchet..md»
        # и при этом пропускала сетевой путь, где двух точек нет вовсе.
        return "компонент «..» или «.» — куда он ведёт, зависит от каталога запуска делегата"
    if regex.search(r"^..[^\\/]*:|(?<=[^:]):(?!$)", rp[2:] if len(p.drive) == 2 else rp):
        return "двоеточие вне буквы диска — это альтернативный поток NTFS, а не файл"

    if not p.drive and not p.root:
        return None                      # ordinary relative path, climbs nowhere
    if not (p.is_absolute() and len(p.drive) == 2 and p.drive[1] == ":"
            and p.drive[0].isascii() and p.drive[0].isalpha()):
        return (f"не полностью квалифицированный путь (диск {p.drive!r}, корень {p.root!r}) "
                f"— форма уводит туда, где делегату писать нечего")

    home = Path(os.path.realpath(Path.home(), strict=False))
    real = Path(os.path.realpath(rp, strict=False))
    if not real.is_relative_to(home):
        return f"ведёт за пределы домашнего контура — на деле в {real}"
    return None


def _is_command(text: str) -> bool:
    """The acceptance criterion is a command or it is not a criterion.

    The rule itself lives in tools/cmdcheck.py because the task registry asks the same
    question, and two copies of one rule drift without a word — they already had, in
    opposite directions, on the same day. Here it is only wrapped: invisible code points
    are stripped first, so a command spelled with a zero-width space inside is judged on
    what it actually says.
    """
    return cmdcheck.is_command(_meaningful(text))


# === Канон v2 §4: опциональные разделы со словарями значений ============================
# Пять разделов валидируются только при ПРИСУТСТВИИ: старые карточки (ядро из восьми)
# обязаны оставаться зелёными без единого изменения. Каждый раздел имеет словарь
# допустимых значений; нарушение словаря — отказ (код 2), потому что раздел несёт
# машинно-читаемое поручение (класс цикла, требования к возможностям, бюджет контекста),
# и пропустить искажённое поручение хуже, чем отвергнуть карточку. Содержимое перед
# проверкой проходит _meaningful: раздел, разбавленный нулевой шириной, обязан судиться
# по тому, что в нём на деле написано.
LOOP_CLASSES = ("one-shot", "continuable", "ralph-round")
CAPABILITY_KEYS = ("vision", "terminal", "long-context", "reasoning")
# One resolution of the format owner for every reader below, two layouts (2026-09-29): the ops
# tree (<root>/tools/xtml/validate.py + <root>/config/card-format.json) and the portable skill
# copy, which carries card-format.json next to itself. Before this, the skill copy could not find
# the file at all and rejected every card over «routing». Byte-identity of the copies is enforced
# by tools/xtml/check_vocab_sync.py. No absolute install path: XTML_CARD_FORMAT overrides, else
# the file is found relative to this validator (a relocated tree keeps working; test clones carry
# their own config/card-format.json).
_CARD_FORMAT = next(
    (p for p in ((Path(os.environ["XTML_CARD_FORMAT"]),) if os.environ.get("XTML_CARD_FORMAT") else ())
     + (Path(__file__).resolve().parents[2] / "config" / "card-format.json",
        Path(__file__).resolve().with_name("card-format.json")) if p.is_file()),
    Path(__file__).resolve().parents[2] / "config" / "card-format.json")
# W1a-K2 2026-09-26: loop-class vocabulary also has ONE owner (card-format.json);
# the tuples above are fallbacks only, same contract as CAPABILITY_KEYS below.
try:
    LOOP_CLASSES = tuple(
        json.loads(_CARD_FORMAT.read_text(encoding="utf-8")).get("loop_classes", ())
    ) or LOOP_CLASSES
except Exception:
    pass
# The card vocabulary has ONE owner (config/card-format.json); the tuple above is only the
# fallback. Keeping them equal by hand is what made a matrix-mandated key ('mechanical')
# illegal in the very card that had to state it. A missing file is reported, not ignored.
try:
    CAPABILITY_KEYS = tuple(
        json.loads(_CARD_FORMAT.read_text(encoding="utf-8"))["capability_keys"]
    )
except (OSError, ValueError, KeyError, TypeError) as _exc:
    print(f"card-format.json unusable ({type(_exc).__name__}); using the built-in vocabulary",
          file=sys.stderr)
# W65 2026-10-01 (выровнено W68 2026-10-01 по encoding_k3.py): профиль message — горизонтальная карта агент↔агент
# (peer message), ¬ постановка. Грамматика первоисточника (arXiv 2607.24653, прил. F; код encoding_k3.py — истина):
# верхняя единица message с role; роли прил. F — system | user | tool | assistant, межагентное сообщение — role="peer"
# (расширение cXTML [X], ¬ прил. F); запрос к соседу МОЖЕТ нести call tool= index= с дочерними argument key= type=
# (_render_assistant_segments); ответ на вызов несёт tool= index= вызова, как результат инструмента прил. F
# (message role="tool" tool= index=); argument name= — устаревший алиас key= (предупреждение); [end_of_msg] допустим
# в конце. Наши атрибуты id / from / to / type / re и разделы subject / body / evidence / needs / until — поверх. Владелец словаря — блок "message" в card-format.json (контракт как у
# CAPABILITY_KEYS: словарь ниже — запасной). Карту читает машина (peer-bus send --xtml, messages.jsonl), поэтому
# неизвестный раздел или атрибут — отказ, а не предупреждение: это канал доставки непроверенного текста соседу.
MSG = {"root": "message", "role": "peer", "attrs": ["role", "id", "from", "to", "type", "re"],
       "optional_attrs": ["tool", "index"], "types": ["REQ", "ACK", "NACK", "INFO", "CLAIM", "CONFLICT", "HANDOFF", "ESCALATE"],
       "sections": ["subject", "body", "evidence", "needs", "until"], "until_required": ["REQ", "CLAIM", "CONFLICT"],
       "needs_none_ok": ["INFO", "ACK"], "re_required": ["ACK", "NACK"], "closing_types": ["ACK", "NACK", "HANDOFF"],
       "call": {"tag": "call", "attrs": ["tool", "index"], "argument": "argument", "argument_attrs": ["key", "type"],
                "argument_alias": {"name": "key"}, "types": ["REQ", "CLAIM", "CONFLICT"]}}
try:
    MSG = {**MSG, **json.loads(_CARD_FORMAT.read_text(encoding="utf-8")).get("message", {})}
except (OSError, ValueError, TypeError, AttributeError):
    pass
VOCAB["message"] = {MSG["root"], *MSG["sections"], MSG["call"]["tag"], MSG["call"]["argument"]}
# W73 2026-10-01 (X11.1): профиль doc — документ (программа, план, сводка), ¬ постановка ∧ ¬ сообщение. Прежде у документа
# не было профиля: any = только грамматика (код 1 по замыслу), delegation требует ядро карточки, и потребитель сверял
# словарь сам. Здесь грамматика + закрытый словарь (тег вне словаря — отказ, код 2: документ читает машина) + корень из
# roots; ядра нет. Владелец словаря — блок "doc" в card-format.json (контракт как у MSG: ниже запасной).
DOC = {"roots": ["doc", "task"],
       "elements": ["evidence", "invariants", "item", "items", "mission", "note", "section", "step", "steps", "t",
                    "targets"]}
try:
    DOC = {**DOC, **json.loads(_CARD_FORMAT.read_text(encoding="utf-8")).get("doc", {})}
except (OSError, ValueError, TypeError, AttributeError):
    pass
VOCAB["doc"] = {*DOC["roots"], *DOC["elements"]}
# Адрес actor'а peer-bus (W44): agent:sid — основной поток, agent:sid:<agent_id> — субагент; в to ещё
# agent:sid:* (все живые actor'ы сессии) и lane:<имя> (полоса). ASCII по построению, как NAME. Разбор адреса для
# доставки — один, agents.addr в peer-bus; здесь только форма.
MSG_ACTOR = regex.compile(r"^(?:claude|codex|hermes):[A-Za-z0-9._-]+(?::[A-Za-z0-9._-]+)?$")
MSG_TO = regex.compile(r"^(?:(?:claude|codex|hermes):[A-Za-z0-9._-]+(?::(?:[A-Za-z0-9._-]+|\*))?|lane:[A-Za-z0-9._-]+)$")
MSG_ID = regex.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _message_complaints(rep: Report) -> list[str]:
    """Defects of a peer message card (profile message)."""
    from datetime import datetime
    if rep.root != MSG["root"]:
        return [f"корневой элемент «{rep.root}» — сообщение обязано начинаться с «{MSG['root']}»"]
    a, bad = rep.attrs, []
    missing = [k for k in MSG["attrs"] if k not in a]
    if missing:
        return [f"у «{MSG['root']}» нет атрибутов — " + ", ".join(missing)]
    extra = set(a) - set(MSG["attrs"]) - set(MSG["optional_attrs"])
    if extra:
        bad.append(f"у «{MSG['root']}» неизвестные атрибуты — " + ", ".join(sorted(extra)))
    if a["role"] != MSG["role"]:
        bad.append(f"role «{a['role'][:20]}» — межагентное сообщение несёт role=\"{MSG['role']}\" (расширение cXTML; "
                   "роли прил. F system | user | tool | assistant — encoding_k3.py, «other» там нет)")
    t = a["type"]
    if t not in MSG["types"]:
        bad.append(f"type «{t}» вне словаря — допустимы: " + " | ".join(MSG["types"]))
    if not MSG_ID.match(a["id"]):
        bad.append(f"id «{a['id'][:40]}» — только [A-Za-z0-9._-], до 64 знаков")
    if not MSG_ACTOR.match(a["from"]):
        bad.append(f"from «{a['from'][:60]}» — не адрес actor'а agent:sid[:agent_id]")
    if not MSG_TO.match(a["to"]):
        bad.append(f"to «{a['to'][:60]}» — не agent:sid[:agent_id], не agent:sid:* и не lane:<имя>")
    if a["re"] != "none" and not MSG_ID.match(a["re"]):
        bad.append(f"re «{a['re'][:40]}» — id треда или none")
    if a["re"] == "none" and t in MSG["re_required"]:
        bad.append(f"{t} без re — отвечать не на что; re = id сообщения, на которое ответ")
    if "tool" in a or "index" in a:
        if t not in MSG["closing_types"] or a["re"] == "none":
            bad.append("tool / index на корне — только у ответа (" + " | ".join(MSG["closing_types"])
                       + ") с re: вызов call, на который ответ")
        elif "tool" not in a or "index" not in a:
            bad.append("tool и index у ответа идут парой, как у результата инструмента прил. F "
                       "(message role=\"tool\" tool= index=)")
        elif not a["index"].isdigit() or not MSG_ID.match(a["tool"]):
            bad.append("у ответа tool — имя ([A-Za-z0-9._-]), index — целое: номер вызова call")
    c = MSG["call"]
    unknown = sorted(set(rep.content) - set(MSG["sections"]) - {c["tag"], MSG["root"]})
    if unknown:
        bad.append("разделы вне профиля message: " + ", ".join(unknown)
                   + " — непроверенный текст соседу не доставляется")
    missing = [s for s in MSG["sections"] if s not in rep.content]
    if missing:
        bad.append("нет обязательных разделов сообщения — " + ", ".join(missing))
    calls = [(tag, at) for tag, depth, at in rep.elems if tag == c["tag"] and depth == 2]
    if calls and t not in c["types"]:
        bad.append(f"call у {t} — вызов на соседе несут только " + " | ".join(c["types"]))
    for tag, depth, at in rep.elems:
        if tag == c["tag"] and (depth != 2 or sorted(at) != sorted(c["attrs"]) or not at["index"].isdigit()):
            bad.append(f"«{tag}» — прямой раздел сообщения с атрибутами tool и целым index, ничего больше")
        if tag == c["argument"]:
            alias = {c.get("argument_alias", {}).get(k, k): v for k, v in at.items()}
            if sorted(alias) == sorted(c["argument_attrs"]) and len(alias) == len(at) and alias != at:
                rep.warnings.append(
                    f"устаревший атрибут «{' '.join(sorted(set(at) - set(alias)))}» у «{tag}» — замени на "
                    f"«{' '.join(sorted(set(alias) - set(at)))}» (encoding_k3.py: key + type); алиас будет снят")
            if depth != 3 or sorted(alias) != sorted(c["argument_attrs"]) or len(alias) != len(at) \
                    or not all(MSG_ID.match(v) for v in at.values()):
                bad.append(f"«{tag}» — только внутри call, атрибуты key и type ([A-Za-z0-9._-]); "
                           "name — устаревший алиас key, вместе они не ходят")
    idx = [at.get("index") for _tag, at in calls]
    if len(idx) != len(set(idx)):
        bad.append("index вызовов повторяется — ответ не сопоставить с вызовом")
    body = {s: _meaningful(rep.content[s]) for s in MSG["sections"] if s in rep.content}
    empty = [s for s, v in body.items() if not _has_printable(v)]
    if empty:
        bad.append("пустые разделы сообщения: " + ", ".join(empty))
    stubs = [s for s, v in body.items() if _stub_shape(v)]
    if stubs:
        bad.append("заглушка вместо содержимого: " + ", ".join(stubs))
    if any(BIDI_CONTROL.search(v) for v in rep.content.values()):
        bad.append("управляющие символы двунаправленного письма в разделах сообщения")
    needs, until = body.get("needs", ""), body.get("until", "")
    if needs.lower() == "none" and t not in MSG["needs_none_ok"]:
        bad.append(f"needs none у {t} — none допустим только для " + " | ".join(MSG["needs_none_ok"]))
    if until.lower() == "none":
        if t in MSG["until_required"]:
            bad.append(f"{t} без until — срок ответа обязателен (ISO с часовым поясом)")
    elif until:
        try:
            if datetime.fromisoformat(until.replace("Z", "+00:00")).tzinfo is None:
                bad.append(f"until «{until[:40]}» без часового пояса — срок неоднозначен (Z или +03:00)")
        except ValueError:
            bad.append(f"until «{until[:40]}» — не ISO-8601 (пример 2026-10-01T12:00:00+03:00) и не none")
    return bad


CONTEXT_BUDGET_KEYS = ("max-input-tokens", "report-inline-max")
SEED_POLICIES = ("none", "context-inline")
# Маркер, по которому читающий отчёт отличает вердикт от прозы. Форма зафиксирована
# каноном: «VERDICT: PASS|FAIL». Проверяется само слово — регистр значим, маркер
# протокольный, а не бытовой.
VERDICT_MARKER = "VERDICT"

_CAPABILITY_PAIR = regex.compile(r"^([A-Za-z][A-Za-z0-9-]*):(true|false)$")
# «2000» и «2000 chars» — обе формы законны (канон печатает вторую). Единица измерения —
# пояснение для человека; машинно значимо только число.
_BUDGET_ENTRY = regex.compile(r"^([A-Za-z][A-Za-z0-9-]*)\s*:\s*(\d+(?:\s+[A-Za-z]+)?)$")


def _v2_loop_class(body: str) -> str | None:
    if body in LOOP_CLASSES:
        return None
    shown = body[:40] if body else "(пусто)"
    return (f"loop-class «{shown}» вне словаря канона v2 — допустимы: "
            + ", ".join(LOOP_CLASSES))


def _v2_capability_requirements(body: str) -> str | None:
    if not body:
        return ("capability-requirements пуст — раздел без пар ключ:true|false "
                "ничего не требует")
    bad_shape = [t for t in body.split() if not _CAPABILITY_PAIR.match(t)]
    if bad_shape:
        return ("capability-requirements: записи обязаны иметь вид ключ:true|false, "
                "найдено «" + " ".join(bad_shape[:3]) + "»")
    unknown = sorted({t.split(":", 1)[0] for t in body.split()} - set(CAPABILITY_KEYS))
    if unknown:
        return ("capability-requirements: ключи вне словаря (" + ", ".join(CAPABILITY_KEYS)
                + "): " + ", ".join(unknown))
    return None


def _v2_context_budget(body: str) -> str | None:
    seen: dict[str, str] = {}
    for part in body.split(";"):
        part = part.strip()
        if not part:
            continue
        m = _BUDGET_ENTRY.match(part)
        if not m:
            return (f"context-budget: запись «{part[:40]}» не вида «ключ: целое» — "
                    f"бюджет, который нельзя сосчитать, не бюджет")
        if m.group(1) not in CONTEXT_BUDGET_KEYS:
            return (f"context-budget: ключ «{m.group(1)}» вне словаря — допустимы: "
                    + ", ".join(CONTEXT_BUDGET_KEYS))
        seen[m.group(1)] = m.group(2)
    missing = [k for k in CONTEXT_BUDGET_KEYS if k not in seen]
    if missing:
        return ("context-budget: не хватает ключей " + ", ".join(missing)
                + " — раздел объявлен, значит бюджет задан целиком: "
                + ", ".join(CONTEXT_BUDGET_KEYS))
    return None


def _v2_report_schema(body: str) -> str | None:
    if VERDICT_MARKER in body:
        return None
    return ("report-schema без маркера вердикта VERDICT — без него итог отчёта "
            "неотличим от сопроводительной прозы")


def _v2_seed_policy(body: str) -> str | None:
    parts = body.split(None, 1)
    if not parts or parts[0] not in SEED_POLICIES:
        shown = parts[0][:40] if parts else "(пусто)"
        return (f"seed-policy «{shown}» вне словаря канона v2 — допустимы: "
                + " | ".join(SEED_POLICIES))
    if parts[0] == "context-inline" and (len(parts) < 2 or not _meaningful(parts[1])):
        return ("seed-policy context-inline без пояснения — обязано быть сказано, "
                "что именно берётся из родителя и почему, иначе наследование непроверяемо")
    return None


# Отображение «раздел → проверка». Присутствие раздела в карточке запускает его проверку;
# отсутствие законно всегда. Порядок словаря фиксирует порядок сообщений.
# Канон v2 (delegation-canon, card-format/v1): routing — обязательный раздел с строгим
# JSON-пакетом из 13 полей. Единственный владелец формата — config/card-format.json;
# валидатор читает его, а не держит замороженную копию (урок 2026-09-11: mechanical
# требовался матрицей и запрещался валидатором, потому что списки жили в двух местах).
# Путь к владельцу формата — _CARD_FORMAT, разрешён один раз выше (обе раскладки).


def _routing_complaint(content: dict[str, str]) -> str | None:
    """Return an error message when the routing section is missing/invalid, else None."""
    import json as _json
    raw = content.get("routing")
    if raw is None:
        return ("нет обязательного раздела «routing» — канон v2 (card-format/v1): "
                "13-полевой строгий JSON-пакет маршрутизации")
    try:
        pkt = _json.loads(raw)
    except _json.JSONDecodeError as e:
        return f"раздел «routing» не является строгим JSON: {e}"
    if not isinstance(pkt, dict):
        return "раздел «routing» должен быть JSON-объектом"
    try:
        fmt = _json.loads(_CARD_FORMAT.read_text(encoding="utf-8"))
    except Exception as e:
        return f"не читается card-format.json ({_CARD_FORMAT}): {e}"
    required = set(fmt.get("routing_fields", []))
    optional = set(fmt.get("routing_optional", []))
    missing = required - set(pkt)
    extra = set(pkt) - required - optional
    if missing:
        return "routing: нет полей — " + ", ".join(sorted(missing))
    if extra:
        return "routing: неизвестные поля — " + ", ".join(sorted(extra))
    enums = {
        "phase": set(fmt.get("phases", [])),
        "risk": {"low", "elevated", "critical", "unknown"},
        "scope": {"local", "cross_system", "unknown"},
        "contract": {"clear", "ambiguous", "unknown"},
        "failure": {"none", "quality", "infrastructure"},
    }
    for key, allowed in enums.items():
        if pkt.get(key) not in allowed:
            return (f"routing.{key}={pkt.get(key)!r} не входит в "
                    f"{sorted(allowed)}")
    if not isinstance(pkt.get("role"), str) or not pkt["role"].strip():
        return "routing.role должен быть непустой строкой"
    if not isinstance(pkt.get("acceptance"), str) or not pkt["acceptance"].strip():
        return "routing.acceptance должен быть непустой строкой"
    ev = pkt.get("evidence")
    if not isinstance(ev, list) or not ev or not all(
        isinstance(x, str) and x.strip() for x in ev
    ):
        return "routing.evidence должен быть непустым списком строк"
    for key in ("localized", "mechanical"):
        if type(pkt.get(key)) is not bool:
            return f"routing.{key} должен быть bool"
    if not isinstance(pkt.get("escalations"), int) or isinstance(pkt.get("escalations"), bool):
        return "routing.escalations должен быть int"
    tiers = {"luna", "terra", "sol", "astra"}
    for key in ("previous_tier", "specialist"):
        val = pkt.get(key)
        if val is None:
            continue
        if not isinstance(val, str) or not val.strip():
            return f"routing.{key} — JSON null или непустая строка"
        if val.strip().lower() in {"none", "null", "-"}:
            return (f"routing.{key}='{val}' — nullable-поля используют JSON null, "
                    f"а не строки «none»")
    pt = pkt.get("previous_tier")
    if pt is not None and pt.lower() not in tiers:
        return f"routing.previous_tier='{pt}' не входит в {sorted(tiers)}"
    if pkt.get("failure") == "quality" and pkt.get("previous_tier") is None:
        return "routing.previous_tier обязателен при failure=quality"
    return None


V2_SECTIONS = {
    "loop-class": _v2_loop_class,
    "capability-requirements": _v2_capability_requirements,
    "context-budget": _v2_context_budget,
    "report-schema": _v2_report_schema,
    "seed-policy": _v2_seed_policy,
}


def _v2_complaints(content: dict[str, str]) -> list[str]:
    """Defects in the canon-v2 optional sections that are present in the card."""
    bad: list[str] = []
    for tag, check in V2_SECTIONS.items():
        if tag in content:
            msg = check(_meaningful(content[tag]))
            if msg:
                bad.append(msg)
    return bad


def _pos(text: str, idx: int) -> str:
    line = text.count("\n", 0, idx) + 1
    col = idx - (text.rfind("\n", 0, idx) + 1) + 1
    return f"строка {line}, столбец {col}"


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        # Словарные претензии держатся ОТДЕЛЬНО, потому что только они относятся к
        # --strict. Флаг документирован как «теги вне словаря считать отказом», но
        # смотрел на весь список предупреждений разом — а туда с этой сессии попали
        # смягчения, сделанные РАДИ законных карточек: путь отчёта вне объявленных
        # границ, цитата обязательного тега внутри раздела, повтор пояснительного
        # раздела, преамбула до корня. Под --strict каждое из них становилось отказом,
        # то есть флаг отменял ровно те уступки, ради которых они вводились.
        self.vocab_warnings: list[str] = []
        self.elements = 0
        self.root: str | None = None
        self.content: dict[str, str] = {}
        self.dupes: list[str] = []
        # W65: атрибуты корня и (тег, глубина, атрибуты) каждого элемента — профиль message их читает
        self.attrs: dict[str, str] = {}
        self.elems: list[tuple[str, int, dict[str, str]]] = []


def scan(text: str, vocab: set[str], eom_allowed: bool, strict_gaps: bool = True,
         max_depth: int = MAX_NEST_DEPTH) -> Report:
    """Stop at the first structural divergence: a fixer needs the place where the document
    stopped meaning what it says, not the cascade downstream."""
    r = Report()
    stack: list[tuple[str, int, int]] = []
    eom_at: int | None = None
    closed_root = False
    root_end = 0
    literal_hits: list[int] = []
    i = 0

    def fail(msg: str) -> Report:
        r.errors.append(msg)
        return r

    while True:
        m = _next_marker(text, i, literal_hits)
        if not m:
            break
        kind, start = m.group(0), m.start()

        # Text outside the root element is not part of the document and silently ignoring
        # it is how a card acquires an unnoticed second half.
        if not stack and closed_root and kind != EOM:
            return fail(f"{_pos(text, start)}: разметка после закрытия корневого элемента — "
                        f"в документе не может быть двух корней")
        # Текст, не принадлежащий ни одному разделу, есть в трёх местах, и раньше
        # проверялось только третье. Между разделами он опаснее всего: визуально он стоит
        # там же, где содержимое, и читается автором как поручение — а до делегата едет
        # никем не проверенным, потому что не лежит ни в одном элементе.
        gap = text[i:start]
        if _has_printable(gap):
            if len(stack) == 1 and strict_gaps:
                return fail(f"{_pos(text, i)}: текст «{_meaningful(gap)[:40]}» стоит между "
                            f"разделами, а не внутри раздела — он выглядит как поручение и "
                            f"ни одной проверкой не покрыт")
            if not stack and not closed_root:
                # Преамбула до корня встречается и обычно безобидна — заголовок файла,
                # комментарий автора. Ошибкой её делать нельзя: это отвергло бы законные
                # карточки, а живой сторож превращает такой отказ в остановку работы.
                r.warnings.append(f"{_pos(text, i)}: текст до корневого элемента "
                                  f"«{_meaningful(gap)[:40]}» в карточку не входит")

        if kind == EOM:
            if not eom_allowed:
                return fail(f"{_pos(text, start)}: {EOM} — маркер остановки генерации слоя "
                            f"токенов; в карточке профиля его быть не должно")
            if eom_at is not None:
                return fail(f"{_pos(text, start)}: второй {EOM} — маркер остановки один")
            if stack:
                return fail(f"{_pos(text, start)}: {EOM} внутри незакрытого элемента "
                            f"«{stack[-1][0]}»")
            eom_at = start
            i = m.end()
            continue
        if eom_at is not None:
            return fail(f"{_pos(text, start)}: {kind} стоит после {EOM} — маркер остановки "
                        f"обязан быть последним")
        if kind == SEP:
            return fail(f"{_pos(text, start)}: {SEP} без предшествующего {OPEN} или {CLOSE}")

        sep = text.find(SEP, m.end())
        if sep == -1:
            return fail(f"{_pos(text, start)}: {kind} не закрыт {SEP} до конца документа")
        payload = text[m.end():sep].strip()

        if kind == OPEN:
            pm = OPEN_PAYLOAD.match(payload)
            if not pm:
                hint = ""
                bad = NON_ASCII.search(payload.split("=", 1)[0])
                if bad:
                    hint = (f" — символ «{bad.group(0)}» (U+{ord(bad.group(0)):04X}) вне "
                            f"латиницы; имена только ASCII, иначе неразличимые глазом теги")
                elif ATTR_LOOSE.search(payload) and '"' not in payload:
                    hint = " — значение атрибута не в двойных кавычках"
                elif payload.count('"') % 2:
                    hint = " — непарная кавычка"
                return fail(f"{_pos(text, start)}: не разбирается заголовок элемента "
                            f"«{payload[:60]}»{hint}")
            tag = pm.group(1)
            seen_attrs: set[str] = set()
            for am in ATTR.finditer(pm.group(2)):
                key, val = am.group(1), am.group(2)
                if key in seen_attrs:
                    return fail(f"{_pos(text, start)}: атрибут «{key}» повторяется в "
                                f"элементе «{tag}»")
                seen_attrs.add(key)
                # The one channel a control token can hide in, and the one the earlier
                # version did not look at.
                vm = MARKER_IN_VALUE.search(val)
                if vm:
                    return fail(f"{_pos(text, start)}: маркер {vm.group(0)} внутри значения "
                                f"атрибута «{key}» элемента «{tag}» — разметка в данных")
                # Значения атрибутов смотрелись ТОЛЬКО на маркеры и повтор ключа. Ни
                # печатаемости, ни двунаправленных управляющих: атрибут был каналом
                # доставки текста, мимо всех проверок. Замерено адверсарным проходом —
                # инструкция «игнорируй write-scope» в атрибуте корня проходила чисто.
                if BIDI_CONTROL.search(val):
                    return fail(f"{_pos(text, start)}: управляющие символы двунаправленного "
                                f"письма в значении атрибута «{key}» — видимое расходится "
                                f"с записанным")
                if val and not _has_printable(val):
                    return fail(f"{_pos(text, start)}: значение атрибута «{key}» не содержит "
                                f"ни одного печатаемого символа")
            if stack and tag == r.root:
                return fail(f"{_pos(text, start)}: элемент «{tag}» вложен сам в себя — "
                            f"вторая задача внутри карточки, а не раздел первой")
            if stack:
                pass
            elif closed_root:
                return fail(f"{_pos(text, start)}: второй корневой элемент «{tag}»")
            if tag not in vocab:
                r.vocab_warnings.append(f"{_pos(text, start)}: тег «{tag}» вне словаря профиля")
            # Разделом считается только ПРЯМОЙ ребёнок корня, поэтому имя из
            # обязательного ядра, встреченное глубже, не участвует ни в одной проверке.
            # Набор покрывал случай, когда подделка ЗАМЕНЯЕТ настоящий раздел, — тогда
            # краснеет «нет обязательного». Случай, когда подделка СОСЕДСТВУЕТ с
            # настоящим, не покрывал никто: карточка с одиннадцатью элементами и нулём
            # замечаний везла делегату вторую приёмку «python drop_everything.py».
            # Предупреждение, а не отказ: в карточке про саму разметку такая вложенность
            # бывает законной цитатой, и отказ остановил бы работу.
            if len(stack) > 1 and tag in MANDATORY:
                r.warnings.append(
                    f"{_pos(text, start)}: «{tag}» — имя обязательного раздела — вложено "
                    f"внутрь «{stack[-1][0]}» и разделом НЕ считается; если это поручение, "
                    f"оно не проверено ничем, если цитата — так и должно быть")
            if not stack and r.root is None:
                r.root = tag
                r.attrs = dict(ATTR.findall(pm.group(2)))
            if len(stack) >= max_depth:
                return fail(f"{_pos(text, start)}: вложенность глубже {max_depth} "
                            f"уровней — «{tag}» на уровне {len(stack) + 1}; карточка "
                            f"предназначена для плоских разделов")
            stack.append((tag, start, sep + len(SEP)))
            r.elements += 1
            r.elems.append((tag, len(stack), dict(ATTR.findall(pm.group(2)))))
        else:
            cm = CLOSE_PAYLOAD.match(payload)
            if not cm:
                return fail(f"{_pos(text, start)}: у закрывающего элемента должно быть "
                            f"только имя тега, найдено «{payload[:60]}»")
            tag = cm.group(1)
            if not stack:
                return fail(f"{_pos(text, start)}: {CLOSE}{tag} без открытого элемента")
            top, opened_at, content_at = stack.pop()
            # Only a DIRECT child of the root counts as a delivered section. Nested
            # occurrences are examples, counter-examples or forgeries — treating them as
            # assignments is how a card passed with none of its core actually assigned.
            if len(stack) <= 1:
                body = text[content_at:start].strip()
                if top in r.content:
                    r.dupes.append(top)
                else:
                    r.content[top] = body
            if top != tag:
                return fail(f"{_pos(text, start)}: закрывается «{tag}», а последним открыт "
                            f"«{top}» ({_pos(text, opened_at)}) — вложенность нарушена")
            if not stack:
                closed_root = True
                root_end = sep + len(SEP)

        i = sep + len(SEP)

    if stack:
        tag, opened_at, _ = stack[-1]
        r.errors.append(f"{_pos(text, opened_at)}: элемент «{tag}» открыт и не закрыт")
    for p in literal_hits:
        r.warnings.append(f"{_pos(text, p)}: зарезервированный маркер внутри литеральной области "
                          f"(code span / fenced block) — это текст, не разметка (cXTML/1.0)")
    if closed_root and not r.errors:
        # root_end, not rfind(CLOSE): a close marker quoted in a literal region after the root
        # would otherwise be taken for the root's own close.
        tail = text[root_end:]
        if _meaningful(tail.replace(EOM, "")):
            r.errors.append("после закрытия корневого элемента идёт текст: "
                            f"«{_meaningful(tail)[:50]}» — он не часть карточки и до "
                            "делегата доедет, никем не проверенный")
    # Повтор ОБЯЗАТЕЛЬНОГО раздела двусмыслен: какая из двух копий поручение, не определено,
    # и делегат выберет удобную. Повтор пояснительного раздела законен — две оговорки `note`
    # или два `t` в разных местах ничего не ломают, и отвергать их значит запрещать форму,
    # которой карточки пишутся. Прежняя редакция валила и то, и другое.
    core_dupes = sorted({t for t in r.dupes if t in MANDATORY})
    other_dupes = sorted({t for t in r.dupes if t not in MANDATORY})
    if core_dupes:
        r.errors.append("обязательный раздел повторяется: " + ", ".join(core_dupes)
                        + " — какая из копий поручение, а какая нет, не определено")
    if other_dupes:
        r.warnings.append("раздел встречается дважды: " + ", ".join(other_dupes)
                          + " — для необязательного это допустимо, но проверь, что вторая "
                            "копия не противоречит первой")
    if r.elements == 0:
        r.errors.append("в документе нет ни одного элемента XTML — это не «всё чисто», "
                        "а «нечего было смотреть»: разметка забыта либо файл не тот")
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate an XTML-notation prompt.")
    ap.add_argument("source", help="файл или - для stdin")
    ap.add_argument("--profile", choices=sorted(VOCAB) + ["any"], default="delegation")
    ap.add_argument("--allow-no-routing", action="store_true",
                help="канон до v2: разрешить карточку без раздела routing "
                     "(для перевалидации исторического корпуса; новые карточки "
                     "флагом не пользуются)")
    ap.add_argument("--strict", action="store_true",
                    help="теги вне словаря профиля считать отказом (код 1)")
    args = ap.parse_args(argv)

    if args.source == "-":
        text = sys.stdin.read()
    else:
        try:
            text = Path(args.source).read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"ОШИБКА: файла нет: {args.source}", file=sys.stderr)
            return 2
        except UnicodeDecodeError as e:
            print(f"ОШИБКА: {args.source} не читается как UTF-8 (байт {e.start}) — это про "
                  f"кодировку файла, а не про разметку внутри него", file=sys.stderr)
            return 2

    vocab = set().union(*VOCAB.values()) if args.profile == "any" else VOCAB[args.profile]
    if args.profile == "delegation":
        # Разделы канона v2 — известные теги, хотя и вне VOCAB (причина у их объявления
        # выше: VOCAB сверен с user-owned SKILL.md и потому этой волной не расширялся).
        vocab = vocab | set(V2_SECTIONS)
    # Текст прямо внутри корня — ошибка в КАРТОЧКЕ, где всё содержимое обязано лежать в
    # разделах, и норма в СООБЩЕНИИ K3, где тело сообщения лежит в корне и есть весь
    # смысл формата. Правило было написано без этой оговорки и отвергло законное
    # `[open]message role="user"[sep]Privet[close]message[sep]` — то есть ровно то, ради
    # чего профиль kimi существует. Поймано адверсарным проходом в тот же час.
    rep = scan(text, vocab, eom_allowed=args.profile in EOM_ALLOWED,
               strict_gaps=args.profile in ("delegation", "message", "doc"),
               max_depth=KIMI_NEST_DEPTH if args.profile in ("kimi", "any") else MAX_NEST_DEPTH)

    # Скобки сошлись — это ещё не карточка. Ниже то, без чего постановка не поручает
    # ничего проверяемого. Проверяется только у профиля делегирования: у kimi и any другой
    # смысл документа. Не под --strict: обязательные разделы — не вопрос строгости.
    if args.profile == "delegation" and not rep.errors:
        if rep.root != "task":
            rep.errors.append(f"корневой элемент «{rep.root}» — карточка обязана "
                              f"начинаться с «task»")
        missing = [t for t in MANDATORY if t not in rep.content]
        if missing:
            rep.errors.append("нет обязательных разделов — " + "; ".join(
                f"«{t}»: {MANDATORY[t]}" for t in missing))
        # Пусто — это и раздел без единого ПЕЧАТАЕМОГО символа. Список запрещённых
        # невидимых достроить нельзя (одних назначенных Default_Ignorable — четыре сотни),
        # поэтому вопрос перевёрнут: не «нет ли запрещённого», а «есть ли видимое».
        # Неразрывные пробелы сюда тоже попадают: Zs официально входит в Graphic, и без
        # их вычитания раздел из них читался бы как заполненный.
        empty = [t for t in MANDATORY
                 if t in rep.content and not _has_printable(rep.content[t])]
        if empty:
            rep.errors.append("обязательные разделы пусты: " + ", ".join(f"«{t}»" for t in empty))

        # Двунаправленные управляющие — не пустота, а расхождение видимого с настоящим:
        # текст на экране читается в одном порядке, а файл несёт другой. Двенадцать
        # кодовых точек, свойство Bidi_Control; класс известен как Trojan Source.
        bidi = sorted(t for t, body in rep.content.items() if BIDI_CONTROL.search(body))
        if bidi:
            rep.errors.append(
                "управляющие символы двунаправленного письма в разделах: "
                + ", ".join(f"«{t}»" for t in bidi)
                + " — то, что видно на экране, не совпадает с тем, что записано в файле")

        # Заглушка — не содержимое. Карточка с TODO в миссии не поручает ничего, но по
        # заполненности неотличима от настоящей.
        stubs = [t for t in MANDATORY if _stub_shape(rep.content.get(t, ""))]
        if stubs:
            rep.errors.append("заглушка вместо содержимого в разделах: "
                              + ", ".join(f"«{t}»" for t in stubs))

        # Канон v2 (delegation-canon, card-format/v1): routing обязателен и строг.
        # Отказ (не предупреждение): карточка без routing не маршрутизируется
        # evidence_router'ом и деградирует до непроверяемой постановки.
        routing_err = _routing_complaint(rep.content)
        if routing_err:
            if getattr(args, "allow_no_routing", False):
                rep.warnings.append(routing_err + " — допущено флагом --allow-no-routing")
            else:
                rep.errors.append(routing_err)

        acc = rep.content.get("acceptance", "")
        # Приёмка — единственное поле карточки, про которое ИЗВЕСТНО, что его исполнят,
        # и единственное, чьё содержание не смотрел никто. Замерено адверсарным проходом:
        # карточка с приёмкой, удаляющей каталог инструментов, проходила чисто. Это
        # предупреждение, а не отказ: команда может быть разрушительной законно — уборка
        # временного каталога, откат ветки, — и решает автор, а не проверка.
        if acc and DESTRUCTIVE.search(acc):
            rep.warnings.append(
                "приёмка содержит разрушительную команду — а приёмка исполняется; "
                "убедись, что делегат должен это сделать, а не просто проверить")
        if acc and not _is_command(acc):
            rep.errors.append(f"приёмка не является командой — «{acc[:70]}»; прилагательное "
                              f"проверить нельзя, отчёт по нему неопровержим")

        # Команда есть — но смотрит ли она на содержание? Замер автогрейдера 2026-08-01
        # по девяти карточкам одной сессии: во всех приёмка была `Test-Path <отчёт>`,
        # то есть проверяла существование файла. Делегат, положивший файл с одной
        # строкой, проходит её. Проверка тут остаётся ПРЕДУПРЕЖДЕНИЕМ, а не отказом:
        # правило выведено из одного класса примеров, а в энфорс правило идёт только
        # с примером, который оно ОБЯЗАНО пропустить, — иначе живой сторож начинает
        # отвергать законные карточки (проверено на этом же валидаторе неделей раньше).
        if acc and _is_command(acc):
            # Простое вхождение подстроки, а не регулярное выражение: модуль re в этой
            # области не импортирован, и обращение к нему роняло бы валидатор ровно в
            # момент срабатывания ветки — то есть детектор падал бы на том входе, ради
            # которого написан. Поймано статическим анализом до первого прогона.
            existence_only = any(t in acc for t in ("Test-Path", "exists()", "os.path.exists"))
            content_probe = any(t in acc for t in (
                ".Length", "Get-Content", "Select-String", "-match", "-SimpleMatch",
                "findstr", "read_text", "getsize", "wc -c", "grep"))
            if existence_only and not content_probe:
                rep.warnings.append(
                    "приёмка проверяет СУЩЕСТВОВАНИЕ отчёта, а не его содержание — "
                    "файл с одной строкой её пройдёт; добавь порог объёма и обязательную "
                    "подстроку из миссии (имя события, номер инварианта, версию)")

        rp = _meaningful(rep.content.get("report-path", ""))
        bad_path = _path_complaint(rp) if rp else None
        if bad_path:
            rep.errors.append(f"путь отчёта «{rp[:60]}»: {bad_path}")
        elif rp:
            # Путь внутри дома — ещё не путь внутри ОБЪЯВЛЕННОЙ области записи. Эти два
            # поля не сверялись между собой вовсе, хотя декларация мутаций называла свой
            # случай «report-path вне объявленного write-scope»: на деле проверялось лишь
            # «внутри домашнего каталога». Отсюда проходили отчёт поверх самого валидатора,
            # поверх глобальных инструкций и поверх сторожа, который карточку и пропустил.
            # Совпадение ищется грубо — по упоминанию любого пути из write-scope, — потому
            # что область записи пишется прозой, и строгий разбор её формы отверг бы
            # законные карточки.
            scope = _meaningful(rep.content.get("write-scope", ""))
            paths = SCOPE_PATH.findall(scope)
            if paths:
                # Область записи — проза, и путь в ней стоит в конце предложения, то есть
                # с точкой. Без снятия конечной пунктуации правило дало ложную тревогу на
                # первой же карточке, где путь отчёта был назван дословно.
                def _norm(s: str) -> str:
                    return s.replace("\\", "/").rstrip("./ ").lower()
                norm = _norm(rp)
                if not any(_norm(p) in norm for p in paths):
                    # Решение владельца по опроснику, пункт 7в: отказ ТОЛЬКО при явном
                    # конфликте, предупреждение в остальных случаях. Обе оси консенсуса
                    # были правы каждая о своём: ось пропуска — что делегат пишет туда,
                    # куда ему не разрешали; ось ложного отказа — что область записи
                    # пишется прозой, и строгое правило отвергнет законные карточки.
                    # Явный конфликт — это когда область записи названа ОДНИМ путём
                    # (границы описаны полно, толковать нечего), а отчёт лежит не в нём.
                    # Несколько путей в области записи означают, что она описана
                    # перечислением, и отсутствие среди них пути отчёта может быть
                    # неполнотой описания, а не нарушением границ.
                    # Явность определяется тем, что кроме пути в разделе НИЧЕГО НЕТ.
                    # Первая редакция считала явным «один путь в одной короткой строке» —
                    # и объявила отказом эталонную карточку набора, где написано
                    # «Только tools/xtml/.»: слово «Только» делает это прозой, которую
                    # надо толковать. Тот же класс «правило из одного примера», против
                    # которого написан отдельный урок. Критерий: убрать пути и пунктуацию;
                    # если остались слова — это проза, и вердикт смягчается.
                    residue = SCOPE_PATH.sub(" ", _meaningful(scope))
                    residue = regex.sub(r"[\p{P}\p{S}\s]+", "", residue)
                    explicit = len(paths) == 1 and not residue
                    msg = (f"путь отчёта «{rp[:50]}» вне объявленной области записи "
                           f"({', '.join(paths[:3])})")
                    if explicit:
                        rep.errors.append(
                            msg + " — область записи названа одним путём, толковать нечего: "
                                  "делегат напишет туда, куда ему не разрешали")
                    else:
                        rep.warnings.append(
                            msg + " — либо отчёт ляжет вне границ, либо границы описаны "
                                  "не полностью; область записи задана прозой, поэтому "
                                  "это замечание, а не отказ")

        # Канон v2 §4: присутствующие опциональные разделы проверяются по словарям
        # значений. Отсутствие законно (обратная совместимость), искажение — отказ.
        rep.errors.extend(_v2_complaints(rep.content))

    # W65: горизонтальная карта (profile message) — свои атрибуты и разделы, ¬ ядро постановки.
    if args.profile == "message" and not rep.errors:
        rep.errors.extend(_message_complaints(rep))

    # W73: документ — корень из roots, словарь закрыт (вне словаря — отказ, а не предупреждение под --strict).
    if args.profile == "doc" and not rep.errors:
        if rep.root not in DOC["roots"]:
            rep.errors.append(f"корневой элемент «{rep.root}» — документ начинается с одного из: "
                              + " | ".join(DOC["roots"]))
        rep.errors.extend(f"{w} — словарь документа закрыт (card-format.json doc): "
                          f"неизвестный элемент не прочитает ни один потребитель" for w in rep.vocab_warnings)
        rep.vocab_warnings = []

    for w in rep.vocab_warnings + rep.warnings:
        print(f"предупреждение: {w}")
    if rep.errors:
        for e in rep.errors:
            print(f"ОШИБКА: {e}", file=sys.stderr)
        return 2
    total_warn = len(rep.vocab_warnings) + len(rep.warnings)
    print(f"XTML OK: элементов {rep.elements}, предупреждений {total_warn}, "
          f"профиль {args.profile}")

    # --profile any глушит словарный контроль целиком, поэтому его «чисто» не равно
    # «чисто» под настоящим профилем. Возврат нуля сделал бы обход неотличимым от
    # прохода: гейт на коде возврата зеленел бы на карточке с любыми тегами. Единица
    # — совещательная, она не блокирует, но обход в коде виден.
    if args.profile == "any":
        print("предупреждение: --profile any отключает словарный контроль целиком; "
              "код возврата 1 означает «разобрано, но не проверено по словарю»")
        return 1

    # kimi — тот же класс обхода: он снимает и обязательное ядро, и запрет стоп-маркера,
    # то есть проверяет ЧУЖОЙ формат, а не нашу постановку. Опечатка во флаге не должна
    # зеленить гейт, поставленный ради карточек делегатам.
    if args.profile == "kimi":
        print("предупреждение: --profile kimi проверяет формат Kimi, а не карточку "
              "постановки: обязательное ядро и запрет стоп-маркера не применяются; "
              "код возврата 1 означает «разобрано по чужому профилю»")
        return 1
    # Только словарные: флаг документирован как «теги вне словаря профиля считать
    # отказом», и расширять его на прочие предупреждения значит отменять смягчения,
    # введённые ради законных карточек.
    return 1 if (rep.vocab_warnings and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
