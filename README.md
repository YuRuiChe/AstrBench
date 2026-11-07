# AstrBench

> AstrBench 是一个面向 AstrBot 插件开发者的便携式调试软件。基于 AstrBot SDK 的 PluginHarness 构建，在本地模拟完整消息平台环境，让开发者在不需要部署 AstrBot、不需要接入真实平台的情况下，测试插件的全部逻辑
> 功能尚不完整，欢迎试用和反馈

## 功能

- 加载 AstrBot 插件（自动转换 v3 插件格式到 SDK 可加载的格式）
- 模拟文本消息，查看插件回复
- 基于官方 `PluginHarness`，测试行为与生产环境一致

## 安装

下载相应版本的 zip 文件并解压


## 开发

### 环境要求

- Python 3.12+

### 本地运行

当前为预发布版，暂未提供打包产物，请从源码运行：

```bash
git clone https://github.com/YuRuiChe/AstrBench.git
cd AstrBench
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
python launcher.py
```