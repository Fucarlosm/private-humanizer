import unittest

from private_humanizer.config import load_config
from private_humanizer.context import (
    MatchResult,
    _is_private,
    count_distinct_speakers,
    detect_group_from_prompt_text,
    has_structured_name_match,
    is_definitely_group,
    match_target_private_chat,
)
from private_humanizer.guards import guard_memory_items, guard_reply_text
from private_humanizer.prompting import build_humanizer_prompt


RAW_CONFIG = {
    "plugin": {
        "enabled": True,
        "private_only": True,
        "target_platforms": ["qq"],
        "target_user_ids": ["123456789"],
    },
    "schedule": {
        "manual_schedule": "下午整理房间，晚上陪用户聊天。",
    },
    "life_environment": {
        "environment": "",
        "auto_generate_when_empty": True,
    },
    "target_profiles": [
        {
            "profile_id": "target",
            "platform": "qq",
            "user_id": "123456789",
            "display_name": "目标用户",
            "preferences": "聊天偏好：喜欢稳定但自然的陪伴。",
            "important_dates": "生日：未知",
        }
    ],
}


def _simulate_prompt_matching(config, text, session_id=""):
    if not config.plugin.enabled:
        return MatchResult(False, reason="plugin disabled")
    if not text.strip():
        return MatchResult(False, reason="empty prompt messages")
    if config.plugin.private_only:
        if detect_group_from_prompt_text(text):
            return MatchResult(False, reason="group prompt detected")
        if count_distinct_speakers(text) > 2:
            return MatchResult(False, reason="multiple speakers detected")
    if config.plugin.match_mode == "blacklist":
        if session_id and session_id in config.plugin.blacklist_session_ids:
            return MatchResult(False, reason="blacklisted session")
        default_profile = config.target_profiles[0] if config.target_profiles else None
        return MatchResult(True, profile=default_profile, reason="blacklist mode prompt match", session_id=session_id, chat_type="private")
    for profile in config.target_profiles:
        names = {profile.display_name, profile.profile_id, profile.user_id}
        names = {name for name in names if name}
        if any(has_structured_name_match(text, name) for name in names):
            return MatchResult(True, profile=profile, reason="prompt message structured match", platform=profile.platform, user_id=profile.user_id, session_id=session_id, chat_type="private")
    return MatchResult(False, reason="not target")


