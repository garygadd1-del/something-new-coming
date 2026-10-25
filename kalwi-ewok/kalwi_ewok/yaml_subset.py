"""A small YAML subset for role files and the compose sketch.

The subset accepts maps, lists, scalars, and comments. It rejects tags,
anchors, merge keys, and multiline blocks so a role file cannot smuggle
an object constructor or a huge alias expansion.
"""

from __future__ import annotations

from kalwi_ewok.errors import ParseError

_MAX_CHARS = 32_000
_MAX_INDENT = 12
_KEY_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")


def parse_simple_yaml(text: str):
    """Parse the restricted YAML subset. The root value is a mapping."""
    if len(text) > _MAX_CHARS:
        raise ParseError("document is too large")
    if text.startswith("\ufeff"):
        text = text[1:]
    items = _tokenize(text)
    if not items:
        raise ParseError("document is empty")
    if items[0][1] != 0:
        raise ParseError(f"line {items[0][0]}: root indent must be 0")
    value, index = _parse_block(items, 0, 0)
    if index != len(items):
        raise ParseError(f"line {items[index][0]}: trailing content")
    if not isinstance(value, dict):
        raise ParseError("root must be a mapping")
    return value


def _tokenize(text: str) -> list[tuple[int, int, str]]:
    items: list[tuple[int, int, str]] = []
    for line_no, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw:
            raise ParseError(f"line {line_no}: tabs are not allowed")
        if raw.strip() == "" or raw.lstrip(" ").startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent > _MAX_INDENT:
            raise ParseError(f"line {line_no}: nesting is too deep")
        content = _strip_inline_comment(raw.strip())
        if content == "":
            continue
        items.append((line_no, indent, content))
    return items


def _strip_inline_comment(text: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(text):
        if in_double and char == "\\" and not escaped:
            escaped = True
            continue
        if char == "'" and not in_double and not escaped:
            in_single = not in_single
        elif char == '"' and not in_single and not escaped:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or text[index - 1].isspace():
                return text[:index].rstrip()
        escaped = False
    return text.rstrip()


def _parse_block(items, index: int, indent: int):
    if items[index][2].startswith("- "):
        return _parse_list(items, index, indent)
    return _parse_map(items, index, indent)


def _parse_map(items, index: int, indent: int):
    result: dict = {}
    while index < len(items):
        line_no, item_indent, content = items[index]
        if item_indent < indent:
            break
        if item_indent != indent:
            raise ParseError(f"line {line_no}: unexpected indent")
        if content.startswith("- "):
            raise ParseError(f"line {line_no}: expected a key")
        key, sep, rest = content.partition(":")
        if sep == "" or key.strip() == "":
            raise ParseError(f"line {line_no}: expected key: value")
        key = key.strip()
        _check_key(key, line_no)
        if key in result:
            raise ParseError(f"line {line_no}: duplicate key {key}")
        rest = rest.strip()
        if rest == "":
            index += 1
            if index >= len(items) or items[index][1] <= indent:
                raise ParseError(f"line {line_no}: expected a nested block")
            child_indent = items[index][1]
            nested, index = _parse_block(items, index, child_indent)
            result[key] = nested
            continue
        result[key] = _parse_scalar(rest, line_no)
        index += 1
    return result, index


def _parse_list(items, index: int, indent: int):
    result = []
    while index < len(items):
        line_no, item_indent, content = items[index]
        if item_indent < indent:
            break
        if item_indent != indent or not content.startswith("- "):
            raise ParseError(f"line {line_no}: expected a list item")
        item_text = content[2:].strip()
        if item_text == "":
            raise ParseError(f"line {line_no}: nested list blocks are not accepted")
        result.append(_parse_scalar(item_text, line_no))
        index += 1
    return result, index


def _check_key(key: str, line_no: int) -> None:
    if not key or key[0] not in _KEY_CHARS or not key[0].isalpha() and key[0] != "_":
        raise ParseError(f"line {line_no}: illegal key {key!r}")
    if any(char not in _KEY_CHARS for char in key):
        raise ParseError(f"line {line_no}: illegal key {key!r}")


def _parse_scalar(raw: str, line_no: int):
    if raw == "[]":
        return []
    if raw == "{}":
        return {}
    if raw.startswith('"'):
        if len(raw) < 2 or not raw.endswith('"'):
            raise ParseError(f"line {line_no}: unterminated double quote")
        return _unescape_double(raw[1:-1], line_no)
    if raw.startswith("'"):
        if len(raw) < 2 or not raw.endswith("'"):
            raise ParseError(f"line {line_no}: unterminated single quote")
        inner = raw[1:-1]
        if "'" in inner.replace("''", ""):
            raise ParseError(f"line {line_no}: broken single-quoted string")
        return inner.replace("''", "'")
    if raw in ("true", "false"):
        return raw == "true"
    if _is_int(raw):
        return int(raw)
    if _is_float(raw):
        return float(raw)
    if any(char in raw for char in "{}[]&*!|>"):
        raise ParseError(f"line {line_no}: unsupported syntax")
    if ": " in raw:
        raise ParseError(f"line {line_no}: quote values that contain ': '")
    return raw


def _unescape_double(inner: str, line_no: int) -> str:
    out: list[str] = []
    escaped = False
    for char in inner:
        if escaped:
            if char in ('"', "\\"):
                out.append(char)
            else:
                raise ParseError(f"line {line_no}: unsupported escape")
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        out.append(char)
    if escaped:
        raise ParseError(f"line {line_no}: dangling escape")
    return "".join(out)


def _is_int(raw: str) -> bool:
    if raw.startswith("-"):
        raw = raw[1:]
    return raw.isdigit() and raw != ""


def _is_float(raw: str) -> bool:
    if raw.startswith("-"):
        raw = raw[1:]
    left, sep, right = raw.partition(".")
    return sep == "." and left.isdigit() and right.isdigit() and left != "" and right != ""
