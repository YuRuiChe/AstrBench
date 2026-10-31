# 更新日志

本文件记录 AstrBench 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

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