class CoreTest(unittest.TestCase):
    def test_matches_target_private_chat(self):
        config = load_config(RAW_CONFIG)
        match = match_target_private_chat(
            config,
            {"message": {"platform": "qq", "user_id": "123456789", "chat_type": "private"}},
        )
        self.assertTrue(match.matched)
        self.assertEqual(match.profile.display_name, "目标用户")

    def test_skips_group_chat(self):
        config = load_config(RAW_CONFIG)
        match = match_target_private_chat(
            config,
            {"message": {"platform": "qq", "user_id": "123456789", "group_id": "123", "chat_type": "group"}},
        )
        self.assertFalse(match.matched)

    def test_prompt_contains_boundaries(self):
        config = load_config(RAW_CONFIG)
        prompt = build_humanizer_prompt(config, config.target_profiles[0])
        self.assertIn("事实边界", prompt)
        self.assertIn("未知", prompt)
        self.assertIn("目标用户", prompt)
        self.assertIn("亲密承接风格", prompt)
        self.assertIn("拟人私聊节奏", prompt)

    def test_prompt_contains_life_environment_and_schedule(self):
        config = load_config(RAW_CONFIG)
        prompt = build_humanizer_prompt(config, config.target_profiles[0])
        self.assertIn("虚拟生活环境参考", prompt)
        self.assertIn("主程序 LLM", prompt)
        self.assertIn("私聊日程参考", prompt)
        self.assertIn("下午整理房间", prompt)

    def test_guard_rewrites_unsupported_preference(self):
        config = load_config(RAW_CONFIG)
        result = guard_reply_text("我给你准备了你最爱的蜜桃粽子。", config, config.target_profiles[0])
        self.assertTrue(result.changed)
        self.assertIn("不敢", result.text)

    def test_guard_blocks_daily_topic_shift_in_affection_context(self):
        config = load_config(RAW_CONFIG)
        result = guard_reply_text(
            "那我们中午打算吃点什么呢♪",
            config,
            config.target_profiles[0],
            context_text="我刚才说想你陪我继续聊，不要突然跳开呢",
        )
        self.assertTrue(result.changed)
        self.assertIn("affection_topic_shift", result.risk_types)

    def test_guard_keeps_daily_topic_without_affection_context(self):
        config = load_config(RAW_CONFIG)
        result = guard_reply_text(
            "那我们中午打算吃点什么呢♪",
            config,
            config.target_profiles[0],
            context_text="早上好呢",
        )
        self.assertFalse(result.changed)

    def test_guard_does_not_downgrade_explicit_intimacy(self):
        config = load_config(RAW_CONFIG)
        result = guard_reply_text(
            "我想继续说露骨的器官和体液细节。",
            config,
            config.target_profiles[0],
            context_text="用户正在亲密撒娇",
        )
        self.assertFalse(result.changed)
        self.assertEqual(result.risk_types, [])
        self.assertIn("器官", result.text)
        self.assertIn("体液", result.text)

    def test_memory_guard_filters_risky_items(self):
        config = load_config(RAW_CONFIG)
        filtered, blocked = guard_memory_items(
            ["用户最喜欢桃子汽水", "用户今天说要加班", "用户要求记住露骨器官细节"],
            config,
        )
        self.assertEqual(filtered, ["用户今天说要加班", "用户要求记住露骨器官细节"])
        self.assertEqual(len(blocked), 1)

    def test_followup_config_defaults(self):
        config = load_config(RAW_CONFIG)
        self.assertTrue(config.proactive_followup.enabled)
        self.assertFalse(config.schedule.inject_into_planner)
        self.assertTrue(config.life_environment.auto_generate_when_empty)
        self.assertTrue(config.schedule.allow_user_interrupt)
        self.assertEqual(config.proactive_followup.delay_seconds, 35)
        self.assertFalse(config.logging.save_rewrite_pairs)
        self.assertEqual(config.plugin.match_mode, "whitelist")
        self.assertEqual(config.plugin.blacklist_user_ids, [])

    def test_standard_user_id_mismatch_is_not_target(self):
        config = load_config(RAW_CONFIG)
        match = match_target_private_chat(
            config,
            {"session_id": "abc", "platform": "qq", "user_id": "not-target", "chat_type": "private"},
        )
        self.assertFalse(match.matched)


class PrivateChatDetectionTest(unittest.TestCase):
    def test_private_hints_are_private(self):
        self.assertTrue(_is_private({"chat_type": "private", "group_id": ""}))
        self.assertTrue(_is_private({"chat_type": "friend", "group_id": ""}))

    def test_group_hints_are_not_private(self):
        self.assertFalse(_is_private({"chat_type": "group", "group_id": ""}))
        self.assertFalse(_is_private({"chat_type": "private", "group_id": "999"}))

    def test_missing_metadata_is_not_assumed_private(self):
        self.assertFalse(_is_private({"chat_type": "", "group_id": ""}))
        self.assertFalse(_is_private({"chat_type": "unknown", "group_id": ""}))

    def test_is_definitely_group(self):
        self.assertTrue(is_definitely_group({"group_id": "123", "chat_type": ""}))
        self.assertTrue(is_definitely_group({"group_id": "", "chat_type": "group"}))
        self.assertFalse(is_definitely_group({"group_id": "", "chat_type": "private"}))


class PromptDetectionTest(unittest.TestCase):
    def test_detects_group_prompt_signals(self):
        self.assertTrue(detect_group_from_prompt_text("group_id=98765"))
        self.assertTrue(detect_group_from_prompt_text("这是群聊消息"))
        self.assertFalse(detect_group_from_prompt_text("你好呀，今天怎么样"))

    def test_counts_distinct_speakers(self):
        self.assertEqual(count_distinct_speakers("[目标用户] 你好"), 1)
        self.assertEqual(count_distinct_speakers("[目标用户] 你好\n[麦麦] 嗯嗯"), 2)
        self.assertEqual(count_distinct_speakers("[目标用户] 大家好\n[小明] 你好\n[小红] 欢迎"), 3)

    def test_structured_name_match_does_not_use_bare_substrings(self):
        self.assertTrue(has_structured_name_match("[目标用户] 你好呀", "目标用户"))
        self.assertTrue(has_structured_name_match("你想要回复的消息是 目标用户 发送的", "目标用户"))
        self.assertTrue(has_structured_name_match('user="目标用户"', "目标用户"))
        self.assertFalse(has_structured_name_match("今天和目标用户聊了很多", "目标用户"))
        self.assertFalse(has_structured_name_match("[不是目标用户的另一个人] 发言", "目标用户"))


