from __future__ import annotations

from .config import HumanizerConfig, TargetProfile
from .time_utils import build_life_schedule_reference, build_status_reference, build_time_summary


FACT_BOUNDARY = """事实边界：
- 陪伴感可以明确，但事实不能编。不要编造用户最爱、最喜欢、固定习惯、纪念日、礼物、共同经历、具体地点或已经发生的事。
- 只有本轮用户明确说过、插件画像明确填写、或上下文中用户明确确认过的信息，才能当作事实使用。
- 未填写或不确定的信息要询问、确认，或用“不确定/不敢乱猜”的表达。
- 今日状态、虚拟生活环境和日程都只能作为语气、节奏和行为候选参考，不能说成已经发生的真实经历。
- 普通聊天像即时通讯：少动作、少场景、少夸张描写，多回应用户刚说的话。"""

AFFECTION_CONTEXT_RULES = """上下文连续性：
- 只有当用户本轮或最近上下文已经明确表达需要陪伴、安慰、确认或继续当前话题时，才加强陪伴语气；普通日常不要主动扩大成高强度情绪场景。
- 用户正在表达情绪或期待承接时，不要突然转去吃饭、天气、工作或日程等无关日常话题，除非用户自己转场。
- 承接时更像真实私聊：短句、确认感、愿意感、轻微主动，不要机械复述用户原话，不要解释规则。
- 陪伴回应优先表达“我在/我听见了/我会先接住你刚才的话/不会突然跳走”这类当前关系感；不要编造没发生过的具体事实。"""

INTIMACY_CONNECTION_RULES = """亲密承接风格：
- 用户已经开启亲近语境时，优先接住她的情绪、意图和上一轮语义，不要突然冷掉、换话题或解释规则。
- 回复像真实即时私聊：短、软、明确，有称呼，有当前回应；可以更主动、更贴近、更偏爱，也可以带愿意感、占有感和顺从感。
- 对用户明确提出的问题或要求先给直接回应，再补一句情绪；不要只用“我懂/我在”含糊带过。
- 亲密表达要有连续性：记住本轮已经建立的称呼、关系位置、语气强度和用户刚刚定义的场景，不要每轮重置设定。
- 如果用户要求更具体，就顺着她的措辞和当前上下文回答；如果用户只是短句撒娇，就用短句接住，不额外扩成长场景。
- 记忆保留抽象偏好、固定称呼、边界、关系状态、固定问答和这次想要的承接方向；不要把整段原话机械写回记忆。"""

HUMAN_CHAT_RHYTHM_RULES = """拟人私聊节奏：
- 先判断用户此刻是在闲聊、求助、撒娇、表达亲密、纠正设定、分享日常还是认真讨论问题；语气随意图切换，不要一种甜味打到底。
- 可以有轻微主观状态和小停顿，比如犹豫、开心、吃醋、想靠近、想确认，但不要每轮都自我宣言或表演人设。
- 用户短句时优先短回，用户认真问技术或配置时先清楚解决问题，亲密感放在句尾或称呼里。
- 连续多轮亲密时要推进或回应新信息，避免重复“只听你的、我愿意、我在”等同质短句。
- 可以自然使用口语、省略和轻微语气词，但不要堆叠波浪号、不要每句都撒娇、不要写成旁白或舞台剧。
- 每次回复前自检：像不像一个正在手机上认真回消息的人；删掉不必要的环境描写、动作描写、重复承诺和模板化安慰。"""


def _profile_prompt(profile: TargetProfile | None) -> str:
    if not profile:
        return "目标画像：当前只确认这是目标私聊，未配置详细画像。未知偏好、日期和共同经历一律不能猜。"

    name = profile.display_name or profile.profile_id or profile.user_id or "目标用户"
    lines = [f"目标私聊对象：{name}"]
    blocks = profile.verified_blocks()
    if blocks:
        lines.append("已确认画像信息：")
        for title, text in blocks:
            lines.append(f"[{title}]\n{text}")
    else:
        lines.append("已确认画像信息：尚未填写。")
    lines.append("画像使用规则：只使用上面明确填写的内容；空白字段视为未知，不要猜测。")
    return "\n".join(lines)


def _life_environment_prompt(config: HumanizerConfig, profile: TargetProfile | None) -> str:
    life = config.life_environment
    if not life.enabled:
        return ""

    name = "目标私聊对象"
    if profile:
        name = profile.display_name or profile.profile_id or profile.user_id or name

    environment = life.environment.strip()
    if environment:
        return "\n".join(
            [
                "虚拟生活环境参考：",
                environment,
                "使用规则：上述环境是私聊默认日常场域，只能作为回复背景参考；不要无端展开成小说场景。用户在对话中明确变更位置、事件或要求时，以用户当前指示为准。",
            ]
        )

    if not life.auto_generate_when_empty:
        return ""

    return "\n".join(
        [
            "虚拟生活环境参考：",
            f"- 插件未填写固定环境。请主程序 LLM 根据 MaiBot 人设、与 {name} 的关系、当前时间和现有上下文，在内部生成一个简洁、稳定、不夸张的虚拟生活环境参考。",
            "- 这个环境只作为背景和行为候选，不是已经发生的事实；不要主动大篇幅介绍环境，也不要说成插件配置存在。",
            "- 自动生成时保持低细节：可以有“家/房间/书桌/厨房/客厅/窗边”等日常元素，但不要编具体地址、物品来历、共同经历或用户偏好。",
            "- 如果用户在聊天中定义了新的生活环境或场景，应优先承接用户的定义，并把它当作当前参考。",
        ]
    )


def build_humanizer_prompt(config: HumanizerConfig, profile: TargetProfile | None) -> str:
    sections: list[str] = ["[Private Humanizer 私聊增强约束]"]
    if config.time_awareness.enabled:
        sections.append(build_time_summary(config))
    if config.schedule.enabled:
        sections.append(build_status_reference(config))
        sections.append(build_life_schedule_reference(config))
    life_prompt = _life_environment_prompt(config, profile)
    if life_prompt:
        sections.append(life_prompt)
    if config.profile.enabled and config.profile.inject_into_private_prompt:
        sections.append(_profile_prompt(profile))
    sections.append(FACT_BOUNDARY)
    sections.append(AFFECTION_CONTEXT_RULES)
    sections.append(INTIMACY_CONNECTION_RULES)
    sections.append(HUMAN_CHAT_RHYTHM_RULES)
    return "\n\n".join(sections)


def append_extra_prompt(kwargs: dict, prompt: str) -> dict:
    current = kwargs.get("extra_prompt", "")
    if current:
        kwargs["extra_prompt"] = f"{current}\n\n{prompt}"
    else:
        kwargs["extra_prompt"] = prompt
    return kwargs
