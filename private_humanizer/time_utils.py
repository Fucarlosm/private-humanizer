from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import HumanizerConfig


WEEKDAYS_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


CN_FIXED_HOLIDAYS = {
    "01-01": "元旦",
    "02-14": "情人节",
    "03-08": "妇女节",
    "05-01": "劳动节",
    "06-01": "儿童节",
    "10-01": "国庆节",
    "12-24": "平安夜",
    "12-25": "圣诞节",
}


def now_in_timezone(timezone_name: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(timezone_name))
    except Exception:
        return datetime.now(tz=timezone_from_name(timezone_name))


def timezone_from_name(name: str):
    if str(name or "").strip() in {"Asia/Shanghai", "Asia/Chongqing", "Asia/Harbin", "Asia/Urumqi", "CN", "PRC"}:
        return timezone(timedelta(hours=8), name="Asia/Shanghai")
    return timezone(timedelta(hours=8), name="Asia/Shanghai")


def period_name(hour: int) -> str:
    if 5 <= hour < 9:
        return "早晨"
    if 9 <= hour < 12:
        return "上午"
    if 12 <= hour < 14:
        return "中午/午休前后"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 22:
        return "晚上"
    return "深夜/睡前"


def nearby_dates(config: HumanizerConfig, now: datetime) -> list[str]:
    items: list[str] = []
    today_key = now.strftime("%m-%d")
    tomorrow_key = (now + timedelta(days=1)).strftime("%m-%d")
    for key, name in CN_FIXED_HOLIDAYS.items():
        if key == today_key:
            items.append(f"今天是{name}")
        elif key == tomorrow_key:
            items.append(f"明天是{name}")

    if config.time_awareness.custom_dates_enabled:
        for item in config.time_awareness.custom_dates:
            name = str(item.get("name", "")).strip()
            date = str(item.get("date", "")).strip()
            desc = str(item.get("description", "")).strip()
            if not name or not date:
                continue
            suffix = f"：{desc}" if desc else ""
            if date.endswith(today_key) or date == now.strftime("%Y-%m-%d"):
                items.append(f"今天是{name}{suffix}")
            elif date.endswith(tomorrow_key) or date == (now + timedelta(days=1)).strftime("%Y-%m-%d"):
                items.append(f"明天是{name}{suffix}")
    return items


def build_time_summary(config: HumanizerConfig, now: datetime | None = None) -> str:
    now = now or now_in_timezone(config.time_awareness.timezone)
    tomorrow = now + timedelta(days=1)
    lines = [
        "当前时间信息：",
        f"- 日期：{now:%Y-%m-%d}，{WEEKDAYS_CN[now.weekday()]}",
        f"- 当前时段：{period_name(now.hour)}",
        f"- 明天：{tomorrow:%Y-%m-%d}，{WEEKDAYS_CN[tomorrow.weekday()]}",
    ]
    nearby = nearby_dates(config, now)
    if nearby:
        lines.append("- 近期明确日期：" + "；".join(nearby))
    lines.append("- 对话建议：结合当前时段自然回应午饭、下班、睡前、节假日等话题；不要乱猜纪念日。")
    return "\n".join(lines)


def build_status_reference(config: HumanizerConfig, now: datetime | None = None) -> str:
    if config.schedule.manual_status and config.schedule.allow_manual_override:
        return config.schedule.manual_status.strip()

    now = now or now_in_timezone(config.time_awareness.timezone)
    period = period_name(now.hour)
    if "早晨" in period:
        status = "刚开始一天，状态还在慢慢进入节奏，适合简短自然地回应。"
    elif "上午" in period:
        status = "上午在处理日常事项，回复应清楚直接，不主动编造正在做的具体事。"
    elif "中午" in period:
        status = "午饭或午休前后，状态偏轻松，适合自然关心对方吃饭和休息。"
    elif "下午" in period:
        status = "下午在平稳处理日常安排，适合陪伴式聊天，少写场景动作。"
    elif "晚上" in period:
        status = "晚上节奏放慢，适合更温柔地回应，但不要扩写成剧情。"
    else:
        status = "深夜或睡前，应更克制、简短、安稳，不制造新事件。"
    return f"今日状态参考：{status} 这只是状态参考，不是已经发生的事实。"


def build_life_schedule_reference(config: HumanizerConfig, now: datetime | None = None) -> str:
    now = now or now_in_timezone(config.time_awareness.timezone)
    manual = config.schedule.manual_schedule.strip()
    if manual:
        schedule_text = manual
    else:
        hour = now.hour
        if 5 <= hour < 8:
            schedule_text = "清晨：慢慢醒来、整理心情，适合短句问候和轻柔陪伴。"
        elif 8 <= hour < 11:
            schedule_text = "上午：处理日常小事、整理房间或做自己的轻量安排，回复应清楚自然。"
        elif 11 <= hour < 14:
            schedule_text = "中午：准备午饭、吃饭或午休前后，适合自然关心吃饭和休息。"
        elif 14 <= hour < 17:
            schedule_text = "下午：安静做事、看书、整理东西或短暂休息，适合陪伴式闲聊。"
        elif 17 <= hour < 20:
            schedule_text = "傍晚：节奏放松，可能准备晚饭或从白天安排里收尾，适合温柔接话。"
        elif 20 <= hour < 23:
            schedule_text = "晚上：更适合放慢节奏、聊天、休息和稳定陪伴。"
        else:
            schedule_text = "深夜/睡前：更克制、简短、安稳，不主动制造新事件。"

    lines = [
        "私聊日程参考：",
        schedule_text,
        "日程使用规则：这只是当前时段的行为候选和语气参考，不是已发生事实；除非用户询问或上下文需要，不要主动宣称自己刚刚完成了某个具体事项。",
    ]
    if config.schedule.allow_user_interrupt:
        lines.append(
            "如果用户在聊天中让 MaiBot 做其他事情、改变场景或推进新的互动，请根据人设、关系和当前提示词判断是否自然打断当前日程；通常应优先承接用户指示，并把新指示作为接下来的当前状态参考。"
        )
    else:
        lines.append("如果用户指示与日程冲突，请先简短确认，再谨慎承接。")
    if config.schedule.reference_only:
        lines.append("不要把日程写成固定剧本，不要为了贴合日程而忽略用户刚说的话。")
    return "\n".join(lines)
