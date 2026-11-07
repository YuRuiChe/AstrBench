"""
启动流程：
1. 读取 bundled/config.json
2. 启动 asyncio 事件循环（子线程）
3. 加载默认插件（转换 AstrBot 格式 → SDK 格式）
4. 启动 Flask 服务（子线程），静态文件直接从 bundled/web 提供
5. 打开 PyWebView 窗口（主线程）
"""

import asyncio
import atexit
import importlib
import importlib.abc
import importlib.machinery
from loguru import logger as _loguru
import json
import re
import shutil
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

import yaml
from flask import Flask, jsonify, request, send_from_directory
import webview
from astrbot_sdk.testing import PluginHarness

from version import __version__

# ==================== AstrBot 兼容层 ====================
# 插件加载时如果还有残留的 `import astrbot.xxx`，这里会自动：
#   1) 尝试 astrbot_sdk.xxx 里的同名模块
#   2) 找不到就返回一个 stub（任何属性访问都不会崩）
# 这样即使字符串替换漏掉了某个导入，也不会直接 ModuleNotFoundError。


class _Stub:
    """万能占位对象：可调用、可取属性、可迭代，一律返回自身或空。"""

    def __init__(self, *a, **kw):
        pass

    def __call__(self, *a, **kw):
        return _Stub()

    def __getattr__(self, name):
        # 双下划线属性（如 __wrapped__）抛出 AttributeError，
        # 避免破坏 inspect / abc 等库的探测逻辑
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _Stub()

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False

    def __repr__(self):
        return "<AstrBot stub>"


class _AstrBotCompatLoader(importlib.abc.Loader):
    """处理 astrbot.* 的加载：优先映射到 astrbot_sdk，失败则给 stub。"""

    def __init__(self, fullname: str):
        self.fullname = fullname

    def create_module(self, spec):
        parts = self.fullname.split(".")

        # 候选模块名列表，按优先级尝试
        candidates = []
        if len(parts) > 2 and parts[1] in ("api", "core"):
            # astrbot.api.star → astrbot_sdk.star
            candidates.append("astrbot_sdk." + ".".join(parts[2:]))
            candidates.append("astrbot_sdk")
        # astrbot.star → astrbot_sdk.star
        candidates.append("astrbot_sdk." + ".".join(parts[1:]))
        candidates.append("astrbot_sdk")

        for name in candidates:
            try:
                return importlib.import_module(name)
            except ImportError:
                continue

        # 全部失败 → 返回一个 stub 模块，任何属性访问都返回 _Stub
        mod = types.ModuleType(self.fullname)

        def _module_getattr(name):
            if name.startswith("__") and name.endswith("__"):
                raise AttributeError(name)
            return _Stub()

        mod.__getattr__ = _module_getattr
        return mod

    def exec_module(self, module):
        # 模块已由 create_module 构造，无需额外执行
        pass


class _AstrBotCompatFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        # 放行真实的 astrbot_sdk 包，不拦截
        if fullname == "astrbot_sdk" or fullname.startswith("astrbot_sdk."):
            return None
        # 只拦截 astrbot.*
        if fullname == "astrbot" or fullname.startswith("astrbot."):
            return importlib.machinery.ModuleSpec(
                fullname, _AstrBotCompatLoader(fullname)
            )
        return None


# 插到 meta_path 最前面，保证优先于真实导入
sys.meta_path.insert(0, _AstrBotCompatFinder())

# ==================== AstrBench 运行时 stubs ====================
# 给转换后的插件提供一个假的 Context，让 self.context.llm_generate(...) 能调。

_stubs = types.ModuleType("astrbench_stubs")


class _FakeLLMResponse:
    """模拟 llm_generate 的返回值，只提供 completion_text。"""

    def __init__(self, text: str):
        self.completion_text = text


