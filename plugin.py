from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any

# MaiBot's plugin loader executes this file by absolute path. In that loading
# mode Python may not automatically put the plugin directory on sys.path, so
# local packages such as private_humanizer can fail to import after installation.
# Keep this bootstrap before every local import.
PLUGIN_DIR = Path(__file__).resolve().parent
PLUGIN_DIR_TEXT = str(PLUGIN_DIR)
if PLUGIN_DIR_TEXT not in sys.path:
    sys.path.insert(0, PLUGIN_DIR_TEXT)

from maibot_sdk import Field, HookHandler, MaiBotPlugin, PluginConfigBase
from maibot_sdk.types import ErrorPolicy, HookMode, HookOrder

from private_humanizer.audit import write_audit
from private_humanizer.config import DEFAULT_FOLLOWUP_INTENT, HumanizerConfig, TargetProfile, load_config
from private_humanizer.context import MatchResult, extract_chat_fields, match_target_private_chat
from private_humanizer.guards import guard_memory_items, guard_reply_text, is_intimate_context
from private_humanizer.prompting import append_extra_prompt, build_humanizer_prompt


PROMPT_MARKER = "[Private Humanizer 私聊增强约束]"
FOLLOWUP_LOG_WINDOW_SECONDS = 3600
INTIMATE_FOLLOWUP_INTENT = (
    "这是私聊增强插件发起的主动续话检查。最近上下文已经由用户明确开启亲密/暧昧话题；"
    "请只判断是否需要像真实私聊一样自然补一句很短的话。"
    "如果要发，承接刚才的亲密情绪和关系感，可以更主动一点，1-2句话即可，每句不超过30字；"
    "先承接感受再回应内容，不要突然转去吃饭、天气、工作或日程等无关话题；"
    "不要机械复述刚才的话，不要解释插件，不要编造未确认事实。"
    "如果刚才已经自然收束、对方明显转场、或自你上条回复后对方没有新的回应，就不要发。"
)


class PluginSectionConfig(PluginConfigBase):
    """Basic enablement and private chat target settings."""

    __ui_label__ = "基础设置"
    __ui_icon__ = "settings"
    __ui_order__ = 0

    config_version: str = Field(default="1.0.0", title="配置版本", description="供 MaiBot WebUI 识别配置版本，普通用户不要修改。")
    enabled: bool = Field(default=True, title="启用插件", description="关闭后插件安装但不生效。")
    private_only: bool = Field(default=True, title="只在私聊生效", description="建议开启，避免影响群聊。")
    target_platforms: list[str] = Field(default_factory=lambda: ["qq"], title="生效平台", description="QQ / NapCat 私聊一般填写 qq。")
    target_user_ids: list[str] = Field(default_factory=list, title="目标用户 QQ 号", description="插件只会对这些用户的私聊生效。")
    target_session_ids: list[str] = Field(default_factory=list, title="目标会话 ID", description="通常留空；只有无法按 user_id 识别时再填写。")


class TimeAwarenessConfig(PluginConfigBase):
    """Real date, weekday and time-period awareness."""

    __ui_label__ = "时间感知"
    __ui_icon__ = "calendar-clock"
    __ui_order__ = 1

    enabled: bool = Field(default=True, title="启用时间感知", description="让 MaiBot 知道当前日期、星期和时段。")
    timezone: str = Field(default="Asia/Shanghai", title="时区", description="中国大陆用户保持 Asia/Shanghai。")
    holiday_region: str = Field(default="CN", title="节假日地区", description="保留字段，默认 CN。")
    custom_dates_enabled: bool = Field(default=True, title="启用自定义日期", description="填写生日、相识日、纪念日等已确认日期时开启。")
    custom_dates: list[dict[str, str]] = Field(default_factory=list, title="自定义重要日期", description="格式为 name/date/description；不确定的日期请留空。")


