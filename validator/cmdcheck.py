#!/usr/bin/env python3
"""Is this line of text a command, or is it prose pretending to be one?

Imported by both places that ask the question:
  - tools/xtml/validate.py       — acceptance section of an XTML delegation card
  - tools/task-registry/render_note.py — acceptance field of a task registry

WHY ONE MODULE AND NOT TWO COPIES

    The question was answered twice, differently, and the two answers drifted without a
    word. The registry side judged by SUBSTRING — "does the text contain 'python'
    anywhere" — which accepts a sentence that merely mentions a tool and rejects nothing.
    The card side judged by prefix, which accepted "github" under "git" and carried a hint
    "uv " with a space inside that could never match, because tokens come from splitting
    on whitespace.

    Both were fixed separately on the same day, in different directions, by different
    sessions. That is the failure mode: two copies of one rule, each locally sensible,
    together meaning that a card accepted by one tool is rejected by the other, and the
    disagreement reads as a random glitch. A shared module makes the divergence
    impossible rather than merely unlikely.

WHAT COUNTS AS A COMMAND

    The first token of ANY line, judged by equality against a list of executable names or
    by looking like a path. Never by substring. A bare executable name counts only when
    something follows it — otherwise every English sentence opening with "make" or "go"
    would read as a command.

    Deliberately NOT checked: whether the command exists, whether its flags are real,
    whether it would succeed. Measured this session: a card passed with the acceptance
    `mutate.py --declaration xtml-validator`, and the engine has no `--declaration` flag —
    it takes `--only`. The unknown flag was ignored and every declaration ran. Judging
    flags means executing or parsing each tool, which is a different tool from this one;
    what this module guarantees is that a criterion is EXECUTABLE, not that it is correct.
"""

from __future__ import annotations

import re

# Имена исполняемых. Сверяются ТОЧНЫМ равенством первого токена строки.
# ⛔ Список пополняется, а не заменяется: каждое имя здесь стоит потому, что приёмка в
# такой форме реально писалась. `bash` добавлен параллельной сессией 31.07 после того,
# как реестр с приёмкой-шелл-скриптом был помечен прозой; здесь он сохранён без пробела
# на конце, потому что равенство токену пробела не содержит.
EXEC_NAMES = frozenset("""
python python3 py pytest tox uv uvx pip poetry ruff mypy black isort flake8 pylint
pwsh powershell cmd bash sh zsh fish ksh dash
node npm npx pnpm yarn bun deno tsc vitest jest eslint prettier
git gh hg svn
cargo rustc rustup go dotnet java javac mvn gradle
make cmake ctest ninja meson bazel
docker podman kubectl helm terraform ansible
rg grep egrep fgrep sed awk jq yq fd find xargs curl wget
gcc clang cl msbuild dart flutter swift kotlinc
robocopy scp rsync ssh
ruby gem bundle rake perl php composer artisan lua Rscript julia
ls cat head tail wc sort uniq diff cut tr tee stat du df tar zip unzip 7z
restic rclone borg duplicati systemctl journalctl schtasks netsh ip ping traceroute
psql mysql sqlite3 mongosh redis-cli
""".split())

# Обёртки, которые сами являются исполняемыми и запускают следующую команду. Без них
# приёмка «env PYTHONPATH=. pytest tests» и «timeout 60 pytest» читались как проза:
# первый токен есть в списке, но смысловая команда стоит дальше. Замер разведки: из
# тридцати реалистичных форм приёмки прежнее правило отвергало пятнадцать, и обёртки
# были в числе самых частых промахов.
WRAPPERS = frozenset("env sudo time timeout nice ionice nohup stdbuf xargs doas".split())

# Версионный суффикс. Инструменты этого класса срезают имя по точкам справа налево:
# python3.12.1 -> python3.12 -> python3 -> python. Точное равенство без этого промахивается
# по совершенно обычной форме вызова.
VERSION_TAIL = re.compile(r"\.\d[\d.]*$|(?<=[a-z])\d+(?:\.\d+)*$")


def _known_exec(head: str) -> bool:
    """Executable name, with version suffixes peeled off right to left."""
    name = head
    for _ in range(4):
        if name in EXEC_NAMES:
            return True
        stripped = VERSION_TAIL.sub("", name)
        if stripped == name:
            return False
        name = stripped
    return name in EXEC_NAMES

# Глаголы PowerShell идут семейством: Get-*, Test-*, Set-* и так далее. Судить по дефису
# после известного глагола дешевле, чем перечислять командлеты.
PS_VERB = re.compile(r"^(?:Get|Set|New|Test|Remove|Start|Stop|Invoke|Select|Measure|"
                     r"Import|Export|ConvertTo|ConvertFrom|Write|Read|Out|Compare)-[A-Za-z]")
# Первый токен как ПУТЬ: относительный запуск, переменная оболочки, слэш внутри либо
# расширение исполняемого файла. Этого достаточно и без второго токена.
SCRIPT_LIKE = re.compile(
    r"^(?:\./|\.\\|\$|~/|/)|[/\\]|\.(?:py|sh|ps1|bat|cmd|exe|js|mjs|ts)$")


