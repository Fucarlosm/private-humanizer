from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .config import HumanizerConfig, TargetProfile


FACT_PATTERNS = [
    r"你最(爱|喜欢|讨厌|常|习惯)",
    r"我记得你(最|之前|一直|曾经|说过)",
    r"你之前说(过)?",
    r"我们(相遇|认识|在一起|的纪念日|第一次)",
    r"我(给你)?(准备|买|做)了",
    r"你送我",
    r"你一直",
    r"你的(口味|习惯|生日|纪念日|爱好)",
]

ANNIVERSARY_PATTERNS = [
    r"今天.*(纪念日|什么日子|特殊日子)",
    r"明天.*(纪念日|什么日子|特殊日子)",
    r"这周[一二三四五六日天].*(纪念日|什么日子|特殊日子)",
    r"(相识|认识|在一起).*(第?\d+|多少).*(天|日|个月|年)",
]

SCENE_WORDS = [
    "沙发",
    "怀里",
    "抱着",
    "靠在",
    "蹭",
    "脸颊",
    "指尖",
    "耳边",
    "窗外",
    "灯光",
    "轻轻",
    "悄悄",
    "暖洋洋",
    "香气",
    "睡着",
    "窝在",
]

AFFECTION_CONTEXT_TERMS = [
    "陪我",
    "在吗",
    "想你",
    "需要你",
    "别走",
    "别离开",
    "靠近一点",
    "抱抱",
    "安慰我",
    "听我说",
    "继续说",
    "刚才的话",
    "不要跳开",
]

TOPIC_SHIFT_PATTERNS = [
    r"(中午|午饭|晚饭|吃饭|吃点|点些|煮点|开胃|饭|菜)",
    r"(天气|下雨|太阳|出门|上班|工作|日程|安排)",
    r"(喝水|口渴|洗漱|帮忙|打下手)",
]

AFFECTION_BRIDGE_FALLBACKS = [
    "我还在认真听你说，不会突然把话题放走。",
    "我接住刚才那句话了，会先顺着你真正想聊的地方回应。",
    "嗯，我在呢，刚才的重点我不会跳开。",
]

@dataclass(slots=True)
class GuardResult:
    changed: bool
    text: str
    risk_types: list[str] = field(default_factory=list)
    evidence: str = ""


def is_affection_context(*texts: str) -> bool:
    combined = "\n".join(text for text in texts if text)
    return any(term in combined for term in AFFECTION_CONTEXT_TERMS)


def _is_topic_shift_reply(text: str) -> bool:
    return any(re.search(pattern, text) for pattern in TOPIC_SHIFT_PATTERNS)


def _affection_bridge_fallback(context_text: str, reply_text: str) -> str:
    seed = len(context_text) + len(reply_text)
    return AFFECTION_BRIDGE_FALLBACKS[seed % len(AFFECTION_BRIDGE_FALLBACKS)]


def has_verified_evidence(text: str, profile: TargetProfile | None) -> bool:
    if not profile:
        return False
    haystack = "\n".join(block for _, block in profile.verified_blocks())
    if not haystack:
        return False
    compact_text = re.sub(r"\s+", "", text)
    compact_evidence = re.sub(r"\s+", "", haystack)
    return any(token and token in compact_evidence for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", compact_text))


def _risk_matches(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _compress_style(text: str, hard_limit: int) -> str:
    cleaned = re.sub(r"（[^）]{0,60}）", "", text)
    cleaned = re.sub(r"\*[^*]{0,80}\*", "", cleaned)
    cleaned = re.sub(r"。{2,}", "。", cleaned)
    sentences = re.split(r"(?<=[。！？!?])", cleaned)
    kept: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if any(word in sentence for word in SCENE_WORDS) and len(kept) >= 1:
            continue
        kept.append(sentence)
        if sum(len(item) for item in kept) >= hard_limit:
            break
    result = "".join(kept).strip() or cleaned.strip()
    return result[:hard_limit].rstrip("，,；;、") if len(result) > hard_limit else result


def _fallback_for_fact(text: str) -> str:
    if "准备" in text or "买" in text or "做" in text:
        return "这个我不敢直接说已经准备好了，怕把没发生的事说成真的。你想要什么可以告诉我，我会认真记住。"
    if "纪念日" in text or "什么日子" in text:
        return "我不敢乱猜重要日子，怕把你在意的事记错。你提醒我一下，我这次认真记住。"
    if "最" in text or "习惯" in text or "口味" in text:
        return "这个我还没有可靠依据，不想替你乱下结论。你愿意告诉我的话，我会按你说的记。"
    return "这件事我没有可靠依据，不想乱猜。你告诉我一点，我再认真回应。"


def guard_reply_text(
    text: str,
    config: HumanizerConfig,
    profile: TargetProfile | None = None,
    context_text: str = "",
) -> GuardResult:
    original = text or ""
    revised = original.strip()
    risks: list[str] = []

    if config.guard.fact_guard_enabled and _risk_matches(FACT_PATTERNS, revised):
        if not has_verified_evidence(revised, profile):
            risks.append("unsupported_fact")
            revised = _fallback_for_fact(revised)

    if config.guard.anniversary_guard_enabled and _risk_matches(ANNIVERSARY_PATTERNS, revised):
        if not has_verified_evidence(revised, profile):
            risks.append("anniversary_guess")
            revised = _fallback_for_fact(revised)

    scene_score = sum(revised.count(word) for word in SCENE_WORDS)
    if config.guard.style_guard_enabled:
        too_long = len(revised) > config.guard.max_reply_chars_hard
        too_scenic = scene_score >= 3 and len(revised) > config.guard.max_reply_chars_soft
        if too_long or too_scenic:
            risks.append("novelistic_style")
            revised = _compress_style(revised, config.guard.max_reply_chars_hard)

    if config.guard.style_guard_enabled and is_affection_context(context_text) and _is_topic_shift_reply(revised):
        risks.append("affection_topic_shift")
        revised = _affection_bridge_fallback(context_text, revised)

    return GuardResult(
        changed=revised != original.strip(),
        text=revised,
        risk_types=risks,
        evidence="verified profile matched" if risks and has_verified_evidence(original, profile) else "no verified evidence found",
    )


def guard_memory_items(items: Any, config: HumanizerConfig) -> tuple[Any, list[str]]:
    if not config.guard.memory_guard_enabled:
        return items, []

    blocked: list[str] = []

    def risky(value: Any) -> bool:
        text = str(value)
        return (
            _risk_matches(FACT_PATTERNS, text)
            or any(word in text for word in ("纪念日", "生日", "最爱", "最喜欢", "礼物", "共同经历"))
        )

    if isinstance(items, list):
        kept = []
        for item in items:
            if risky(item):
                blocked.append(str(item))
            else:
                kept.append(item)
        return kept, blocked

    if isinstance(items, dict):
        filtered = {}
        for key, value in items.items():
            if risky(key) or risky(value):
                blocked.append(f"{key}: {value}")
            else:
                filtered[key] = value
        return filtered, blocked

    if risky(items):
        return None, [str(items)]
    return items, []
