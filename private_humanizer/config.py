from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


#
# N.B.: The dataclasses below mirror the PluginConfigBase subclasses defined in
# ../plugin.py.  When adding or changing a configuration field, update BOTH files
# to keep the WebUI config model and the internal runtime model in sync.
#


DEFAULT_FOLLOWUP_INTENT = (
    "这是私聊增强插件发起的主动续话检查。请回看刚才这一轮用户发言和你已经发出的回复，"
    "像真人私聊一样判断是否还需要自然补一句。只有在话题仍有余温、对方可能期待承接、"
    "或你刚才的回复留下了可继续的情绪/信息时才主动发一条很短的后续；"
    "如果要发，1-2句即可，先回应用户刚说的话再自然延伸，不要开启全新话题；"
    "如果刚才已经完整收束、对方明显不需要继续、或继续会显得打扰，就选择不发。"
    "不要编造未确认事实，不要解释插件，不要重复刚才的话，不要预设未来安排。"
)


@dataclass(slots=True)
class PluginSection:
    enabled: bool = True
    private_only: bool = True
    target_platforms: list[str] = field(default_factory=lambda: ["qq"])
    target_user_ids: list[str] = field(default_factory=list)
    target_session_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TimeAwarenessSection:
    enabled: bool = True
    timezone: str = "Asia/Shanghai"
    holiday_region: str = "CN"
    custom_dates_enabled: bool = True
    custom_dates: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class ScheduleSection:
    enabled: bool = True
    generation_mode: str = "daily"
    refresh_hours: list[int] = field(default_factory=lambda: [7, 12, 18, 22])
    inject_into_planner: bool = False
    inject_into_replyer: bool = True
    allow_manual_override: bool = True
    manual_status: str = ""
    reference_only: bool = True
    allow_user_interrupt: bool = True
    manual_schedule: str = ""


@dataclass(slots=True)
class LifeEnvironmentSection:
    enabled: bool = True
    environment: str = ""
    auto_generate_when_empty: bool = True
    use_as_reference_only: bool = True


@dataclass(slots=True)
class ProfileSection:
    enabled: bool = True
    inject_into_private_prompt: bool = True
    require_evidence_for_preferences: bool = True


@dataclass(slots=True)
class GuardSection:
    fact_guard_enabled: bool = True
    anniversary_guard_enabled: bool = True
    style_guard_enabled: bool = True
    memory_guard_enabled: bool = True
    max_reply_chars_soft: int = 400
    max_reply_chars_hard: int = 800


@dataclass(slots=True)
class ProactiveFollowupSection:
    enabled: bool = True
    delay_seconds: int = 35
    cooldown_seconds: int = 180
    max_per_hour: int = 6
    min_reply_chars: int = 2
    intent: str = DEFAULT_FOLLOWUP_INTENT


@dataclass(slots=True)
class LoggingSection:
    enabled: bool = True
    log_level: str = "info"
    save_rewrite_pairs: bool = False


@dataclass(slots=True)
class TargetProfile:
    profile_id: str = ""
    platform: str = ""
    user_id: str = ""
    session_id: str = ""
    display_name: str = ""
    basic_info: str = ""
    preferences: str = ""
    important_dates: str = ""
    relationship_notes: str = ""

    def has_identity(self) -> bool:
        return bool(self.user_id or self.session_id)

    def verified_blocks(self) -> list[tuple[str, str]]:
        blocks = [
            ("基础信息", self.basic_info),
            ("偏好信息", self.preferences),
            ("重要日期", self.important_dates),
            ("关系说明", self.relationship_notes),
        ]
        return [(title, text.strip()) for title, text in blocks if text and text.strip()]


@dataclass(slots=True)
class HumanizerConfig:
    plugin: PluginSection = field(default_factory=PluginSection)
    time_awareness: TimeAwarenessSection = field(default_factory=TimeAwarenessSection)
    schedule: ScheduleSection = field(default_factory=ScheduleSection)
    life_environment: LifeEnvironmentSection = field(default_factory=LifeEnvironmentSection)
    profile: ProfileSection = field(default_factory=ProfileSection)
    guard: GuardSection = field(default_factory=GuardSection)
    proactive_followup: ProactiveFollowupSection = field(default_factory=ProactiveFollowupSection)
    logging: LoggingSection = field(default_factory=LoggingSection)
    target_profiles: list[TargetProfile] = field(default_factory=list)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _str_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _int_list(value: Any, default: list[int]) -> list[int]:
    result: list[int] = []
    for item in _as_list(value):
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result or default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    return value if isinstance(value, dict) else {}