def line_is_command(line: str) -> bool:
    """One line: does it start with something executable?

    Wrappers are peeled first: `env VAR=x pytest tests` and `timeout 60 pytest` are
    commands whose meaningful head sits further along. Peeling is bounded — a line that is
    nothing but wrapper names is not a command, it is a list of words.

    ⛔ Требование «у имени должно быть продолжение» существует против прозы:
    одинокое слово `make` или `find` в предложении командой не является. Но
    после СНЯТОЙ обёртки эта улика уже получена — «timeout 60 pytest» прозой не
    бывает, — и требовать сверх того ещё один аргумент значило бы отвергать
    форму, которую сама эта строка документации называет командой. Расхождение
    кода с собственной документацией снято в пользу документации: продолжение
    обязательно только тогда, когда обёртки не было.
    """
    parts = [p for p in line.strip().split() if p]
    depth = 0
    while parts and depth < 3:
        head = parts[0].strip("`\"'")
        # Чистый ASCII обязателен: команда, чья первая буква — кириллический двойник,
        # выглядит исполнимой и не исполняется.
        if not head or any(ord(ch) > 127 for ch in head):
            return False
        if SCRIPT_LIKE.search(head) or PS_VERB.match(head):
            return True
        if head in WRAPPERS and len(parts) > 1:
            # Присваивание переменной окружения между обёрткой и командой — часть той же
            # формы: env PYTHONPATH=. pytest.
            # Между обёрткой и командой стоят её собственные аргументы: присваивание
            # окружения у env, длительность у timeout, флаг у nice. Снимаются только
            # формы, которые исполняемым именем быть не могут — присваивание, число,
            # флаг. Снимать всё подряд означало бы объявить командой любую строку,
            # начинающуюся словом «time».
            rest = parts[1:]
            while rest and re.match(r"^(?:[A-Za-z_][A-Za-z0-9_]*=|-|\d+[smhd]?$)", rest[0]):
                rest = rest[1:]
            parts = rest
            depth += 1
            continue
        return _known_exec(head) and (len(parts) > 1 or depth > 0)
    return False


# Разделители, за которыми в той же строке начинается ещё одна команда. Приёмка
# «set PYTHONIOENCODING=utf-8 && python -c ...» — не выдумка, а форма, ПРЕДПИСАННАЯ
# постоянно загруженными правилами этого контура для вывода кириллицы; прежнее правило
# смотрело только на голову строки и отвергало её. Замер второго адверсарного прохода:
# восемь классов ложного отказа, и этот — первый по цене.
CHAIN = re.compile(r"&&|\|\||;|\|")
# Присваивание переменной окружения впереди команды: и «VAR=x cmd», и «set VAR=x && cmd».
ASSIGN = re.compile(r"^(?:set\s+)?[A-Za-z_][A-Za-z0-9_]*=")


def acceptance_text(value: object) -> str:
    """Приёмка одной задачи, приведённая к тексту, какой бы формой она ни пришла.

    ⛔ Форм две, и обе законны. `tools/task-registry/from_native.py` отдаёт приёмку
    строкой, потому что в metadata родной задачи она строкой и лежит.
    `tools/registry-note/generate.py` писался под рукописный реестр, где приёмка —
    отображение с ключом `command` и пояснением рядом. Замерено 2026-08-05: второй
    генератор падал на первом же собранном реестре с AttributeError в строке 72, потому
    что звал `.get("command")` у строки. Связка «реестр порождает записку» держалась на
    одном из двух путей, второй был мёртв, и узналось это только запуском.

    Приводить форму к форме в каждом инструменте порознь — ровно тот режим отказа, из-за
    которого этот модуль появился: две копии одного правила расходятся молча. Поэтому
    нормализация живёт здесь, рядом с самим вопросом «а это команда?».

    Отображение без ключа `command` даёт пустую строку НАМЕРЕННО: приёмка, у которой
    команды нет, обязана остаться непройденной проверкой, а не подменить критерий
    текстом пояснения, который читается солидно и не исполняется.
    """
    if isinstance(value, dict):
        return str(value.get("command") or "")
    if value is None:
        return ""
    return str(value)


def is_command(text: str) -> bool:
    """ANY segment of ANY line qualifies.

    Three widenings, each from a measured false alarm:
      - any LINE, not only the first — acceptance is written with a Russian lead-in;
      - any SEGMENT of a chained line — `set VAR=x && python …` is the documented shape;
      - a leading environment assignment is peeled, since it is prologue, not command.
    """
    for line in str(text).splitlines():
        for seg in CHAIN.split(line):
            seg = seg.strip()
            while ASSIGN.match(seg):
                seg = seg.split("=", 1)[1]
                seg = seg.split(None, 1)[1] if " " in seg else ""
            if seg and line_is_command(seg):
                return True
    return False
