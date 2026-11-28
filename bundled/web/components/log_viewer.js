const LogViewer = (() => {
  let el = null;
  let levelSelect = null;
  let allLines = [];
  let lastCount = -1;
  let currentLevel = "info";

  // 级别权重：值越大越严重
  const LEVELS = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3 };

  function init(element, select, defaultLevel) {
    el = element;
    levelSelect = select;

    if (levelSelect) {
      levelSelect.addEventListener("change", (e) => setLevel(e.target.value));
    }

    // 完全以 config.json 的 ui.log_level 为准
    setLevel(defaultLevel || "info");
  }


  function setLevel(level) {
    currentLevel = (level || "info").toLowerCase();
    if (levelSelect) levelSelect.value = currentLevel;
    render();
  }
  function visibleLines() {
    const minLevel = LEVELS[currentLevel.toUpperCase()] ?? 1;
    return allLines.filter(item => {
      const lv = LEVELS[(item.level || "INFO").toUpperCase()] ?? 1;
      return lv >= minLevel;
    });
  }

  async function poll(url) {
    try {
      const resp = await fetch(url || "/api/logs");
      const data = await resp.json();
      const lines = data.lines || [];
      if (lines.length !== lastCount) {
        allLines = lines;
        lastCount = lines.length;
        render();
      }
    } catch (e) {
      // 静默忽略轮询错误
    }
  }

    function render() {
    if (!el) return;

    const filtered = visibleLines();

    if (filtered.length === 0) {
      el.innerHTML = `<div class="log-empty">（暂无日志）</div>`;
      return;
    }

    el.innerHTML = "";
    const frag = document.createDocumentFragment();
    for (const item of filtered) {
      const line = document.createElement("div");
      line.className = `log-line log-${(item.level || "info").toLowerCase()}`;
      line.textContent = item.text;
      frag.appendChild(line);
    }
    el.appendChild(frag);
    el.scrollTop = el.scrollHeight;
  }


  function clear() {
    allLines = [];
    lastCount = -1;
    render();
  }
    function getText() {
    return visibleLines().map(item => item.text).join("\n");
  }

  async function copyAll() {
    const text = getText();
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (_) {}
      ta.remove();
      return ok;
    }
  }

  async function saveAll() {
    const resp = await fetch("/api/logs/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lines: visibleLines() }),
    });
    return await resp.json();
  }

  return { init, poll, render, setLevel, clear, copyAll, saveAll, getText };

})();