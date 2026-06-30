import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_PLUGIN_DIR_TEXT = str(_PLUGIN_DIR)
if _PLUGIN_DIR_TEXT not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR_TEXT)

import unittest

from private_humanizer.config import load_config
from private_humanizer.context import _is_private, extract_chat_fields, match_target_private_chat
from private_humanizer.guards import (
    INTIMATE_BRIDGE_FALLBACKS,
    INTIMATE_TERMS,
    guard_memory_items,
    guard_reply_text,
    is_intimate_context,
)
from private_humanizer.prompting import append_extra_prompt, build_humanizer_prompt


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
            "preferences": "聊天偏好：喜欢亲密但自然的陪伴。",
            "important_dates": "生日：未知",
        }
    ],
}


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

    def test_is_private_with_unknown_chat_type_and_no_group_id(self):
        self.assertTrue(_is_private({"group_id": "", "chat_type": ""}))
        self.assertTrue(_is_private({"group_id": "", "chat_type": "private"}))
        self.assertFalse(_is_private({"group_id": "", "chat_type": "group"}))
        self.assertFalse(_is_private({"group_id": "123", "chat_type": ""}))
        self.assertFalse(_is_private({"group_id": "", "chat_type": "unknown"}))

    def test_extract_chat_fields_from_nested_message(self):
        fields = extract_chat_fields({
            "message": {"platform": "qq", "user_id": "123", "chat_type": "private"},
            "session_id": "s1",
        })
        self.assertEqual(fields["platform"], "qq")
        self.assertEqual(fields["user_id"], "123")
        self.assertEqual(fields["chat_type"], "private")

    def test_prompt_contains_boundaries(self):
        config = load_config(RAW_CONFIG)
        prompt = build_humanizer_prompt(config, config.target_profiles[0])
        self.assertIn("事实边界", prompt)
        self.assertIn("未知", prompt)
        self.assertIn("目标用户", prompt)

    def test_prompt_contains_life_environment_and_schedule(self):
        config = load_config(RAW_CONFIG)
        prompt = build_humanizer_prompt(config, config.target_profiles[0])
        self.assertIn("虚拟生活环境参考", prompt)
        self.assertIn("主程序 LLM", prompt)
        self.assertIn("私聊日程参考", prompt)
        self.assertIn("下午整理房间", prompt)

    def test_append_extra_prompt_sets_when_empty(self):
        result = append_extra_prompt({"extra_prompt": ""}, "test")
        self.assertIn("test", result["extra_prompt"])

    def test_append_extra_prompt_appends(self):
        result = append_extra_prompt({"extra_prompt": "hello"}, "world")
        self.assertEqual(result["extra_prompt"], "hello\n\nworld")

    def test_guard_rewrites_unsupported_preference(self):
        config = load_config(RAW_CONFIG)
        result = guard_reply_text("我给你准备了你最爱的蜜桃粽子。", config, config.target_profiles[0])
        self.assertTrue(result.changed)
        self.assertIn("不敢", result.text)

    def test_guard_fallback_for_fact_uses_right_template(self):
        config = load_config(RAW_CONFIG)
        result = guard_reply_text("我给你买了一件你最爱的东西。", config)
        self.assertTrue(result.changed)
        self.assertIn("不敢", result.text)

    def test_guard_blocks_daily_topic_shift_in_intimate_context(self):
        config = load_config(RAW_CONFIG)
        result = guard_reply_text(
            "那我们中午打算吃点什么呢♪",
            config,
            config.target_profiles[0],
            context_text="肉棒还在小穴里没有拔出来呢",
        )
        self.assertTrue(result.changed)
        self.assertIn("intimate_topic_shift", result.risk_types)

    def test_guard_keeps_daily_topic_without_intimate_context(self):
        config = load_config(RAW_CONFIG)
        result = guard_reply_text(
            "那我们中午打算吃点什么呢♪",
            config,
            config.target_profiles[0],
            context_text="早上好呢",
        )
        self.assertFalse(result.changed)

    def test_guard_does_not_false_trigger_on_common_words(self):
        config = load_config(RAW_CONFIG)
        result = guard_reply_text(
            "抱抱你，今天身体舒服吗？",
            config,
            config.target_profiles[0],
            context_text="我今天跑完步腿有点酸",
        )
        self.assertFalse(result.changed)

    def test_intimate_bridge_fallbacks_are_gender_neutral(self):
        for fallback in INTIMATE_BRIDGE_FALLBACKS:
            self.assertNotIn("姐姐", fallback)

    def test_intimate_terms_excludes_common_words(self):
        self.assertNotIn("舒服", INTIMATE_TERMS)
        self.assertNotIn("身体", INTIMATE_TERMS)
        self.assertNotIn("腿", INTIMATE_TERMS)
        self.assertNotIn("嘴巴", INTIMATE_TERMS)
        self.assertNotIn("亲", INTIMATE_TERMS)
        self.assertNotIn("吻", INTIMATE_TERMS)
        self.assertNotIn("抱", INTIMATE_TERMS)

    def test_is_intimate_context_only_matches_explicit(self):
        self.assertTrue(is_intimate_context("我想要做爱"))
        self.assertTrue(is_intimate_context("肉棒"))
        self.assertFalse(is_intimate_context("今天身体不舒服"))
        self.assertFalse(is_intimate_context("亲，你好呀"))

    def test_memory_guard_filters_risky_items(self):
        config = load_config(RAW_CONFIG)
        filtered, blocked = guard_memory_items(["用户最喜欢桃子汽水", "用户今天说要加班"], config)
        self.assertEqual(filtered, ["用户今天说要加班"])
        self.assertEqual(len(blocked), 1)

    def test_memory_guard_handles_dict_items(self):
        config = load_config(RAW_CONFIG)
        filtered, blocked = guard_memory_items({"good": "hello", "fact": "用户最喜欢桃子汽水"}, config)
        self.assertEqual(filtered, {"good": "hello"})
        self.assertGreater(len(blocked), 0)

    def test_followup_config_defaults(self):
        config = load_config(RAW_CONFIG)
        self.assertTrue(config.proactive_followup.enabled)
        self.assertFalse(config.schedule.inject_into_planner)
        self.assertTrue(config.life_environment.auto_generate_when_empty)
        self.assertTrue(config.schedule.allow_user_interrupt)
        self.assertEqual(config.proactive_followup.delay_seconds, 35)
        self.assertFalse(config.logging.save_rewrite_pairs)

    def test_standard_user_id_mismatch_is_not_target(self):
        config = load_config(RAW_CONFIG)
        match = match_target_private_chat(
            config,
            {"session_id": "abc", "platform": "qq", "user_id": "not-target", "chat_type": "private"},
        )
        self.assertFalse(match.matched)

    def test_config_empty_fields_handled(self):
        empty_config = {
            "plugin": {"enabled": True, "target_platforms": [], "target_user_ids": []},
        }
        config = load_config(empty_config)
        self.assertTrue(config.plugin.enabled)
        self.assertEqual(config.target_profiles, [])

    def test_config_load_handles_none(self):
        config = load_config(None)
        self.assertTrue(config.plugin.enabled)


if __name__ == "__main__":
    unittest.main()
