const LogViewer = (() => {
  let el = null;
  let levelSelect = null;
  let allLines = [];
  let lastCount = -1;
  let currentLevel = "info";

  // 级别权重：值越大越严重
  const LEVELS = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3 };

  function init(element, select) {
    el = element;
    levelSelect = select;

    if (levelSelect) {
      levelSelect.addEventListener("change", (e) => setLevel(e.target.value));
    }

    const saved = localStorage.getItem("astrbench-log-level");
    setLevel(saved || "info");
  }

  function setLevel(level) {
    currentLevel = (level || "info").toLowerCase();
    localStorage.setItem("astrbench-log-level", currentLevel);
    if (levelSelect) levelSelect.value = currentLevel;
    render();
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

    const minLevel = LEVELS[currentLevel.toUpperCase()] ?? 1;
    const filtered = allLines.filter(item => {
      const lv = LEVELS[(item.level || "INFO").toUpperCase()] ?? 1;
      return lv >= minLevel;
    });

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

  return { init, poll, render, setLevel, clear };
})();