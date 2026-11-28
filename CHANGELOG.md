# 更新日志

本文件记录 AstrBench 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0-alpha.4] - 2026-11-28

### 新增

- **日志面板工具**：右上角新增「复制」「目录」「全屏」三个按钮。复制取当前级别过滤后的全部日志（`navigator.clipboard` 失败时回退 `execCommand`）；目录在 Finder 中打开日志文件夹；全屏切换日志面板为整窗浮层，`Esc` 退出
- **日志自动落盘（双文件按天切分）**：
  - `log/backend-YYYY-MM-DD.log`：`loguru` 全量日志，含 SDK DEBUG 与异常堆栈，每天 0 点切分，保留 30 天，`enqueue=True` 保证 Flask 线程与 asyncio 线程安全
  - `log/frontend-YYYY-MM-DD.log`：与前端面板内容一致的业务日志（`[启动]` / `[UI]` / `[插件]` / `[切换]` / `[设置]` / `[ERROR]`），随 `LogBuffer.add()` 就地追加
  - 不再需要手动「保存」日志
- **插件指令别名与描述展示**：指令解析同时识别 `alias` / `aliases`（集合、列表、单字符串三种写法）与 `desc` / `description`；行为弹窗按「类型 + 主指令 + 别名 + 描述」展示
- **输入框指令提示（`/` 触发）**：输入 `/` 时在输入框上方竖向列出当前插件的全部指令（含别名、描述）；继续输入逐步收敛，唯一命中后自动收起。**仅作提示，不做 Tab 补全、不点击填入**
- **设置页双标签**：「设置」标题右侧并排 `AstrBench` / `AstrBot` 两个按钮，当前项高亮
  - **AstrBench**：默认主题、默认日志级别、日志轮询间隔、`bundled/config.json` 路径
  - **AstrBot**：`bundled/data/cmd_config.json` 路径 + JSON 编辑器 + 保存（前端先校验 JSON 合法性）
- **默认主题 / 默认日志级别**：写入 `bundled/config.json` 的 `ui` 段，新增 `POST /api/config/ui` 局部更新接口（只改 `ui`，其余字段原样保留）
- **新增 API**：`GET/POST /api/astrbot/config`、`POST /api/config/ui`、`GET /api/commands`、`POST /api/logs/open`、`GET /api/logs/path`

### 改进

- **数据目录重组**：`bundled/plugins` → `bundled/data/plugins`；插件生成的配置统一落到 `bundled/data/config/<插件名>_config.json`；新增 `bundled/data/cmd_config.json` 承载 AstrBot 侧配置（初始为空对象）
- **主题与日志级别改为完全以 `config.json` 为唯一来源**：移除 `localStorage` 记忆与系统深浅色回退；顶部「暗色/亮色」按钮、设置页两个下拉、日志面板级别选择，任一操作都即时写回 `config.json`
- **指令解析统一**：`/api/plugin/<name>/behaviors` 与新增 `/api/commands` 共用 `_parse_commands()`，避免两套正则不一致
- 启动日志增补「日志目录」提示，便于定位落盘位置
- 设置页 AstrBench 标签补一行说明：默认值写入 `config.json`，下次启动生效

### 修复

- 修复输入 `/` 时报 `TypeError: null is not an object (evaluating 'cmdHintEl.hidden = true')`：输入区补回 `.input-wrap` 与 `#cmd-hint` 容器，并在 `loadCommands()` / `updateCmdHint()` 增加空值保护
- 修复全屏按钮显示为「条纹方块」：`⛶` / `⤢`（U+26F6 / U+2922）在 macOS 系统字体缺字形，改用中文「全屏 / 还原」
- 修复日志面板空白：`aside.logs` 内补回被遗漏的 `<div id="log-view" class="log-view">`，`LogViewer.init(null, …)` 不再静默失效
- 修复插件配置保存仍写入相对路径 `Path("data/config")` 的残留逻辑，统一走 `PLUGIN_CONFIG_DIR`

### 已知问题

- `PluginHarness` 在 `session_waiter` 场景下存在分发问题（上游 Issue #32）
- 仅支持 macOS，Windows / Linux 未验证
- 仅支持文本消息，富媒体（图片、@、文件）未实现
- 假 LLM 固定回复，不解析 `system_prompt`
- 事件按钮、热重载尚未实现
- 打包为 `.app` 后 `bundled/` 位于只读的 `_MEIPASS`，此时写 `bundled/config.json` 不会持久（源码运行时正常）；后续需迁移到用户数据目录
- 插件运行时可能在工作目录生成数据文件（如 `fortune_data.json`），暂无独立数据目录隔离


## [0.1.0-alpha.3] - 2026-11-21

### 新增

- **插件配置界面**：点击插件卡片「设置」按钮，读取插件的 `_conf_schema.json` 动态生成表单，支持 bool / int / float / string / 多行文本 / 下拉选项，支持单项「恢复默认值」，保存后写入 `data/config/<插件名>_config.json`
- **配置表单组件化**：配置表单渲染逻辑拆分为独立组件 `web/components/config_form.js`，对外暴露 `ConfigForm.open(pluginName)`，与 `log_viewer.js` 保持同一套 IIFE + 全局对象风格，便于后续事件面板等组件复用

### 改进