class FakeContext:
    """假的 Context，提供 llm_generate 等常用方法。"""

    async def llm_generate(
        self,
        chat_provider_id=None,
        prompt="",
        system_prompt="",
        **kwargs,
    ):
        """假 LLM：返回固定格式的回复，并把 prompt 回显一段。"""
        preview = (prompt or "")[:100]
        sys_preview = (system_prompt or "")[:80]
        text = (
            f"[MockLLM 假回复]\n"
            f"provider_id: {chat_provider_id or '(未指定)'}\n"
            f"用户输入: {preview}\n"
            f"系统提示: {sys_preview}...\n"
            f"判定：没有违反群规。"
        )
        _loguru.debug(
            f"[MockLLM] 被调用 provider={chat_provider_id} prompt={preview[:30]}"
        )
        return _FakeLLMResponse(text)

    async def llm_generate_stream(self, *a, **kw):
        raise NotImplementedError("暂未实现流式")

    def __getattr__(self, name):
        # 其他未知方法返回一个异步空函数，避免 AttributeError
        async def _noop(*a, **kw):
            return None

        return _noop


_stubs.FakeContext = FakeContext
_stubs._FakeLLMResponse = _FakeLLMResponse
sys.modules["astrbench_stubs"] = _stubs
try:
    from astrbot_sdk import Star as _Star

    if isinstance(getattr(_Star, "context", None), property):
        _Star.context = None  # 用普通属性覆盖 property
        _loguru.debug("[补丁] Star.context property 已被覆盖为可写属性")
except Exception as e:
    _loguru.warning(f"[补丁] Star.context 覆盖失败：{e}")

# ==================== 路径 ====================

APP_NAME = "AstrBench"

if getattr(sys, "frozen", False):
    # PyInstaller 打包后，资源在临时解压目录
    BUNDLED_DIR = Path(sys._MEIPASS)
else:
    # 开发模式：launcher.py 同级的 bundled/
    BUNDLED_DIR = Path(__file__).parent / "bundled"

WEB_DIR = BUNDLED_DIR / "web"
CONFIG_FILE = BUNDLED_DIR / "config.json"
PLUGINS_DIR = BUNDLED_DIR / "plugins"

# ==================== 全局配置 ====================


def load_config() -> dict:
    """读取 config.json，与默认值做浅合并，version 强制来自 version.py。"""
    defaults = {
        "default_plugin": "test_plugin",
        "server": {"host": "127.0.0.1", "port": 5001},
        "log": {"max_lines": 500, "poll_interval_ms": 2000},
    }
    if not CONFIG_FILE.exists():
        data = {}
    else:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    merged = {**defaults, **data}
    # 嵌套字段单独合并，避免用户只改一半时丢失默认值
    merged["server"] = {**defaults["server"], **data.get("server", {})}
    merged["log"] = {**defaults["log"], **data.get("log", {})}
    # 【关键】版本号只来自 version.py，覆盖 config.json 里可能残留的 version
    merged["version"] = __version__
    merged["config_path"] = str(CONFIG_FILE)
    return merged


CONFIG = load_config()
SERVER_HOST = CONFIG["server"]["host"]
SERVER_PORT = CONFIG["server"]["port"]
MAX_LOG_LINES = CONFIG["log"]["max_lines"]

# ==================== 日志缓冲 ====================


class LogBuffer:
    """线程安全的环形日志缓冲，每条带级别。"""

    def __init__(self, max_lines: int = 500):
        self.lines: list[dict] = []          # ← 从 str 改成 dict
        self.max_lines = max_lines
        self.lock = threading.Lock()

    def add(self, text: str, level: str = "INFO") -> None:
        with self.lock:
            self.lines.append({
                "text": text,
                "level": level.upper(),
            })
            if len(self.lines) > self.max_lines:
                self.lines = self.lines[-self.max_lines:]

    def get(self) -> list[dict]:
        with self.lock:
            return list(self.lines)


log_buffer = LogBuffer(max_lines=MAX_LOG_LINES)


# 把 loguru 的日志接入 log_buffer
def _loguru_sink(message) -> None:
    record = message.record
    level = record["level"].name
    ts = record["time"].strftime("%H:%M:%S.%f")[:-3]
    module = record["name"].split(".")[-1] if record["name"] else "?"
    text = f"{ts} | {level:<8} | {module}:{record['function']} - {record['message']}"
    log_buffer.add(text, level=level)


# 添加 sink，最低级别 DEBUG，这样 debug 日志也能被捕获
_loguru.add(_loguru_sink, level="DEBUG")

