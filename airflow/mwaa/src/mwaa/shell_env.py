# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Statically works out the environment a startup script exports, as far as that's possible.

MWAA runs the startup script with `sh` before starting Airflow, and whatever it
exports is the environment the OpenLineage provider later reads. This walks the
script top to bottom the way the shell would for the parts that decide that --
`export NAME=value`, `NAME=value` then `export NAME`, `set -a`, `unset` -- and
resolves each value's expansions against what the script assigned earlier:

  ${VAR:-default} / ${VAR-default}  default when VAR isn't set earlier (VAR's value otherwise)
  ${VAR:+alt} / ${VAR+alt}          the usual alternate-value forms
  ${VAR} / $VAR                     VAR's earlier value
  'single quotes'                   literal

A value that can't be known statically -- command substitution, a variable
the script never assigned (it may come from MWAA itself, like
AIRFLOW_ENV_NAME), an assignment inside an `if`/loop or after `&&`/`||` -- is
None: the variable is *set*, to something this can't see. Function bodies,
heredoc bodies, subshells and command-prefix assignments (`VAR=x cmd`)
don't change the script's own environment, so they're skipped.

This is deliberately not a shell: anything it doesn't model is either
skipped (commands) or comes out as None, never as a confident wrong value.
"""

import re
from typing import Optional

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ASSIGNMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", re.DOTALL)
_FUNCTION = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\(\)")
_BLOCK_OPENERS = {"if", "case", "for", "while", "until"}
_BLOCK_CLOSERS = {"fi", "esac", "done"}
_BLOCK_CONTINUATIONS = {"then", "else", "do"}

#: Variables -> value (None: set, but not statically knowable).
Variables = dict[str, Optional[str]]


class _Unknown(Exception):
    pass


def _matching(text: str, start: int, opener: str, closer: str) -> int:
    """Index of the `closer` matching the `opener` at text[start], skipping quoted spans."""
    depth, i, quote = 0, start, None
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "\\":
            i += 1
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(text) - 1


def _lookup(name: str, variables: Variables) -> str:
    if name not in variables or variables[name] is None:
        raise _Unknown
    return variables[name]


def _parameter(body: str, variables: Variables) -> str:
    """One ${...} expansion."""
    name = _NAME.match(body)
    if not name:
        raise _Unknown
    operator_and_word = body[name.end() :]
    name = name.group(0)
    if not operator_and_word:
        return _lookup(name, variables)
    for operator in (":-", ":=", ":+", "-", "=", "+"):
        if operator_and_word.startswith(operator):
            word = operator_and_word[len(operator) :]
            break
    else:
        raise _Unknown  # ${#VAR}, ${VAR%pattern}, ...
    is_set = name in variables
    value = variables.get(name)
    if operator in (":-", ":="):
        if is_set and value is None:
            raise _Unknown
        return value if value else _expand(word, variables)
    if operator in ("-", "="):
        return _lookup(name, variables) if is_set else _expand(word, variables)
    if operator == ":+":
        if is_set and value is None:
            raise _Unknown
        return _expand(word, variables) if value else ""
    return _expand(word, variables) if is_set else ""  # "+"


def _expand(raw: str, variables: Variables) -> str:
    out = []
    i, in_double = 0, False
    while i < len(raw):
        c = raw[i]
        if c == "'" and not in_double:
            end = raw.find("'", i + 1)
            end = len(raw) if end == -1 else end
            out.append(raw[i + 1 : end])
            i = end + 1
        elif c == '"':
            in_double = not in_double
            i += 1
        elif c == "\\" and i + 1 < len(raw):
            out.append(raw[i + 1])
            i += 2
        elif c == "`":
            raise _Unknown
        elif c == "$" and raw[i + 1 : i + 2] == "(":
            raise _Unknown
        elif c == "$" and raw[i + 1 : i + 2] == "{":
            end = _matching(raw, i + 1, "{", "}")
            out.append(_parameter(raw[i + 2 : end], variables))
            i = end + 1
        elif c == "$" and _NAME.match(raw, i + 1):
            name = _NAME.match(raw, i + 1)
            out.append(_lookup(name.group(0), variables))
            i = name.end()
        elif c == "$" and i + 1 < len(raw) and raw[i + 1] in "0123456789@*#?$!-":
            raise _Unknown
        else:
            out.append(c)
            i += 1
    return "".join(out)


def expand(raw: str, variables: Variables) -> Optional[str]:
    """A raw shell word's value, or None if it can't be known statically."""
    try:
        return _expand(raw, variables)
    except _Unknown:
        return None


def _statements(line: str) -> list[tuple[str, list[str]]]:
    """Split one logical line into (preceding operator, words) statements, quotes and $(...) kept intact."""
    statements: list[tuple[str, list[str]]] = []
    words: list[str] = []
    word = ""
    operator = ""
    i = 0

    def end_word() -> None:
        nonlocal word
        if word:
            words.append(word)
            word = ""

    def end_statement(next_operator: str) -> None:
        nonlocal words, operator
        end_word()
        if words:
            statements.append((operator, words))
        words, operator = [], next_operator

    while i < len(line):
        c = line[i]
        if c in "'\"":
            end = _matching(line, i, c, c) if c == "'" else _closing_double_quote(line, i)
            word += line[i : end + 1]
            i = end + 1
        elif c == "\\":
            word += line[i : i + 2]
            i += 2
        elif c == "$" and line[i + 1 : i + 2] in ("(", "{"):
            end = _matching(line, i + 1, line[i + 1], ")" if line[i + 1] == "(" else "}")
            word += line[i : end + 1]
            i = end + 1
        elif c == "`":
            end = line.find("`", i + 1)
            end = len(line) - 1 if end == -1 else end
            word += line[i : end + 1]
            i = end + 1
        elif c == "#" and not word:
            break
        elif c.isspace():
            end_word()
            i += 1
        elif line.startswith(("&&", "||"), i):
            end_statement(line[i : i + 2])
            i += 2
        elif c == ";" or c == "|" or (c == "&" and not word.endswith((">", "<")) and line[i + 1 : i + 2] != ">"):
            end_statement(c)
            i += 1
        else:
            word += c
            i += 1
    end_statement("")
    return statements


def _closing_double_quote(text: str, start: int) -> int:
    i = start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == '"':
            return i
        if text[i] == "$" and text[i + 1 : i + 2] in ("(", "{"):
            i = _matching(text, i + 1, text[i + 1], ")" if text[i + 1] == "(" else "}") + 1
            continue
        i += 1
    return len(text) - 1


def _heredoc(statements: list[tuple[str, list[str]]]) -> "tuple[str, bool] | None":
    """(delimiter, strips leading tabs) of a heredoc a line opens, from its unquoted `<<WORD` token."""
    for _, words in statements:
        for i, word in enumerate(words):
            if not word.startswith("<<") or word.startswith("<<<"):
                continue
            delimiter = word[2:] or (words[i + 1] if i + 1 < len(words) else "")
            strip_tabs = delimiter.startswith("-")
            delimiter = delimiter.removeprefix("-").strip("'\"")
            if delimiter:
                return delimiter, strip_tabs
    return None


def _logical_lines(text: str) -> list[str]:
    lines, current = [], ""
    for physical in text.splitlines():
        if physical.endswith("\\") and not physical.endswith("\\\\"):
            current += physical[:-1] + " "
            continue
        lines.append(current + physical)
        current = ""
    if current:
        lines.append(current)
    return lines


def exported_environment(script: str) -> Variables:
    """The variables `script` leaves exported, each resolved as far as statically possible."""
    variables: Variables = {}
    exported: set[str] = set()
    allexport = False
    block_depth = 0
    function_depth: Optional[int] = None
    heredoc: Optional[tuple[str, bool]] = None

    for line in _logical_lines(script):
        if heredoc:
            delimiter, strip_tabs = heredoc
            if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                heredoc = None
            continue
        statements = _statements(line)
        heredoc = _heredoc(statements)

        for operator, words in statements:
            if function_depth is not None:
                function_depth += words.count("{") - words.count("}")
                if function_depth <= 0 and "}" in words:
                    function_depth = None
                continue
            if _FUNCTION.fullmatch(words[0]) or (len(words) > 1 and words[1] == "()") or words[0] == "function":
                function_depth = words.count("{") - words.count("}")
                if function_depth <= 0 and "}" in words:
                    function_depth = None
                continue

            first = words[0]
            if first in _BLOCK_OPENERS:
                block_depth += 1
                continue
            if first in _BLOCK_CLOSERS:
                block_depth = max(block_depth - 1, 0)
                continue
            if first == "elif":
                continue
            if first in _BLOCK_CONTINUATIONS or first in ("{", "}"):
                words = words[1:]
                if not words:
                    continue
                first = words[0]
            if first.startswith("("):
                continue  # subshell
            conditional = block_depth > 0 or operator in ("&&", "||") or operator == "|"

            if first == "set" and len(words) > 1:
                if "-a" in words[1:] or "allexport" in words[1:]:
                    allexport = True
                if "+a" in words[1:]:
                    allexport = False
                continue
            if first == "unset":
                for name in words[1:]:
                    variables.pop(name, None)
                    exported.discard(name)
                continue

            if first == "export":
                targets = [w for w in words[1:] if not w.startswith("-")]
            elif all(_ASSIGNMENT.fullmatch(w) for w in words):
                targets = words
            else:
                continue  # a command, possibly with VAR=x prefix assignments for itself only

            for target in targets:
                assignment = _ASSIGNMENT.fullmatch(target)
                if assignment:
                    name = assignment.group(1)
                    variables[name] = None if conditional else expand(assignment.group(2), variables)
                else:
                    name = target
                if first == "export" or allexport:
                    exported.add(name)

    return {name: variables[name] for name in exported if name in variables}