class ScheduleConfig(PluginConfigBase):
    """Soft daily status and schedule reference."""

    __ui_label__ = "日程参考"
    __ui_icon__ = "sun"
    __ui_order__ = 2

    enabled: bool = Field(default=True, title="启用日程参考", description="让 MaiBot 根据当前时段更像真的在生活，但日程不是事实。")
    generation_mode: str = Field(default="daily", title="生成模式", description="保留 daily 即可。")
    refresh_hours: list[int] = Field(default_factory=lambda: [7, 12, 18, 22], title="状态刷新小时", description="用于区分早晨、中午、傍晚、睡前。")
    inject_into_planner: bool = Field(default=False, title="注入 Planner", description="建议关闭；长私聊中 Planner payload 可能较大。")
    inject_into_replyer: bool = Field(default=True, title="注入 Replyer", description="建议开启，让最终回复遵守私聊增强约束。")
    allow_manual_override: bool = Field(default=True, title="允许手动今日状态", description="开启后 manual_status 非空时优先使用。")
    manual_status: str = Field(default="", title="手动今日状态", description="可留空。填写后作为今日状态参考，不是已发生事实。")
    reference_only: bool = Field(default=True, title="日程仅作参考", description="建议开启。日程只影响语气和行为候选。")
    allow_user_interrupt: bool = Field(default=True, title="允许用户打断日程", description="用户让 MaiBot 做其他事时，MaiBot 会优先判断并承接用户当前指示。")
    manual_schedule: str = Field(default="", title="手动日程参考", description="可留空。留空时插件按当前时段自动生成轻量日程；填写后作为固定日程参考。")


class LifeEnvironmentConfig(PluginConfigBase):
    """Virtual living environment configuration for private chats."""

    __ui_label__ = "虚拟生活环境"
    __ui_icon__ = "home"
    __ui_order__ = 3

    enabled: bool = Field(default=True, title="启用虚拟生活环境", description="为私聊注入生活环境参考。")
    environment: str = Field(default="", title="固定虚拟生活环境", description="可留空。留空时由主程序 LLM 根据人设自动生成；填写时作为固定环境参考。")
    auto_generate_when_empty: bool = Field(default=True, title="留空时自动生成", description="环境字段留空时，让主程序 LLM 生成一个稳定、低细节的生活环境参考。")
    use_as_reference_only: bool = Field(default=True, title="环境仅作参考", description="建议开启。环境只作为背景，不主动扩写成小说场景。")


class ProfileConfig(PluginConfigBase):
    """Private target profile injection settings."""

    __ui_label__ = "画像规则"
    __ui_icon__ = "user-round-check"
    __ui_order__ = 4

    enabled: bool = Field(default=True, title="启用画像", description="开启后注入下方私聊对象画像。")
    inject_into_private_prompt: bool = Field(default=True, title="画像写入私聊提示词", description="开启后 MaiBot 能看到 display_name、偏好、禁忌等。")
    require_evidence_for_preferences: bool = Field(default=True, title="偏好必须有证据", description="建议开启。未填写的偏好、日期、共同经历视为未知。")


class TargetProfileConfig(PluginConfigBase):
    """Verified profile for a private chat target."""

    __ui_label__ = "私聊对象画像"
    __ui_icon__ = "contact-round"
    __ui_order__ = 5

    profile_id: str = Field(default="target", title="画像编号", description="内部编号，用于区分多个私聊对象。")
    platform: str = Field(default="qq", title="平台", description="QQ 私聊填写 qq。")
    user_id: str = Field(default="", title="目标用户 QQ 号", description="应与 target_user_ids 中的值一致。")
    session_id: str = Field(default="", title="会话 ID", description="通常留空。")
    display_name: str = Field(default="", title="显示称呼", description="MaiBot 识别这个私聊对象时使用的称呼。")
    basic_info: str = Field(default="", title="基础信息", description="只写确定事实，不知道就留空或写未知。")
    preferences: str = Field(default="", title="偏好信息", description="只写确认过的聊天偏好、内容偏好和禁忌。")
    important_dates: str = Field(default="", title="重要日期", description="只有确认过才写；不确定就留空。")
    relationship_notes: str = Field(default="", title="关系说明和禁忌", description="写 MaiBot 应如何陪伴，以及不能编造什么。")