# ==================== 插件格式转换 ====================


def convert_plugin_to_sdk(src_dir: Path, dst_dir: Path) -> None:
    """三步：复制 → 生成 plugin.yaml → 重写 py 文件。"""
    shutil.copytree(src_dir, dst_dir)
    _generate_plugin_yaml(src_dir, dst_dir)
    _rewrite_python_files(dst_dir)


def _generate_plugin_yaml(src_dir: Path, dst_dir: Path) -> None:
    """从 metadata.yaml 生成 SDK 要求的 plugin.yaml。

    SDK 强制要求 runtime.python 和 components，缺一不可。
    components 必须是对象列表，不能是字符串。
    """
    metadata_path = src_dir / "metadata.yaml"
    if not metadata_path.exists():
        raise FileNotFoundError(f"缺少 metadata.yaml：{metadata_path}")

    with open(metadata_path, "r", encoding="utf-8") as f:
        meta = yaml.safe_load(f) or {}

    class_name = _detect_plugin_class(dst_dir / "main.py")
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"

    plugin_yaml = {
        **meta,  # 继承 metadata 全部字段
        "runtime": {"python": python_version},
        "components": [{"class": f"main:{class_name}"}],
    }

    with open(dst_dir / "plugin.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(plugin_yaml, f, allow_unicode=True, sort_keys=False)


def _detect_plugin_class(main_py: Path) -> str:
    """从 main.py 找第一个 class XXX(Star) 的类名。"""
    if not main_py.exists():
        return "TestPlugin"
    text = main_py.read_text(encoding="utf-8")
    match = re.search(r"class\s+(\w+)\s*\(\s*Star\b", text)
    return match.group(1) if match else "TestPlugin"


def _rewrite_python_files(plugin_dir: Path) -> None:
    """对每个 .py 文件依次做四步转换。顺序不能乱。"""
    for py_file in plugin_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        text = _rewrite_imports(text)
        text = _rewrite_decorators(text)
        text = _remove_legacy_init(text)
        py_file.write_text(text, encoding="utf-8")


def _rewrite_imports(text: str) -> str:
    """把 astrbot.api.* 导入换到 astrbot_sdk.*。

    对于确定能映射的（Star / Context / MessageEvent / 装饰器），直接替换。
    对于不确定的（logger / AstrBotConfig / message_components），
    用内联 stub 替换，避免依赖 astrbot_sdk 里是否导出这些名字。
    """
    replacements = [
        # === 确定能映射的 ===
        ("from astrbot.api.star import Star, Context",
         "from astrbot_sdk import Star, Context"),
        ("from astrbot.api.star import Context, Star, register",
         "from astrbot_sdk import Star, Context"),
        ("from astrbot.api.event import filter, AstrMessageEvent",
         "from astrbot_sdk import MessageEvent\n"
         "from astrbot_sdk.decorators import on_command, on_message"),
        ("from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult",
         "from astrbot_sdk import MessageEvent\n"
         "from astrbot_sdk.decorators import on_command, on_message"),

        # === 不确定的，用内联 stub 替换 ===
        # logger：直接用标准 logging，日志会打到终端 stderr
        ("from astrbot.api import logger",
         "import logging as _astrbench_logging\n"
         "logger = _astrbench_logging.getLogger('astrbot.plugin')"),

        # AstrBotConfig：用 dict 顶替，config.get(...) 能正常返回默认值
        ("from astrbot.core import AstrBotConfig",
         "AstrBotConfig = dict"),

        # message_components：内联 stub 类，可调用、可实例化
        # 注意：用 __new__ 而非 __init__，避免被 _remove_legacy_init 误伤
        ("from astrbot.api.message_components import At, Plain",
         "class _AstrBenchMsgStub:\n"
         "    def __new__(cls, *args, **kwargs):\n"
         "        obj = object.__new__(cls)\n"
         "        obj.args = args\n"
         "        obj.kwargs = kwargs\n"
         "        return obj\n"
         "    def __repr__(self):\n"
         "        return '<AstrBenchMsgStub>'\n"
         "At = _AstrBenchMsgStub\n"
         "Plain = _AstrBenchMsgStub"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def     _rewrite_decorators(text: str) -> str:
    """替换装饰器、事件类型、yield 返回、@register。"""
    # @filter.command("x") → @on_command("x")
    text = re.sub(r'@filter\.command\(([^)]+)\)', r'@on_command(\1)', text)
    # @filter.on_event(...) → @on_message()
    text = re.sub(r'@filter\.on_event\([^)]*\)', r'@on_message()', text)
    # AstrMessageEvent → MessageEvent
    text = text.replace("AstrMessageEvent", "MessageEvent")
    # yield event.plain_result(...) → await event.reply(...)
    text = re.sub(
        r'yield\s+event\.plain_result\(([^)]*)\)',
        r'await event.reply(\1)',
        text,
    )
    # 移除 @register(...) 装饰器（SDK 不需要）
    text = re.sub(r'@register\([^)]*\)\s*\n', '', text)
    # event.get_xxx() → event.xxx（SDK 用属性，不是方法）
    event_method_map = {
        "get_sender_name": "sender_name",
        "get_sender_id": "sender_id",
        "get_group_id": "group_id",
        "get_session_id": "session_id",
        "get_message_str": "message_str",
        "get_message_id": "message_id",
    }
    for method, attr in event_method_map.items():
        text = re.sub(rf'\bevent\.{method}\(\)', f'event.{attr}', text)
    return text


def _remove_legacy_init(text: str) -> str:
    """删除 Star 子类的 __init__，把初始化逻辑搬到 on_start。
    只处理 Star 子类的 __init__，嵌套类或其他类的 __init__ 不动。
    """
    lines = text.split("\n")

    # 第一步：找 Star 子类的位置和缩进
    star_indent = None
    star_line_idx = None
    for i, line in enumerate(lines):
        m = re.match(r"(\s*)class\s+\w+\s*\(\s*Star\b", line)
        if m:
            star_indent = len(m.group(1))
            star_line_idx = i
            break

    if star_indent is None:
        return text

    init_indent = star_indent + 4     # __init__ 必须和类体缩进一致
    in_init = False
    init_body = []
    init_body_indent = None
    found_init = False
    result = []
    class_left = False

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        current_indent = len(line) - len(stripped)

        # 判断是否已经离开 Star 类
        if i > star_line_idx and stripped and not stripped.startswith("#"):
            if current_indent <= star_indent and not re.match(r"\s*class\s+", line):
                class_left = True

       
        # 只在 Star 类内部、且缩进等于类方法缩进时，匹配 __init__
        # 注意 i > star_line_idx：确保只处理 Star 类之后的行
        # 避免误伤 Star 类之前定义的其他类的 __init__
        if i > star_line_idx and not class_left and not in_init:
            if re.match(rf"^\s{{{init_indent}}}def\s+__init__\s*\(", line):
                in_init = True
                found_init = True
                continue

        if in_init:
            if stripped == "" or current_indent > init_indent:
                if init_body_indent is None and stripped:
                    init_body_indent = current_indent
                init_body.append(line)
                continue
            else:
                in_init = False
                result.append(line)
        else:
            result.append(line)

    text = "\n".join(result)

    # 没找到 __init__ → 直接返回
    if not found_init:
        return text

    # 已有 on_start → 不重复生成
    if re.search(r"async\s+def\s+on_start\b", text):
        return text

    class_match = re.search(r"class\s+\w+\s*\(\s*Star\b[^)]*\)\s*:", text)
    if not class_match:
        return text

    # 转换 body 缩进：从原 init 缩进 → on_start 方法体缩进（8 空格）
    body_lines = []
    if init_body_indent is not None:
        for line in init_body:
            if line.strip() == "":
                body_lines.append("")
            else:
                rel = line[init_body_indent:]
                body_lines.append("        " + rel)

    # 清理：移除 super().__init__(...)，移除已有的 FakeContext 导入行
    cleaned = []
    for line in body_lines:
        if re.match(r"\s*super\(\)\.__init__\s*\(", line):
            continue
        if "from astrbench_stubs" in line:
            continue
        cleaned.append(line)

    # 检测 body 里是否已有 config 定义
    has_config = any(re.match(r"\s*config\s*=", line) for line in cleaned)

    # 拼装 on_start
    snippet_lines = ["", "    async def on_start(self, ctx=None):"]
    snippet_lines.append("        from astrbench_stubs import FakeContext")
    snippet_lines.append("        self.context = FakeContext()")
    if not has_config:
        snippet_lines.append("        config = {")
        snippet_lines.append('            "llm_provide": "mock",')
        snippet_lines.append(
            '            "is_regulations": "1、践行社会主义价值观 2、坚决不违反法律、道德与纪律",'
        )
        snippet_lines.append("        }")
    snippet_lines.extend(cleaned)
    if not cleaned:
        snippet_lines.append("        pass")
    snippet_lines.append("")

    insert_pos = class_match.end()
    snippet = "\n".join(snippet_lines)
    return text[:insert_pos] + snippet + text[insert_pos:]


def _ensure_on_start(text: str) -> str:
    """SDK v4 用 on_start(ctx) 做初始化，如果插件没有就补一个空占位。"""
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

# ==================== 引擎状态 ====================

_harness: PluginHarness | None = None
_loop: asyncio.AbstractEventLoop | None = None
_tmp_dir: Path | None = None
_current_plugin: str | None = None
_switch_lock = threading.Lock()


async def _dispatch_text(text: str):
    if _harness is None:
        raise RuntimeError("插件尚未加载")
    return await _harness.dispatch_text(text)


def _start_asyncio_loop() -> None:
    """在子线程里跑一个独立事件循环，供 harness 使用。"""
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_forever()


def _unload_current() -> None:
    """卸载当前插件，清理临时目录。"""
    global _harness, _tmp_dir, _current_plugin
    if _harness is not None and _loop is not None:
        try:
            asyncio.run_coroutine_threadsafe(
                _harness.__aexit__(None, None, None), _loop
            ).result(timeout=10)
        except Exception:
            pass
        _harness = None
    if _tmp_dir is not None:
        shutil.rmtree(_tmp_dir, ignore_errors=True)
        _tmp_dir = None
    _current_plugin = None


def _load_plugin(plugin_name: str) -> None:
    """转换并加载指定插件。调用前 _loop 必须已启动。"""
    global _harness, _tmp_dir, _current_plugin

    src = PLUGINS_DIR / plugin_name
    if not src.exists() or not src.is_dir():
        raise FileNotFoundError(f"插件不存在：{plugin_name}")

    # 每次加载都用独立的临时目录，避免两次加载互相污染
    _tmp_dir = Path(tempfile.mkdtemp(prefix="astrbench_"))
    tmp_plugin_dir = _tmp_dir / "plugin"
    convert_plugin_to_sdk(src, tmp_plugin_dir)

    async def _init():
        global _harness
        _harness = await PluginHarness.from_plugin_dir(
            str(tmp_plugin_dir)
        ).__aenter__()

    # 把协程丢进子线程的 loop 里执行，阻塞等结果
    asyncio.run_coroutine_threadsafe(_init(), _loop).result(timeout=30)
    _current_plugin = plugin_name


def _list_plugins() -> list[dict]:
    """扫描 bundled/plugins/，返回每个插件的元数据。"""
    result = []
    if not PLUGINS_DIR.exists():
        return result

    for d in sorted(PLUGINS_DIR.iterdir()):
        if not d.is_dir():
            continue

        metadata = d / "metadata.yaml"
        plugin_yaml = d / "plugin.yaml"

        info = {"name": d.name, "display_name": d.name, "desc": "", "version": ""}

        # metadata.yaml 优先，其次 plugin.yaml
        for f in (metadata, plugin_yaml):
            if f.exists():
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        meta = yaml.safe_load(fh) or {}
                    if meta.get("name"):
                        info["display_name"] = meta["name"]
                    if meta.get("display_name"):
                        info["display_name"] = meta["display_name"]
                    if meta.get("desc"):
                        info["desc"] = meta["desc"]
                    if meta.get("description"):
                        info["desc"] = meta["description"]
                    if meta.get("version") is not None:
                        info["version"] = str(meta["version"])
                    break
                except Exception:
                    pass

        result.append(info)

    return result

# ==================== Flask 服务 ====================

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    return send_from_directory(str(WEB_DIR), "index.html")


@app.route("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(str(WEB_DIR), filename)


@app.route("/api/config")
def api_config():
    return jsonify(CONFIG)


@app.route("/api/version")
def api_version():
    return jsonify({"version": __version__})


@app.route("/api/plugins")
def api_plugins():
    return jsonify({
        "plugins": _list_plugins(),
        "current": _current_plugin,
    })


@app.route("/api/plugins/switch", methods=["POST"])
def api_plugins_switch():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()

    if not name:
        return jsonify({"error": "缺少插件名"}), 400
    if name == _current_plugin:
        return jsonify({"ok": True, "current": _current_plugin})

    try:
        # _switch_lock 保证并发切换时不会互相打断
        with _switch_lock:
            log_buffer.add(f"[切换] 卸载 {_current_plugin} → 加载 {name}")
            _unload_current()
            _load_plugin(name)
        log_buffer.add(f"[切换] 当前插件：{name}")
        return jsonify({"ok": True, "current": name})
    except Exception as e:
        log_buffer.add(f"[ERROR] 切换插件失败：{e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/send", methods=["POST"])
def api_send():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"error": "消息为空"}), 400

    log_buffer.add(f"[UI] {text}")

    try:
        # Flask 线程 → 子线程 loop，阻塞等 harness 执行
        future = asyncio.run_coroutine_threadsafe(_dispatch_text(text), _loop)
        records = future.result(timeout=15)
    except Exception as e:
        log_buffer.add(f"[ERROR] {e}")
        return jsonify({"error": str(e)}), 500

    replies = []
    for r in records:
        reply_text = getattr(r, "text", "") or ""
        replies.append({"text": reply_text})
        log_buffer.add(f"[插件] {reply_text}")

    return jsonify({"replies": replies})


@app.route("/api/logs")
def api_logs():
    return jsonify({"lines": log_buffer.get()})


def _start_flask() -> None:
    # 关掉 werkzeug 的启动日志，避免刷屏
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app.run(
        host=SERVER_HOST,
        port=SERVER_PORT,
        debug=False,
        use_reloader=False,
    )

# ==================== 主流程 ====================


def _wait_for_flask(timeout: float = 10.0) -> bool:
    """轮询直到 Flask 能响应，或超时。"""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(
                f"http://{SERVER_HOST}:{SERVER_PORT}/", timeout=0.5
            )
            return True
        except Exception:
            time.sleep(0.1)
    return False


def _cleanup() -> None:
    _unload_current()


def main() -> None:
    log_buffer.add(f"[启动] AstrBench {__version__}")
    log_buffer.add(f"[启动] 配置：{CONFIG_FILE}")
    log_buffer.add(f"[启动] 前端：{WEB_DIR}")
    log_buffer.add(f"[启动] 插件目录：{PLUGINS_DIR}")

    # 1. 启动 asyncio loop（子线程）
    threading.Thread(target=_start_asyncio_loop, daemon=True).start()
    while _loop is None:
        time.sleep(0.01)

    # 2. 加载默认插件
    default_plugin = CONFIG.get("default_plugin", "test_plugin")
    try:
        _load_plugin(default_plugin)
        log_buffer.add(f"[启动] 插件加载完成：{default_plugin}")
    except Exception as e:
        log_buffer.add(f"[ERROR] 插件加载失败：{e}")
        raise

    # 3. 注册退出清理
    atexit.register(_cleanup)

    # 4. 启动 Flask（子线程）
    threading.Thread(target=_start_flask, daemon=True).start()
    if not _wait_for_flask():
        log_buffer.add("[ERROR] Flask 启动失败")
        raise SystemExit(1)
    log_buffer.add(f"[启动] Flask 已就绪：http://{SERVER_HOST}:{SERVER_PORT}")

    # 5. 打开窗口（主线程）
    webview.create_window(
        "AstrBench",
        f"http://{SERVER_HOST}:{SERVER_PORT}/",
        width=1200,
        height=780,
    )
    webview.start()


if __name__ == "__main__":
    main()