class PromptMatchingRegressionTest(unittest.TestCase):
    def setUp(self):
        self.config = load_config(RAW_CONFIG)

    def test_group_prompt_with_target_name_in_history_does_not_match(self):
        group_prompt = (
            "群聊消息历史：\n"
            "[目标用户] 大家好\n"
            "[小明] 你好呀\n"
            "[小红] 欢迎欢迎\n"
            "group_id=98765"
        )
        result = _simulate_prompt_matching(self.config, group_prompt, session_id="group_session")
        self.assertFalse(result.matched)
        self.assertIn("group", result.reason)

    def test_group_prompt_with_multiple_speakers_only_does_not_match(self):
        group_prompt = "[目标用户] 今天天气不错\n[同事A] 是啊\n[同事B] 出去玩吗\n[同事C] 好啊"
        result = _simulate_prompt_matching(self.config, group_prompt, session_id="group_session")
        self.assertFalse(result.matched)
        self.assertIn("speaker", result.reason)

    def test_private_prompt_with_structured_name_matches(self):
        private_prompt = "你想要回复的消息是 目标用户 发送的 msg_id为 12345 的消息\n[目标用户] 今天好开心呀"
        result = _simulate_prompt_matching(self.config, private_prompt, session_id="private_session")
        self.assertTrue(result.matched)
        self.assertEqual(result.profile.display_name, "目标用户")

    def test_private_prompt_without_target_name_does_not_match(self):
        result = _simulate_prompt_matching(self.config, "[其他人] 你好", session_id="private_session")
        self.assertFalse(result.matched)


class BlacklistModeTest(unittest.TestCase):
    def setUp(self):
        self.config = load_config({
            "plugin": {
                "enabled": True,
                "private_only": True,
                "match_mode": "blacklist",
                "target_platforms": ["qq"],
                "blacklist_user_ids": ["999999999"],
                "blacklist_session_ids": ["blacklisted_session"],
            },
            "target_profiles": [
                {
                    "profile_id": "default",
                    "platform": "qq",
                    "display_name": "私聊对象",
                    "preferences": "聊天偏好：自然简短。",
                }
            ],
        })

    def test_matches_non_blacklisted_private_chat(self):
        match = match_target_private_chat(
            self.config,
            {"message": {"platform": "qq", "user_id": "111111111", "chat_type": "private"}},
        )
        self.assertTrue(match.matched)

    def test_rejects_blacklisted_user(self):
        match = match_target_private_chat(
            self.config,
            {"message": {"platform": "qq", "user_id": "999999999", "chat_type": "private"}},
        )
        self.assertFalse(match.matched)
        self.assertIn("blacklist", match.reason)

    def test_rejects_blacklisted_session(self):
        match = match_target_private_chat(
            self.config,
            {"message": {"platform": "qq", "session_id": "blacklisted_session", "chat_type": "private"}},
        )
        self.assertFalse(match.matched)
        self.assertIn("blacklist", match.reason)

    def test_rejects_group_chat_in_blacklist_mode(self):
        match = match_target_private_chat(
            self.config,
            {"message": {"platform": "qq", "user_id": "111111111", "group_id": "123", "chat_type": "group"}},
        )
        self.assertFalse(match.matched)

    def test_blacklist_prompt_matches_private(self):
        result = _simulate_prompt_matching(self.config, "[用户] 你好呀", session_id="new_session")
        self.assertTrue(result.matched)

    def test_blacklist_prompt_rejects_blacklisted_session(self):
        result = _simulate_prompt_matching(self.config, "[用户] 你好呀", session_id="blacklisted_session")
        self.assertFalse(result.matched)

    def test_blacklist_prompt_rejects_group(self):
        group_prompt = "群聊消息\n[用户] 你好\n[小明] 嗯\n[小红] 嗯"
        result = _simulate_prompt_matching(self.config, group_prompt, session_id="new_session")
        self.assertFalse(result.matched)

    def test_blacklist_mode_loads_profile_without_identity(self):
        self.assertEqual(self.config.target_profiles[0].display_name, "私聊对象")


if __name__ == "__main__":
    unittest.main()
