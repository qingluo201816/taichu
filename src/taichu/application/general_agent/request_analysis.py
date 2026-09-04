"""从当前请求中提取可确定的章节引用，不承担小说事实检索。"""

from __future__ import annotations

import re


_CHAPTER_NUMBER = r"[0-9零〇一二三四五六七八九十百千万两]+"
_CHAPTER_RANGE_PATTERN = re.compile(
    rf"第(?P<start>{_CHAPTER_NUMBER})(?:章)?"
    rf"(?:到|至|—|–|-|~|～)(?:第)?(?P<end>{_CHAPTER_NUMBER})章"
)
_CHAPTER_PATTERN = re.compile(rf"第(?P<number>{_CHAPTER_NUMBER})章")
_RECENT_CHAPTER_PATTERN = re.compile(
    rf"最近(?P<count>{_CHAPTER_NUMBER})章"
)
_CONTENT_REQUEST_MARKERS = (
    "讲的什么",
    "讲了什么",
    "写的什么",
    "写了什么",
    "主要内容",
    "内容是什么",
    "发生了什么",
    "概括",
    "总结",
    "摘要",
    "原文",
)
_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CHINESE_UNITS = {"十": 10, "百": 100, "千": 1_000, "万": 10_000}


def explicit_chapter_orders(text: str) -> list[int]:
    """按出现顺序返回明确章节序号，连续范围最多展开一百章。"""

    orders: list[int] = []
    range_spans: list[tuple[int, int]] = []
    for match in _CHAPTER_RANGE_PATTERN.finditer(text):
        start = _chapter_number(match.group("start"))
        end = _chapter_number(match.group("end"))
        range_spans.append(match.span())
        if start <= 0 or end < start or end - start >= 100:
            continue
        orders.extend(range(start, end + 1))
    for match in _CHAPTER_PATTERN.finditer(text):
        if any(start <= match.start() and match.end() <= end for start, end in range_spans):
            continue
        number = _chapter_number(match.group("number"))
        if number > 0:
            orders.append(number)
    return list(dict.fromkeys(orders))


def is_explicit_chapter_content_request(text: str) -> bool:
    """判断请求是否要求读取明确章节的内容，而不是未知位置搜索。"""

    normalized = text.strip()
    return bool(explicit_chapter_orders(normalized)) and any(
        marker in normalized for marker in _CONTENT_REQUEST_MARKERS
    )


def recent_chapter_count(text: str) -> int | None:
    """提取“最近 N 章”的确定性范围，避免模型猜测结构输出路径。"""

    match = _RECENT_CHAPTER_PATTERN.search(text.strip())
    if match is None:
        return None
    count = _chapter_number(match.group("count"))
    return count if 1 <= count <= 100 else None


def _chapter_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    if all(character in _CHINESE_DIGITS for character in value):
        return int("".join(str(_CHINESE_DIGITS[character]) for character in value))
    total = 0
    section = 0
    current = 0
    for character in value:
        if character in _CHINESE_DIGITS:
            current = _CHINESE_DIGITS[character]
            continue
        unit = _CHINESE_UNITS.get(character)
        if unit is None:
            return 0
        if unit == 10_000:
            section += current
            total += max(1, section) * unit
            section = 0
            current = 0
            continue
        section += max(1, current) * unit
        current = 0
    return total + section + current