class GuardConfig(PluginConfigBase):
    """Reply and memory guard settings."""

    __ui_label__ = "回复守卫"
    __ui_icon__ = "shield-check"
    __ui_order__ = 6

    fact_guard_enabled: bool = Field(default=True, title="事实守卫", description="防止无证据事实。")
    anniversary_guard_enabled: bool = Field(default=True, title="纪念日守卫", description="防止乱猜日期和相遇天数。")
    style_guard_enabled: bool = Field(default=True, title="风格守卫", description="减少过长、过度动作化和小说化回复。")
    memory_guard_enabled: bool = Field(default=True, title="记忆守卫", description="阻止模型自创个人事实进入表达学习。")
    max_reply_chars_soft: int = Field(default=400, title="软长度阈值", description="超过后更容易触发压缩。")
    max_reply_chars_hard: int = Field(default=800, title="硬长度上限", description="高风险长回复会被压缩到附近。")


class ProactiveFollowupConfig(PluginConfigBase):
    """Proactive follow-up settings."""

    __ui_label__ = "主动续话"
    __ui_icon__ = "message-circle-plus"
    __ui_order__ = 7

    enabled: bool = Field(default=True, title="启用主动续话", description="MaiBot 回复后延迟检查是否自然补一句。")
    delay_seconds: int = Field(default=35, title="续话延迟秒数", description="建议 20-60 秒。")
    cooldown_seconds: int = Field(default=180, title="冷却秒数", description="同一会话两次主动续话的最短间隔。")
    max_per_hour: int = Field(default=6, title="每小时最多触发次数", description="0 表示不限制。")
    min_reply_chars: int = Field(default=2, title="最短回复长度", description="上一条回复短于该长度时不安排续话。")
    intent: str = Field(default=DEFAULT_FOLLOWUP_INTENT, title="续话判断意图", description="传给 Maisaka 主动任务的意图说明。")


class LoggingConfig(PluginConfigBase):
    """Audit log settings."""

    __ui_label__ = "日志审计"
    __ui_icon__ = "file-clock"
    __ui_order__ = 8

    enabled: bool = Field(default=True, title="启用日志", description="记录插件拦截、改写和主动续话行为。")
    log_level: str = Field(default="info", title="日志等级", description="普通用户保持 info。")
    save_rewrite_pairs: bool = Field(default=False, title="保存改写前后文本", description="默认关闭以保护隐私；排查问题时可临时打开。")


class PrivateHumanizerRuntimeConfig(PluginConfigBase):
    """MaiBot private-chat humanizer configuration."""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig, description="Basic plugin settings.")
    time_awareness: TimeAwarenessConfig = Field(default_factory=TimeAwarenessConfig, description="Date and time awareness.")
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig, description="Soft daily schedule reference.")
    life_environment: LifeEnvironmentConfig = Field(default_factory=LifeEnvironmentConfig, description="Virtual living environment reference.")
    profile: ProfileConfig = Field(default_factory=ProfileConfig, description="Profile injection settings.")
    target_profiles: list[TargetProfileConfig] = Field(default_factory=lambda: [TargetProfileConfig()], description="Private chat target profiles.")
    guard: GuardConfig = Field(default_factory=GuardConfig, description="Reply and memory guards.")
    proactive_followup: ProactiveFollowupConfig = Field(default_factory=ProactiveFollowupConfig, description="Proactive follow-up settings.")
    logging: LoggingConfig = Field(default_factory=LoggingConfig, description="Audit log settings.")

