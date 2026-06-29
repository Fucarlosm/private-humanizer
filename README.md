# 麦麦私聊拟人化增强

[MaiBot](https://github.com/MaiM-with-u/MaiBot) 私聊拟人增强插件。它会为指定私聊注入时间感、对象画像、亲密连续性和事实边界，让麦麦更像一个正在认真回消息的私聊对象：先接住当前话题，再自然回应，少一点模板味和小说旁白。

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🎯 指定私聊生效 | 支持白名单 / 黑名单模式，默认只对配置的 QQ 私聊用户生效 |
| 🧭 私聊画像注入 | 将称呼、偏好、重要日期、关系说明注入回复上下文 |
| 🕰️ 时间感增强 | 注入当前日期、时段、节假日和自定义日期参考 |
| 🏠 虚拟生活参考 | 可配置轻量生活场域，让回复更有日常感，但不会当成真实经历 |
| 💬 拟人私聊节奏 | 强化短句、承接、轻微主动、当前回应和口语化表达 |
| 💗 亲密上下文连续 | 对已开启的亲密语境保持称呼、语气强度和上一轮语义连续 |
| 🧠 记忆写入守卫 | 阻止无证据的个人事实、纪念日、礼物和共同经历写入表达学习 |
| 🧱 事实边界守卫 | 避免“你最爱”“我记得你”“我给你准备了”等无依据事实 |
| ✂️ 反小说化压缩 | 对过长、动作过密、场景化过强的回复做轻量压缩 |
| 🔁 主动续话检查 | 可选延迟补一句，带冷却和频率限制，避免刷屏 |
| 🧾 调试日志 | 可记录插件匹配、注入和改写情况，默认不保存完整改写对 |

## 🚀 快速开始

### 1. 安装

将 `private-humanizer/` 文件夹放到 MaiBot 的 `plugins/` 目录下：

```text
MaiBot/
└── plugins/
    └── private-humanizer/
        ├── plugin.py
        ├── config.toml
        ├── config.blank.toml
        ├── _manifest.json
        ├── private_humanizer/
        └── README.md
```

### 2. 配置

首次使用建议从空白模板复制：

```powershell
Copy-Item config.blank.toml config.toml
```

然后编辑 `config.toml`，至少填写目标私聊用户：

```toml
[plugin]
enabled = true
private_only = true
match_mode = "whitelist"
target_platforms = ["qq"]
target_user_ids = ["123456789"]

[[target_profiles]]
profile_id = "target"
platform = "qq"
user_id = "123456789"
display_name = "私聊对象"
basic_info = "称呼偏好：姐姐。\n"
preferences = "聊天偏好：先回答当前问题，再自然表达亲近感。\n"
important_dates = ""
relationship_notes = "优先接住对方刚说的话；不要编造未确认事实。\n"
```

### 3. 使用

配置完成后重启 MaiBot，或在 WebUI 中重载插件。插件会自动在目标私聊中生效，不需要额外指令。

适合增强的场景：

```text
日常聊天：少旁白，像即时通讯一样自然接话。
认真问题：先解决问题，再把亲近感放在称呼或句尾。
情绪陪伴：先确认感受，再给一句具体、轻量的陪伴。
亲密语境：保持上一轮称呼、语气和上下文，不突然重置设定。
固定问答：遇到“上次怎么说”时优先查记忆，没把握就承认并请对方提醒。
```

## ⚙️ 配置详解

### 插件开关

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | `true` | 总开关 |
| `private_only` | `true` | 只在私聊生效，群聊会跳过 |
| `match_mode` | `"whitelist"` | `whitelist` 只增强指定对象；`blacklist` 增强除黑名单外的私聊 |
| `target_platforms` | `["qq"]` | 允许的平台字段 |
| `target_user_ids` | `[]` | 目标私聊用户 ID |
| `target_session_ids` | `[]` | 可选，适配器更容易提供 session_id 时使用 |
| `blacklist_user_ids` | `[]` | 黑名单模式下排除的用户 |
| `blacklist_session_ids` | `[]` | 黑名单模式下排除的会话 |

### 私聊画像

| 字段 | 说明 |
|------|------|
| `display_name` | 注入 prompt 的对象称呼 |
| `basic_info` | 称呼、地区、作息等已确认基础信息 |
| `preferences` | 聊天偏好、记忆偏好、拟人偏好 |
| `important_dates` | 已确认的重要日期 |
| `relationship_notes` | 陪伴方式、固定问答、事实边界等关系说明 |

画像是可信事实来源。没写的内容会被视为未知，麦麦应询问、确认，或用“不确定 / 不敢乱猜”的方式回应。

### 时间与日程

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `time_awareness.enabled` | `true` | 注入当前日期、星期和时段 |
| `timezone` | `"Asia/Shanghai"` | 时间计算时区 |
| `custom_dates_enabled` | `true` | 是否启用自定义日期 |
| `schedule.enabled` | `true` | 注入轻量日程状态参考 |
| `refresh_hours` | `[7, 12, 18, 22]` | 状态刷新时段 |
| `manual_status` | `""` | 手动覆盖今日状态 |
| `manual_schedule` | `""` | 手动覆盖日程参考 |

时间、状态和生活环境只作为语气参考，不能说成已经真实发生过的经历。

### 生活环境参考

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | `true` | 是否注入生活环境参考 |
| `environment` | `""` | 固定场域描述，留空则自动生成低细节参考 |
| `auto_generate_when_empty` | `true` | 留空时让主程序生成简洁参考 |
| `use_as_reference_only` | `true` | 只作为背景候选，不当成事实 |

### 守卫与风格

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `fact_guard_enabled` | `true` | 改写无依据个人事实 |
| `anniversary_guard_enabled` | `true` | 避免乱猜纪念日 |
| `style_guard_enabled` | `true` | 压缩过长或过度场景化回复 |
| `memory_guard_enabled` | `true` | 阻止可疑自创事实写入记忆 |
| `max_reply_chars_soft` | `80` | 风格软限制 |
| `max_reply_chars_hard` | `160` | 风格硬限制 |

### 主动续话

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | `false` | 是否启用延迟补一句 |
| `delay_seconds` | `35` | 延迟检查秒数 |
| `cooldown_seconds` | `900` | 冷却时间 |
| `max_per_hour` | `2` | 每小时最多触发次数 |
| `min_reply_chars` | `2` | 太短回复可跳过 |
| `intent` | 内置中文说明 | 主动续话判断提示 |

## 🧩 工作原理

插件注册以下 MaiBot hook：

| Hook | 作用 |
|------|------|
| `maisaka.replyer.before_request` | 在回复前注入私聊增强 prompt |
| `maisaka.replyer.before_model_request` | 在最终模型消息中补充边界和画像 |
| `maisaka.replyer.after_response` | 对无依据事实、过长或过度场景化回复做轻量修正 |
| `expression.learn.before_upsert` | 阻止疑似自创事实进入表达学习 |

## 📋 从旧版迁移

1. 备份现有 `config.toml`。
2. 用新版文件替换 `plugin.py`、`private_humanizer/`、`README.md` 和 `_manifest.json`。
3. 对照 `config.blank.toml` 补齐新字段。
4. 确认 `target_user_ids`、`target_profiles.user_id` 和 `display_name` 已填写。
5. 重启 MaiBot 或在 WebUI 重载插件。

## 🔧 排错

### 插件加载了但没有效果

优先检查：

1. `[plugin].enabled` 是否为 `true`。
2. `target_user_ids` 是否填写真实私聊用户 ID。
3. `target_platforms` 是否和适配器平台字段一致，例如 `qq`。
4. 当前消息是否来自私聊。
5. 如果适配器没有传 `user_id`，尝试填写 `target_session_ids`。

### 群聊也触发了

确认：

```toml
[plugin]
private_only = true
```

如果仍然触发，说明适配器传入的 hook payload 缺少明确群聊字段。可以临时使用 `target_session_ids` 限定目标会话。

### 中文显示乱码

插件文件使用 UTF-8 保存。PowerShell 中 `Get-Content` 显示乱码通常是终端代码页问题，不代表文件损坏。可使用支持 UTF-8 的编辑器打开，或执行：

```powershell
chcp 65001
```

### 修改配置后没有变化

重启 MaiBot 或在 WebUI 中重载插件。插件实现了 `on_config_update`，但热更新能力取决于当前 MaiBot 插件运行时版本。

## 🧪 测试

在插件根目录运行：

```powershell
python -m unittest discover -s tests
```

## 📄 License

MIT
