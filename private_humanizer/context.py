from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .config import HumanizerConfig, TargetProfile


PRIVATE_HINTS = {"private", "friend", "direct", "dm", "单聊", "私聊", "person"}
GROUP_HINTS = {"group", "guild", "channel", "群聊", "群"}
GROUP_PROMPT_SIGNALS = (
    "group_id",
    "group_name",
    "qq_group",
    "群聊",
    "群消息",
    "群组",
    "群名称",
    "群成员",
    "群号",
    "group_chat",
    "group_session",
)
_SPEAKER_PATTERN = re.compile(r"\[([^\[\]]{1,32})\]")


@dataclass(slots=True)
class MatchResult:
    matched: bool
    profile: TargetProfile | None = None
    reason: str = ""
    platform: str = ""
    user_id: str = ""
    session_id: str = ""
    group_id: str = ""
    chat_type: str = ""


def extract_chat_fields(kwargs: dict[str, Any]) -> dict[str, str]:
    candidates: list[dict[str, Any]] = [kwargs]
    for key in (
        "message",
        "target_message",
        "chat_info",
        "session",
        "metadata",
        "event",
        "reply_tool_args",
    ):
        value = kwargs.get(key)
        if isinstance(value, dict):
            candidates.append(value)

    def first(*names: str) -> str:
        for source in candidates:
            for name in names:
                value = source.get(name)
                if value is not None and str(value).strip():
                    return str(value).strip()
        return ""

    chat_type = first("chat_type", "message_type", "conversation_type", "scope", "type")
    return {
        "platform": first("platform", "adapter", "platform_name"),
        "user_id": first("user_id", "sender_id", "from_user_id", "person_id", "target_user_id"),
        "session_id": first("session_id", "chat_id", "stream_id", "conversation_id"),
        "group_id": first("group_id", "guild_id", "channel_id"),
        "chat_type": chat_type.lower(),
    }


def _is_private(fields: dict[str, str]) -> bool:
    chat_type = fields.get("chat_type", "").lower()
    group_id = fields.get("group_id", "")
    if group_id:
        return False
    if chat_type in GROUP_HINTS:
        return False
    if chat_type in PRIVATE_HINTS:
        return True
    return False


def is_definitely_group(fields: dict[str, str]) -> bool:
    if fields.get("group_id"):
        return True
    return fields.get("chat_type", "").lower() in GROUP_HINTS


def detect_group_from_prompt_text(text: str) -> bool:
    if not text:
        return False
    return any(signal in text for signal in GROUP_PROMPT_SIGNALS)


def count_distinct_speakers(text: str) -> int:
    if not text:
        return 0
    speakers: set[str] = set()
    for match in _SPEAKER_PATTERN.finditer(text):
        speaker = match.group(1).strip()
        if speaker:
            speakers.add(speaker)
    return len(speakers)


def has_structured_name_match(text: str, name: str) -> bool:
    if not name or not text:
        return False
    return (
        f"[{name}]" in text
        or f"{name} 发送" in text
        or f'user="{name}"' in text
        or f'nickname="{name}"' in text
    )


def match_target_private_chat(config: HumanizerConfig, kwargs: dict[str, Any]) -> MatchResult:
    if not config.plugin.enabled:
        return MatchResult(False, reason="plugin disabled")

    fields = extract_chat_fields(kwargs)
    platform = fields["platform"]
    user_id = fields["user_id"]
    session_id = fields["session_id"]
    chat_type = fields["chat_type"]

    if config.plugin.private_only and not _is_private(fields):
        return MatchResult(False, reason="not private chat", **fields)

    if config.plugin.target_platforms and platform and platform not in config.plugin.target_platforms:
        return MatchResult(False, reason="platform mismatch", **fields)

    if config.plugin.match_mode == "blacklist":
        if user_id and user_id in config.plugin.blacklist_user_ids:
            return MatchResult(False, reason="blacklisted user", **fields)
        if session_id and session_id in config.plugin.blacklist_session_ids:
            return MatchResult(False, reason="blacklisted session", **fields)
        default_profile = config.target_profiles[0] if config.target_profiles else TargetProfile(platform=platform)
        return MatchResult(True, profile=default_profile, reason="blacklist mode matched", **fields)

    for profile in config.target_profiles:
        profile_platform_ok = not profile.platform or not platform or profile.platform == platform
        user_ok = bool(profile.user_id and profile.user_id == user_id)
        session_ok = bool(profile.session_id and profile.session_id == session_id)
        if profile_platform_ok and (user_ok or session_ok):
            return MatchResult(True, profile=profile, reason="profile matched", **fields)

    if user_id and user_id in config.plugin.target_user_ids:
        profile = TargetProfile(profile_id=user_id, platform=platform, user_id=user_id)
        return MatchResult(True, profile=profile, reason="user_id matched", **fields)

    if session_id and session_id in config.plugin.target_session_ids:
        profile = TargetProfile(profile_id=session_id, platform=platform, session_id=session_id)
        return MatchResult(True, profile=profile, reason="session_id matched", **fields)

    return MatchResult(False, reason="not target", **fields)