- **插件卡片布局重排**：Logo 在左，右侧第一行为「显示名 + 版本号」同行排列，第二行为描述（最多两行截断）；三个操作按钮紧贴内容底部右对齐，卡片内边距由 16px 收窄到 14px，整体更紧凑
- **插件卡片不再显示插件目录名**：只展示 `display_name` 与版本号，避免长包名（如 `astrbot_plugin_xxx-main`）撑破布局；目录名仍用于内部识别与切换

### 修复

- 修复含 `MessageEventResult` 的导入行被较短模式优先匹配、导致 `cannot import name 'MessageEventResult'` 的问题：长模式前置，并增加正则整行兜底重写 `astrbot.api.event` / `astrbot.api.star` 导入
- 修复 `@filter.command(..., alias={...})` 转成 `@on_command(..., alias=...)` 时报 `unexpected keyword argument 'alias'` 的问题：现在自动改写为 `aliases=[...]`，兼容 **set / list / 单个字符串** 三种写法，同时把 `desc=` 改写为 `description=`
- 修复导入兜底正则在替换循环内重复执行的问题（移出循环，仅执行一次）

### 已知问题

- `PluginHarness` 在 `session_waiter` 场景下存在分发问题（上游 Issue #32）
- 仅支持 macOS，Windows / Linux 未验证
- 仅支持文本消息，富媒体与事件按钮尚未实现
- 假 LLM 固定回复，不解析 `system_prompt`，不真正判断内容
- 复杂装饰器写法（多行装饰器、位置参数、动态构造参数）可能转换失败
- 插件运行时会在工作目录生成数据文件（如 `fortune_data.json`），暂无独立数据目录隔离


## [0.1.0-alpha.2] - 2026-11-07

### 新增

- **假 LLM**：`FakeContext.llm_generate(...)` 返回固定格式的模拟回复，不调用真实 API、不消耗 token。后端日志显示被调用的 `provider_id` 和 `prompt` 预览。
- **插件切换**：UI 顶部下拉 + 插件列表卡片，点击后后端自动卸载当前插件、加载新插件。切换前弹出确认框“会终止当前测试”。
- **侧边栏布局**：左侧 200px 宽导航，包含「测试」「插件列表」「设置」三个视图。
- **主题切换**：深色 / 亮色两套主题，选择记忆到 `localStorage`。
- **日志面板升级**：
  - 级别：DEBUG / INFO / WARNING / ERROR 四级过滤
  - 颜色区分：DEBUG 灰、INFO 浅灰、WARNING 黄、ERROR 红（暗色 / 亮色都适配）
  - 级别选择记忆到 `localStorage`
  - 后端接入 `loguru` sink，捕获 SDK 内部 DEBUG 日志
- **全局配置**：`bundled/config.json` 控制端口、日志轮询间隔、最大日志行数、默认插件。
- **新增 API**：`GET /api/config`、`GET /api/plugins`、`POST /api/plugins/switch`。

### 改进

- **插件格式转换增强**：
  - 删除 `__init__`，初始化逻辑整体搬到 `async def on_start(self, ctx=None)`
  - `Star.context` property 补丁，允许实例设置 `self.context`
  - `event.get_sender_name()` 等 6 个方法自动替换为属性访问
  - `logger` / `AstrBotConfig` / `message_components` 用内联 stub 替换
  - `message_components` 的 stub 改用 `__new__`，避免被 `__init__` 移除逻辑误伤
- **`astrbot.*` 兼容层**：`sys.meta_path` finder 兜底未覆盖的导入，映射到 `astrbot_sdk.*`，找不到则返回 stub 对象
- **版本号单一来源**：`version.py` 为唯一来源，`config.json` 里的 `version` 字段被忽略，`/api/config` 返回的版本号强制来自 `version.py`

### 修复

- 修复 `__init__` 移除逻辑的正则贪婪问题（会误删同级方法）
- 修复 `__init__` 移除逻辑误伤 `Star` 类之前定义的其他类（如内联 stub）的 `__init__`
- 修复 `Star.context` 只读 property 导致的 `AttributeError`
- 修复 `test_plugin` 的 `hello` 方法被误识别为 handler 候选的问题
- 修复 `on_start(ctx)` 被 SDK 传入真实 `Context` 导致 `llm_generate` 缺失的问题（改为强制使用 `FakeContext`）
- 修复前端 `escapeHtml` 缺失导致的 XSS 风险

### 已知问题

- `PluginHarness` 在 `session_waiter` 场景下存在分发问题（上游 Issue #32）
- 仅支持 macOS，Windows / Linux 未验证
- 仅支持文本消息，富媒体未实现
- 假 LLM 固定回复，不解析 `system_prompt`，不真正判断内容
- 嵌套类、动态导入、`MessageEventResult` 复杂用法可能转换失败
- 插件切换时日志面板会清空，切换前的历史不保留


## [0.1.0-alpha.1] - 2026-10-31

### 新增
- 初始 MVP，支持加载 AstrBot 插件
- 基于 `PluginHarness` 模拟文本消息，显示插件回复
- 自动转换 v3 插件格式（`metadata.yaml` + `main.py`）到 SDK 可加载的格式
- 自动生成 `plugin.yaml`，检测插件主类
- 自动重写 v3 API 导入和装饰器到 SDK 兼容写法

### 已知问题
- `PluginHarness` 在 session waiter 场景下存在分发问题（上游 Issue #32）
- 仅支持 macOS
- 仅支持文本消息，事件按钮、配置界面、热重载尚未实现