def load_config(raw: dict[str, Any] | None) -> HumanizerConfig:
    data = raw or {}
    plugin = _section(data, "plugin")
    time_awareness = _section(data, "time_awareness")
    schedule = _section(data, "schedule")
    life_environment = _section(data, "life_environment")
    profile = _section(data, "profile")
    guard = _section(data, "guard")
    proactive_followup = _section(data, "proactive_followup")
    logging = _section(data, "logging")

    profiles: list[TargetProfile] = []
    for item in _as_list(data.get("target_profiles")):
        if not isinstance(item, dict):
            continue
        target = TargetProfile(
            profile_id=str(item.get("profile_id", "")).strip(),
            platform=str(item.get("platform", "")).strip(),
            user_id=str(item.get("user_id", "")).strip(),
            session_id=str(item.get("session_id", "")).strip(),
            display_name=str(item.get("display_name", "")).strip(),
            basic_info=str(item.get("basic_info", "")).strip(),
            preferences=str(item.get("preferences", "")).strip(),
            important_dates=str(item.get("important_dates", "")).strip(),
            relationship_notes=str(item.get("relationship_notes", "")).strip(),
        )
        if target.has_identity():
            profiles.append(target)

    config = HumanizerConfig(
        plugin=PluginSection(
            enabled=bool(plugin.get("enabled", True)),
            private_only=bool(plugin.get("private_only", True)),
            target_platforms=_str_list(plugin.get("target_platforms", ["qq"])),
            target_user_ids=_str_list(plugin.get("target_user_ids", [])),
            target_session_ids=_str_list(plugin.get("target_session_ids", [])),
        ),
        time_awareness=TimeAwarenessSection(
            enabled=bool(time_awareness.get("enabled", True)),
            timezone=str(time_awareness.get("timezone", "Asia/Shanghai")).strip() or "Asia/Shanghai",
            holiday_region=str(time_awareness.get("holiday_region", "CN")).strip() or "CN",
            custom_dates_enabled=bool(time_awareness.get("custom_dates_enabled", True)),
            custom_dates=[
                item for item in _as_list(time_awareness.get("custom_dates", [])) if isinstance(item, dict)
            ],
        ),
        schedule=ScheduleSection(
            enabled=bool(schedule.get("enabled", True)),
            generation_mode=str(schedule.get("generation_mode", "daily")).strip() or "daily",
            refresh_hours=_int_list(schedule.get("refresh_hours", [7, 12, 18, 22]), [7, 12, 18, 22]),
            inject_into_planner=bool(schedule.get("inject_into_planner", False)),
            inject_into_replyer=bool(schedule.get("inject_into_replyer", True)),
            allow_manual_override=bool(schedule.get("allow_manual_override", True)),
            manual_status=str(schedule.get("manual_status", "")).strip(),
            reference_only=bool(schedule.get("reference_only", True)),
            allow_user_interrupt=bool(schedule.get("allow_user_interrupt", True)),
            manual_schedule=str(schedule.get("manual_schedule", "")).strip(),
        ),
        life_environment=LifeEnvironmentSection(
            enabled=bool(life_environment.get("enabled", True)),
            environment=str(life_environment.get("environment", "")).strip(),
            auto_generate_when_empty=bool(life_environment.get("auto_generate_when_empty", True)),
            use_as_reference_only=bool(life_environment.get("use_as_reference_only", True)),
        ),
        profile=ProfileSection(
            enabled=bool(profile.get("enabled", True)),
            inject_into_private_prompt=bool(profile.get("inject_into_private_prompt", True)),
            require_evidence_for_preferences=bool(profile.get("require_evidence_for_preferences", True)),
        ),
        guard=GuardSection(
            fact_guard_enabled=bool(guard.get("fact_guard_enabled", True)),
            anniversary_guard_enabled=bool(guard.get("anniversary_guard_enabled", True)),
            style_guard_enabled=bool(guard.get("style_guard_enabled", True)),
            memory_guard_enabled=bool(guard.get("memory_guard_enabled", True)),
            max_reply_chars_soft=_safe_int(guard.get("max_reply_chars_soft", 400), 400),
            max_reply_chars_hard=_safe_int(guard.get("max_reply_chars_hard", 800), 800),
        ),
        proactive_followup=ProactiveFollowupSection(
            enabled=bool(proactive_followup.get("enabled", True)),
            delay_seconds=max(1, int(proactive_followup.get("delay_seconds", 35))),
            cooldown_seconds=max(0, int(proactive_followup.get("cooldown_seconds", 180))),
            max_per_hour=max(0, int(proactive_followup.get("max_per_hour", 6))),
            min_reply_chars=max(0, int(proactive_followup.get("min_reply_chars", 2))),
            intent=str(proactive_followup.get("intent", DEFAULT_FOLLOWUP_INTENT)).strip()
            or DEFAULT_FOLLOWUP_INTENT,
        ),
        logging=LoggingSection(
            enabled=bool(logging.get("enabled", True)),
            log_level=str(logging.get("log_level", "info")).strip() or "info",
            save_rewrite_pairs=bool(logging.get("save_rewrite_pairs", False)),
        ),
        target_profiles=profiles,
    )

    if config.guard.max_reply_chars_soft > config.guard.max_reply_chars_hard:
        config.guard.max_reply_chars_soft = config.guard.max_reply_chars_hard

    return config
