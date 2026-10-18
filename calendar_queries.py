"""Deterministic, timezone-aware read-only calendar query periods."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import re

@dataclass(frozen=True)
class CalendarPeriod:
    start: datetime
    end: datetime
    label: str


def chinese_number(text):
    if text.isdigit():
        return int(text)
    digits = dict(zip('零一二三四五六七八九', range(10)))
    text = text.replace('兩', '二')
    if '十' in text:
        left, right = text.split('十', 1)
        return (digits[left] if left else 1) * 10 + (digits[right] if right else 0)
    return digits[text]


def calendar_period(raw, now):
    """Reject ambiguous/unsupported periods instead of silently changing the range."""
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    choices = []
    def add(start, days, label):
        choices.append(CalendarPeriod(start, start + timedelta(days=days), label))
    explicit = re.compile(r'(?<!\d)(?:(\d{4})\s*(?:年|[-/])\s*)?([一二三四五六七八九十\d]{1,3})\s*(?:月|[-/])\s*([一二三四五六七八九十\d]{1,3})\s*(?:日|號)?(?!\d)')
    matches = list(explicit.finditer(raw))
    for match in matches:
        year, month, day = match.groups()
        try:
            start = today.replace(year=int(year) if year else today.year, month=chinese_number(month), day=chinese_number(day))
        except (ValueError, KeyError):
            raise ValueError('日期不存在，請確認年月日。') from None
        add(start, 1, start.strftime('%Y-%m-%d'))
    remainder = explicit.sub('', raw)
    patterns = [(r'大後天', 3, '大後天'), (r'後天', 2, '後天'), (r'明天|\btomorrow\b', 1, '明天'),
                (r'今天|今日|\btoday\b', 0, '今天'), (r'昨天|\byesterday\b', -1, '昨天')]
    for pattern, offset, label in patterns:
        if re.search(pattern, remainder, re.I):
            add(today + timedelta(days=offset), 1, label)
            remainder = re.sub(pattern, '', remainder, flags=re.I)
    for pattern, offset, label in [(r'下週|下星期|\bnext week\b', 1, '下週'),
                                   (r'本週|這週|這星期|\bthis week\b', 0, '本週'),
                                   (r'上週|上星期|\blast week\b', -1, '上週')]:
        if re.search(pattern, remainder, re.I):
            add(today - timedelta(days=today.weekday()) + timedelta(weeks=offset), 7, label)
            remainder = re.sub(pattern, '', remainder, flags=re.I)
    relative = re.search(r'([一二三四五六七八九十兩\d]+)(?:天後|日後)|\bin\s+(\d+)\s+days?\b', remainder, re.I)
    if relative:
        days = chinese_number(relative[1] or relative[2])
        if days > 366:
            raise ValueError('請將查詢日期限制在一年內，或提供明確年月日。')
        add(today + timedelta(days=days), 1, f'{days}天後')
        remainder = remainder[:relative.start()] + remainder[relative.end():]
    if len(choices) > 1:
        raise ValueError('一次請查一個日期或一個週範圍，避免混用多個期間。')
    if re.search(r'月|年|星期|週|周|禮拜|月底|(?<!\d)\d+\s*天|\b(?:week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday|days)\b', remainder.replace('未來14天', '').replace('未來兩週', ''), re.I):
        raise ValueError('請提供明確年月日，或使用今天、明天、本週、下週。')
    if choices:
        return choices[0]
    return CalendarPeriod(now, now + timedelta(days=14), '未來14天')