class PrivateHumanizerPlugin(MaiBotPlugin):
    """Private-chat prompt injector and guard for target MaiBot users."""

    config_model = PrivateHumanizerRuntimeConfig

    def _audit(self, record: dict[str, Any], enabled: bool = True) -> None:
        config = self._config()
        write_audit(PLUGIN_DIR, enabled and config.logging.enabled, record, config.time_awareness.timezone)

    def _config(self) -> HumanizerConfig:
        """Read and normalize this plugin's own config.toml data.

        The plugin intentionally does not read MaiBot's bot_config.toml, because
        it is designed for all MaiBot users and should be portable between bots.
        """
        return load_config(self._raw_config_data())

    def _raw_config_data(self) -> dict[str, Any]:
        """Return config as a plain dict across MaiBot SDK versions."""
        if hasattr(self, "get_plugin_config_data"):
            try:
                data = self.get_plugin_config_data()
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        config = getattr(self, "config", None)
        if config is None:
            return {}
        if isinstance(config, dict):
            return config
        if hasattr(config, "model_dump"):
            return config.model_dump()
        if hasattr(config, "dict"):
            return config.dict()
        return self._object_to_dict(config)

    def _object_to_dict(self, value: Any) -> Any:
        """Convert simple config objects to dictionaries recursively."""
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [self._object_to_dict(item) for item in value]
        if isinstance(value, tuple):
            return [self._object_to_dict(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._object_to_dict(item) for key, item in value.items()}
        raw = getattr(value, "__dict__", {})
        return {
            key: self._object_to_dict(item)
            for key, item in raw.items()
            if not key.startswith("_")
        }

    def _match(self, kwargs: dict[str, Any], config: HumanizerConfig | None = None) -> MatchResult:
        """Return whether the current hook call belongs to a configured private chat."""
        active_config = config or self._config()
        direct_match = match_target_private_chat(active_config, kwargs)
        if direct_match.matched:
            self._remember_matched_session(direct_match.session_id)
            return direct_match

        if direct_match.reason in ("not private chat", "group prompt detected", "platform mismatch"):
            self.ctx.logger.debug("Private Humanizer: early reject reason=%s", direct_match.reason)
            return direct_match

        standard_fields = extract_chat_fields(kwargs)
        if standard_fields.get("user_id"):
            self.ctx.logger.debug(
                "Private Humanizer: user_id=%s present but not matched (reason=%s)",
                standard_fields.get("user_id"), direct_match.reason,
            )
            return direct_match

        session_id = str(kwargs.get("session_id") or "").strip()
        if session_id and session_id in self._matched_sessions():
            self.ctx.logger.info("Private Humanizer: matched via cached session=%s", session_id)
            profile = active_config.target_profiles[0] if active_config.target_profiles else None
            if profile is None and active_config.plugin.target_user_ids:
                profile = TargetProfile(
                    profile_id=active_config.plugin.target_user_ids[0],
                    platform=active_config.plugin.target_platforms[0] if active_config.plugin.target_platforms else "",
                    user_id=active_config.plugin.target_user_ids[0],
                )
            if profile is None:
                return MatchResult(False, reason="stale cached session, no target configured")
            return MatchResult(
                True,
                profile=profile,
                reason="known matched session",
                platform=profile.platform,
                user_id=profile.user_id,
                session_id=session_id,
                chat_type="private",
            )

        inferred_match = self._match_from_prompt_messages(active_config, kwargs)
        if inferred_match.matched:
            self.ctx.logger.info("Private Humanizer: matched via prompt messages")
            self._remember_matched_session(inferred_match.session_id)
        else:
            self.ctx.logger.debug(
                "Private Humanizer: no match (reason=%s, keys=%s)",
                inferred_match.reason,
                list(kwargs.keys())[:10],
            )
        return inferred_match

    def _matched_sessions(self) -> set[str]:
        sessions = getattr(self, "_private_humanizer_matched_sessions", None)
        if isinstance(sessions, set):
            return sessions
        sessions = set()
        setattr(self, "_private_humanizer_matched_sessions", sessions)
        return sessions

    def _remember_matched_session(self, session_id: str) -> None:
        normalized = str(session_id or "").strip()
        if normalized:
            self._matched_sessions().add(normalized)

    def _match_from_prompt_messages(self, config: HumanizerConfig, kwargs: dict[str, Any]) -> MatchResult:
        """Infer target private chat from prompt messages when MaiBot does not pass user_id.

        The caller (_match) has already rejected confirmed group chats before
        reaching this method, so matching on display_name / profile_id here is
        safe as a last-resort fallback.
        """
        if not config.plugin.enabled:
            self.ctx.logger.debug("Private Humanizer: plugin disabled in _match_from_prompt_messages")
            return MatchResult(False, reason="plugin disabled")

        messages = kwargs.get("messages")
        if not isinstance(messages, list):
            self.ctx.logger.debug("Private Humanizer: no prompt messages in kwargs (keys: %s)", list(kwargs.keys())[:10])
            return MatchResult(False, reason="no prompt messages")

        text = "\n".join(
            str(message.get("content_text") or message.get("content") or "")
            for message in messages
            if isinstance(message, dict)
        )
        if not text.strip():
            self.ctx.logger.debug("Private Humanizer: empty prompt messages text")
            return MatchResult(False, reason="empty prompt messages")

        if config.plugin.private_only:
            group_signals = ("group_id=", "qq_group_", "群聊", "频道", "guild_id", "channel_id")
            if any(signal in text for signal in group_signals):
                self.ctx.logger.info("Private Humanizer: group signal detected in prompt, skipping")
                return MatchResult(False, reason="group prompt detected")

        session_id = str(kwargs.get("session_id") or "").strip()
        candidates_list: list[str] = []
        for profile in config.target_profiles:
            candidates = {profile.user_id.strip(), profile.display_name.strip(), profile.profile_id.strip()}
            candidates.discard("")
            candidates_list = list(candidates)
            if not candidates:
                continue
            for candidate in candidates:
                if len(candidate) < 2:
                    continue
                if candidate in text:
                    self.ctx.logger.info(
                        "Private Humanizer: matched candidate=%s in prompt messages (session=%s)",
                        candidate, session_id,
                    )
                    return MatchResult(
                        True,
                        profile=profile,
                        reason="prompt message matched",
                        platform=profile.platform,
                        user_id=profile.user_id,
                        session_id=session_id,
                        chat_type="private",
                    )

        self.ctx.logger.debug(
            "Private Humanizer: no match in prompt messages (candidates=%s, text_preview=%.200s)",
            candidates_list, text,
        )
        return MatchResult(False, reason="not target")

    def _continue(self, modified_kwargs: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"action": "continue"}
        if modified_kwargs is not None:
            payload["modified_kwargs"] = modified_kwargs
        return payload

    def _inject_prompt_into_messages(self, messages: Any, prompt: str) -> list[dict[str, Any]] | None:
        if not isinstance(messages, list):
            return None

        updated: list[dict[str, Any]] = []
        inserted = False
        for item in messages:
            if not isinstance(item, dict):
                updated.append(item)
                continue

            message = dict(item)
            role = str(message.get("role") or "").lower()
            content = str(message.get("content") or message.get("content_text") or "")
            if role == "system" and not inserted:
                if PROMPT_MARKER not in content:
                    content = f"{content.rstrip()}\n\n{prompt}" if content.strip() else prompt
                    message["content"] = content
                    message["content_text"] = content
                inserted = True
            updated.append(message)

        if not inserted:
            updated.insert(0, {"role": "system", "content": prompt, "content_text": prompt})
        return updated

    async def on_load(self) -> None:
        config = self._config()
        profile_count = len(config.target_profiles)
        id_count = len(config.plugin.target_user_ids)
        self.ctx.logger.info(
            "Private Humanizer loaded: enabled=%s target_profiles=%d target_user_ids=%d",
            config.plugin.enabled,
            profile_count,
            id_count,
        )

    async def on_unload(self) -> None:
        for task in list(self._followup_tasks().values()):
            task.cancel()
        self._followup_tasks().clear()
        self.ctx.logger.info("Private Humanizer unloaded")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        self._matched_sessions().clear()
        self._followup_history().clear()
        for task in list(self._followup_tasks().values()):
            if not task.done():
                task.cancel()
        self._followup_tasks().clear()
        self.ctx.logger.info("Private Humanizer config updated: scope=%s version=%s", scope, version)

    async def inject_planner_prompt(self, **kwargs):
        """Optional helper for planner prompt injection (not registered as a hook by default).

        The active injection path is replyer.before_request via the
        inject_replyer_prompt hook. This method is kept for advanced use cases
        where a user manually registers it as a planner hook.
        """
        config = self._config()
        if not config.schedule.inject_into_planner:
            return self._continue()

        match = self._match(kwargs, config)
        if not match.matched:
            return self._continue()

        prompt = build_humanizer_prompt(config, match.profile)
        messages = self._inject_prompt_into_messages(kwargs.get("messages"), prompt)
        if messages is None:
            return self._continue()
        self._audit(
            {"stage": "planner_prompt", "chat_id": match.session_id, "user_id": match.user_id},
        )
        return self._continue({"messages": messages})

    @HookHandler(
        "maisaka.replyer.before_request",
        name="private_humanizer_replyer_prompt",
        description="Inject concise private-chat style rules before replyer.",
        mode=HookMode.BLOCKING,
        order=HookOrder.LATE,
        error_policy=ErrorPolicy.SKIP,
    )
    async def inject_replyer_prompt(self, **kwargs):
        config = self._config()
        if not config.schedule.inject_into_replyer:
            return self._continue()

        match = self._match(kwargs, config)
        if not match.matched:
            return self._continue()

        self.ctx.logger.info("Private Humanizer: inject_replyer_prompt matched (session=%s)", match.session_id)
        prompt = build_humanizer_prompt(config, match.profile)
        modified_kwargs = {"extra_prompt": append_extra_prompt({"extra_prompt": kwargs.get("extra_prompt", "")}, prompt)["extra_prompt"]}
        self._audit(
            {"stage": "replyer_prompt", "chat_id": match.session_id, "user_id": match.user_id},
        )
        return self._continue(modified_kwargs)

    @HookHandler(
        "maisaka.replyer.before_model_request",
        name="private_humanizer_replyer_model_prompt",
        description="Inject private-chat boundaries into the final replyer model messages.",
        mode=HookMode.BLOCKING,
        order=HookOrder.LATE,
        error_policy=ErrorPolicy.SKIP,
    )
    async def inject_replyer_model_prompt(self, **kwargs):
        config = self._config()
        if not config.schedule.inject_into_replyer:
            return self._continue()

        match = self._match(kwargs, config)
        if not match.matched:
            self.ctx.logger.debug("Private Humanizer: inject_replyer_model_prompt not matched, skipping")
            return self._continue()

        self.ctx.logger.info("Private Humanizer: inject_replyer_model_prompt matched (session=%s)", match.session_id)
        prompt = build_humanizer_prompt(config, match.profile)
        messages = self._inject_prompt_into_messages(kwargs.get("messages"), prompt)
        if messages is None:
            self.ctx.logger.warning("Private Humanizer: inject_replyer_model_prompt messages is None, skipping")
            return self._continue()
        self._audit(
            {"stage": "replyer_model_prompt", "chat_id": match.session_id, "user_id": match.user_id},
        )
        return self._continue({"messages": messages})

    @HookHandler(
        "maisaka.replyer.after_response",
        name="private_humanizer_reply_guard",
        description="Rewrite unsupported facts, anniversary guesses, and over-novelistic replies.",
        mode=HookMode.BLOCKING,
        order=HookOrder.LATE,
        error_policy=ErrorPolicy.SKIP,
    )
    async def guard_reply(self, **kwargs):
        config = self._config()
        match = self._match(kwargs, config)
        if not match.matched:
            return self._continue()

        path, text = self._find_reply_text(kwargs)
        if not text:
            return self._continue()

        context_text = self._collect_context_text(kwargs)
        result = guard_reply_text(text, config, match.profile, context_text=context_text)
        final_text = result.text if result.changed else text
        self._schedule_followup_if_needed(kwargs, config, match, final_text, context_text)
        if result.changed:
            modified_kwargs: dict[str, Any] = {}
            target_dict: dict[str, Any] = modified_kwargs
            for key in path[:-1]:
                target_dict[key] = {}
                target_dict = target_dict[key]
            target_dict[path[-1]] = result.text
            self._audit(
                {
                    "stage": "reply_guard",
                    "chat_id": match.session_id,
                    "user_id": match.user_id,
                    "risk_type": ",".join(result.risk_types),
                    "original_reply": text,
                    "rewritten_reply": result.text,
                    "evidence": result.evidence,
                },
                enabled=config.logging.save_rewrite_pairs,
            )
            return self._continue(modified_kwargs)
        return self._continue()

    def _followup_tasks(self) -> dict[str, asyncio.Task[Any]]:
        tasks = getattr(self, "_private_humanizer_followup_tasks", None)
        if isinstance(tasks, dict):
            return tasks
        tasks = {}
        setattr(self, "_private_humanizer_followup_tasks", tasks)
        return tasks

    def _followup_history(self) -> dict[str, list[float]]:
        history = getattr(self, "_private_humanizer_followup_history", None)
        if isinstance(history, dict):
            return history
        history = {}
        setattr(self, "_private_humanizer_followup_history", history)
        return history

    def _schedule_followup_if_needed(
        self,
        kwargs: dict[str, Any],
        config: HumanizerConfig,
        match: MatchResult,
        response_text: str,
        context_text: str = "",
    ) -> None:
        followup = config.proactive_followup
        if not followup.enabled:
            return
        session_id = str(match.session_id or kwargs.get("session_id") or "").strip()
        if not session_id:
            return
        if len((response_text or "").strip()) < followup.min_reply_chars:
            return
        if int(kwargs.get("retry_count") or 0) > 0:
            return

        tasks = self._followup_tasks()
        existing = tasks.get(session_id)
        if existing is not None and not existing.done():
            return

        now = time.time()
        history = self._followup_history()
        recent = [
            stamp
            for stamp in history.get(session_id, [])
            if now - stamp < FOLLOWUP_LOG_WINDOW_SECONDS
        ]
        history[session_id] = recent
        if followup.max_per_hour and len(recent) >= followup.max_per_hour:
            self._audit(
                {
                    "stage": "followup_skipped",
                    "chat_id": session_id,
                    "user_id": match.user_id,
                    "reason": "hourly limit reached",
                    "limit": followup.max_per_hour,
                },
            )
            return
        if recent and now - recent[-1] < followup.cooldown_seconds:
            return

        intimate = is_intimate_context(context_text, response_text)
        tasks[session_id] = asyncio.create_task(
            self._delayed_followup(session_id, config, match.user_id, response_text, intimate)
        )

    async def _delayed_followup(
        self,
        session_id: str,
        config: HumanizerConfig,
        user_id: str,
        response_text: str,
        intimate_context: bool = False,
    ) -> None:
        try:
            await asyncio.sleep(config.proactive_followup.delay_seconds)
            intent = INTIMATE_FOLLOWUP_INTENT if intimate_context else config.proactive_followup.intent
            result = await self.ctx.maisaka.proactive.trigger(
                stream_id=session_id,
                intent=intent,
                reason="private_humanizer_followup",
                metadata={
                    "source": "private_humanizer",
                    "last_reply_preview": (response_text or "").strip()[:120],
                    "intimate_context": intimate_context,
                },
            )
            success = bool(isinstance(result, dict) and result.get("success"))
            if success:
                self._followup_history().setdefault(session_id, []).append(time.time())
            self._audit(
                {
                    "stage": "followup_triggered" if success else "followup_failed",
                    "chat_id": session_id,
                    "user_id": user_id,
                    "result": result,
                },
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._audit(
                {
                    "stage": "followup_failed",
                    "chat_id": session_id,
                    "user_id": user_id,
                    "error": str(exc),
                },
            )
        finally:
            self._followup_tasks().pop(session_id, None)

    @HookHandler(
        "expression.learn.before_upsert",
        name="private_humanizer_memory_guard",
        description="Block suspicious self-created personal facts before expression learning upsert.",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        error_policy=ErrorPolicy.SKIP,
    )
    async def guard_expression_memory(self, **kwargs):
        config = self._config()
        match = self._match(kwargs, config)
        if not match.matched or not config.guard.memory_guard_enabled:
            return self._continue()

        # MaiBot hook payloads may vary by version. Check common container names
        # and only return fields that actually changed to keep RPC payloads small.
        modified_kwargs: dict[str, Any] = {}
        for key in ("items", "candidates", "expressions", "records", "data"):
            if key not in kwargs:
                continue
            filtered, blocked = guard_memory_items(kwargs[key], config)
            if blocked:
                modified_kwargs[key] = filtered
                self._audit(
                    {
                        "stage": "memory_guard",
                        "chat_id": match.session_id,
                        "user_id": match.user_id,
                        "risk_type": "unverified_memory",
                        "blocked": blocked,
                    },
                )
        return self._continue(modified_kwargs or None)

    def _collect_context_text(self, kwargs: dict[str, Any]) -> str:
        texts: list[str] = []

        def add_text(value: Any) -> None:
            if isinstance(value, str) and value.strip():
                texts.append(value.strip()[:240])

        def visit(value: Any, depth: int = 0) -> None:
            if value is None or depth > 3 or len(texts) >= 12:
                return
            if isinstance(value, str):
                add_text(value)
                return
            if isinstance(value, dict):
                for key in (
                    "processed_plain_text",
                    "plain_text",
                    "content",
                    "content_text",
                    "text",
                    "target_message_content",
                    "last_user_message",
                    "reply_reason",
                ):
                    add_text(value.get(key))
                for key in ("message", "target_message", "reply_message", "metadata", "reply_tool_args"):
                    if key in value:
                        visit(value[key], depth + 1)
                return
            if isinstance(value, (list, tuple)):
                for item in value[-8:]:
                    visit(item, depth + 1)

        for key in (
            "message",
            "target_message",
            "reply_message",
            "chat_history",
            "messages",
            "metadata",
            "reply_tool_args",
            "reply_reason",
        ):
            visit(kwargs.get(key))
        return "\n".join(dict.fromkeys(texts))

    def _find_reply_text(self, data: dict[str, Any]) -> tuple[list[Any], str]:
        """Find reply text in common MaiBot response payload shapes.

        Returns (path, text) so callers can build a properly-nested
        modified_kwargs dict for the SDK.
        """
        direct_keys = ("response", "reply", "content", "text", "message", "result")
        for key in direct_keys:
            value = data.get(key)
            if isinstance(value, str):
                return [key], value
            if isinstance(value, dict):
                nested_path, nested_text = self._find_reply_text(value)
                if nested_text:
                    return [key, *nested_path], nested_text
        return [], ""

def create_plugin():
    return PrivateHumanizerPlugin()
