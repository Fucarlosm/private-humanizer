# 排错说明

## `No module named 'private_humanizer'`

原因：MaiBot 用绝对路径加载 `plugin.py`，Python 没有自动把插件根目录加入模块搜索路径。

处理：确认 `plugin.py` 开头有如下逻辑：

```python
PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))
```

并确认安装目录里存在：

```text
private-humanizer/
  plugin.py
  private_humanizer/
    __init__.py
```

## 插件加载了但没有效果

优先检查：

1. `config.toml` 中 `[plugin].enabled` 是否为 `true`。
2. `target_user_ids` 是否填写了真实私聊用户 ID。
3. `target_platforms` 是否和适配器平台字段一致，例如 `qq`。
4. 当前消息是否来自私聊。群聊会被跳过。
5. 如果适配器没有传 `user_id`，可以尝试填写 `target_session_ids` 或在画像里填写 `session_id`。

## 群聊也触发了

确认：

```toml
[plugin]
private_only = true
```

如果仍然触发，说明当前适配器传入的 hook payload 中没有明确的群聊字段。可以临时把目标限制为 `target_session_ids`，只允许指定私聊 session 生效。

## 中文显示乱码

插件文件使用 UTF-8 保存。如果 PowerShell 中 `Get-Content` 显示乱码，通常是终端代码页问题，不代表插件文件损坏。

可以用支持 UTF-8 的编辑器打开，或在 PowerShell 中执行：

```powershell
chcp 65001
```

## 修改配置后没有变化

重启 MaiBot 或在 WebUI 中重载插件。插件实现了 `on_config_update`，但实际是否热更新取决于当前 MaiBot 插件运行时版本。
