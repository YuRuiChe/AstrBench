import asyncio
import re
import shutil
import sys
import tempfile
from pathlib import Path

import yaml
from astrbot_sdk.testing import PluginHarness

# ==================== 配置区 ====================

SOURCE_PLUGIN_DIR = Path("./bundled/plugins/test_plugin")
TEST_MESSAGE = "/hello"


# ==================== 插件格式转换 ====================

def convert_plugin_to_sdk(src_dir: Path, dst_dir: Path) -> None:
    shutil.copytree(src_dir, dst_dir)
    _generate_plugin_yaml(src_dir, dst_dir)
    _rewrite_python_files(dst_dir)


def _generate_plugin_yaml(src_dir: Path, dst_dir: Path) -> None:
    metadata_path = src_dir / "metadata.yaml"
    if not metadata_path.exists():
        raise FileNotFoundError(f"缺少 metadata.yaml：{metadata_path}")

    with open(metadata_path, "r", encoding="utf-8") as f:
        meta = yaml.safe_load(f) or {}

    class_name = _detect_plugin_class(dst_dir / "main.py")
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"

    plugin_yaml = {
        **meta,
        "runtime": {"python": python_version},
        "components": [{"class": f"main:{class_name}"}],
    }

    with open(dst_dir / "plugin.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(plugin_yaml, f, allow_unicode=True, sort_keys=False)


def _detect_plugin_class(main_py: Path) -> str:
    if not main_py.exists():
        return "TestPlugin"
    text = main_py.read_text(encoding="utf-8")
    match = re.search(r"class\s+(\w+)\s*\(\s*Star\b", text)
    if match:
        return match.group(1)
    return "TestPlugin"


def _rewrite_python_files(plugin_dir: Path) -> None:
    for py_file in plugin_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        text = _rewrite_imports(text)
        text = _rewrite_decorators(text)
        text = _remove_legacy_init(text)      # 按缩进精确删除
        text = _ensure_on_start(text)         # 补上 on_start 占位
        py_file.write_text(text, encoding="utf-8")


def _rewrite_imports(text: str) -> str:
    text = text.replace(
        "from astrbot.api.star import Star, Context",
        "from astrbot_sdk import Star, Context",
    )
    text = text.replace(
        "from astrbot.api.event import filter, AstrMessageEvent",
        "from astrbot_sdk import MessageEvent\nfrom astrbot_sdk.decorators import on_command, on_message",
    )
    text = text.replace(
        "from astrbot.api.star import Context, Star, register",
        "from astrbot_sdk import Star, Context",
    )
    text = text.replace(
        "from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult",
        "from astrbot_sdk import MessageEvent\nfrom astrbot_sdk.decorators import on_command, on_message",
    )
    return text


def _rewrite_decorators(text: str) -> str:
    text = re.sub(
        r'@filter\.command\(([^)]+)\)',
        r'@on_command(\1)',
        text,
    )
    text = re.sub(
        r'@filter\.on_event\([^)]*\)',
        r'@on_message()',
        text,
    )
    text = text.replace("AstrMessageEvent", "MessageEvent")
    text = re.sub(
        r'yield\s+event\.plain_result\(([^)]*)\)',
        r'await event.reply(\1)',
        text,
    )
    return text


def _remove_legacy_init(text: str) -> str:
    """按缩进层级精确删除 __init__ 方法，不影响同级方法。"""
    lines = text.split("\n")
    result = []
    in_init = False
    init_indent = 0

    for line in lines:
        stripped = line.lstrip()
        current_indent = len(line) - len(stripped)

        if re.match(r"\s*def\s+__init__\s*\(", line):
            in_init = True
            init_indent = current_indent
            continue  # 跳过 def __init__ 这一行

        if in_init:
            # 空行，或比 __init__ 缩进更深，都属于 __init__ 方法体
            if stripped == "" or current_indent > init_indent:
                continue
            else:
                # 遇到同级或更浅的缩进，__init__ 结束
                in_init = False
                result.append(line)
        else:
            result.append(line)

    return "\n".join(result)


def _ensure_on_start(text: str) -> str:
    """如果类里没有 on_start，就在类体开头补一个。"""
    if "on_start" in text:
        return text

    class_match = re.search(r"class\s+\w+\s*\(\s*Star\b[^)]*\)\s*:", text)
    if not class_match:
        return text

    insert_pos = class_match.end()
    on_start_snippet = (
        "\n    async def on_start(self, ctx: Context = None):\n"
        "        \"\"\"v4 SDK 生命周期入口，插件启动时调用。\"\"\"\n"
        "        pass\n"
    )
    return text[:insert_pos] + on_start_snippet + text[insert_pos:]


# ==================== 主流程 ====================

async def main():
    if not SOURCE_PLUGIN_DIR.exists():
        print(f"[AstrBench] 插件目录不存在：{SOURCE_PLUGIN_DIR}")
        return

    tmp_dir = Path(tempfile.mkdtemp(prefix="astrbench_"))
    tmp_plugin_dir = tmp_dir / "plugin"

    try:
        print(f"[AstrBench] 正在转换插件：{SOURCE_PLUGIN_DIR} → {tmp_plugin_dir}")
        convert_plugin_to_sdk(SOURCE_PLUGIN_DIR, tmp_plugin_dir)

        async with PluginHarness.from_plugin_dir(str(tmp_plugin_dir)) as harness:
            records = await harness.dispatch_text(TEST_MESSAGE)
            for r in records:
                print(f"[插件回复] {r.text}")

    except Exception as e:
        print(f"[AstrBench] 测试失败：{e}")
        raise

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"[AstrBench] 已清理临时目录：{tmp_dir}")


if __name__ == "__main__":
    asyncio.run(main())