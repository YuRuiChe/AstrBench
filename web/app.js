const chatLog = document.getElementById("chat-log");
const msgInput = document.getElementById("msg-input");
const sendBtn = document.getElementById("send-btn");
const versionEl = document.getElementById("version");
const themeToggle = document.getElementById("theme-toggle");
const themeSelect = document.getElementById("theme-select");
const pluginSelect = document.getElementById("plugin-select");
const pluginList = document.getElementById("plugin-list");
const pollIntervalInfo = document.getElementById("poll-interval-info");
const configPathEl = document.getElementById("config-path");
const logViewEl = document.getElementById("log-view");
const logLevelSelect = document.getElementById("log-level-select");

let logTimer = null;
let currentPlugin = null;
let pluginsData = [];
let pollInterval = 2000;

// ==================== 主题 ====================

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  themeToggle.textContent = theme === "dark" ? "暗色" : "亮色";
  if (themeSelect) themeSelect.value = theme;
}

function setupTheme() {
  const saved = localStorage.getItem("astrbench-theme");
  const prefersLight = window.matchMedia("(prefers-color-scheme: light)").matches;
  const theme = saved || (prefersLight ? "light" : "dark");
  applyTheme(theme);

  themeToggle.addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") || "dark";
    const next = cur === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem("astrbench-theme", next);
  });

  themeSelect.addEventListener("change", (e) => {
    applyTheme(e.target.value);
    localStorage.setItem("astrbench-theme", e.target.value);
  });
}

// ==================== 视图切换 ====================

function setupViewNav() {
  document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", (e) => {
      e.preventDefault();
      document.querySelectorAll(".nav-item").forEach(i => i.classList.remove("active"));
      item.classList.add("active");
      const view = item.dataset.view;
      document.querySelectorAll(".view").forEach(v => v.hidden = true);
      const el = document.getElementById(`view-${view}`);
      if (el) el.hidden = false;
    });
  });
}

// ==================== 配置 ====================

async function loadGlobalConfig() {
  try {
    const resp = await fetch("/api/config");
    const cfg = await resp.json();
    if (versionEl && cfg.version) {
      versionEl.textContent = `${cfg.version}`;
    }
    pollInterval = cfg?.log?.poll_interval_ms ?? 2000;
    if (pollIntervalInfo) {
      pollIntervalInfo.textContent = `${pollInterval} ms`;
    }
    if (configPathEl && cfg.config_path) {
      configPathEl.textContent = cfg.config_path;
    }
  } catch (e) {
    if (versionEl) versionEl.textContent = "(配置读取失败)";
  }
}

// ==================== 插件列表 ====================

async function loadPlugins() {
  try {
    const resp = await fetch("/api/plugins");
    const data = await resp.json();
    pluginsData = data.plugins || [];
    currentPlugin = data.current;
    renderPluginSelect();
    renderPluginList();
  } catch (e) {
    console.error("加载插件列表失败:", e);
  }
}

function renderPluginSelect() {
  pluginSelect.innerHTML = "";
  if (pluginsData.length === 0) {
    const opt = document.createElement("option");
    opt.textContent = "(无插件)";
    pluginSelect.appendChild(opt);
    return;
  }
  for (const p of pluginsData) {
    const opt = document.createElement("option");
    opt.value = p.name;
    opt.textContent = p.display_name || p.name;
    if (p.name === currentPlugin) opt.selected = true;
    pluginSelect.appendChild(opt);
  }
}

function renderPluginList() {
  pluginList.innerHTML = "";
  if (pluginsData.length === 0) {
    pluginList.textContent = "没有可用插件";
    return;
  }
  for (const p of pluginsData) {
    const card = document.createElement("div");
    card.className = "plugin-card" + (p.name === currentPlugin ? " active" : "");
    card.innerHTML = `
      <div class="plugin-name">${escapeHtml(p.display_name || p.name)}</div>
      <div class="plugin-desc">${escapeHtml(p.desc || "")}</div>
      <div class="plugin-version">v${escapeHtml(p.version || "?")}${p.name === currentPlugin ? " · 当前" : ""}</div>
    `;
    card.addEventListener("click", () => switchPlugin(p.name));
    pluginList.appendChild(card);
  }
}

function setupPluginSelect() {
  pluginSelect.addEventListener("change", async (e) => {
    const newPlugin = e.target.value;
    if (newPlugin === currentPlugin) return;
    if (!confirm(`切换插件会终止当前测试，是否继续？\n\n新插件：${newPlugin}`)) {
      e.target.value = currentPlugin;
      return;
    }
    await switchPlugin(newPlugin);
  });
}

async function switchPlugin(name) {
  if (!name || name === currentPlugin) return;
  pluginSelect.disabled = true;
  appendMessage("bot", `[切换中] 正在加载插件：${name}...`);
  try {
    const resp = await fetch("/api/plugins/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await resp.json();
    if (data.error) {
      appendMessage("bot", `[切换失败] ${data.error}`);
      return;
    }
    currentPlugin = data.current;
    chatLog.innerHTML = "";
    appendMessage("bot", `已切换到插件：${name}`);
    renderPluginSelect();
    renderPluginList();
    LogViewer.clear();       // ← 清空日志组件
    await LogViewer.poll();  // ← 立即拉一次
  } catch (e) {
    appendMessage("bot", `[切换请求失败] ${e}`);
  } finally {
    pluginSelect.disabled = false;
  }
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = String(s || "");
  return div.innerHTML;
}

// ==================== 聊天 ====================

function appendMessage(who, text) {
  const div = document.createElement("div");
  div.className = `msg ${who}`;
  div.innerHTML = `<div class="who">${who === "user" ? "输入" : "输出"}</div>
                   <div class="body"></div>`;
  div.querySelector(".body").textContent = text;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
}

async function send() {
  const text = msgInput.value.trim();
  if (!text) return;

  appendMessage("user", text);
  msgInput.value = "";
  sendBtn.disabled = true;

  try {
    const resp = await fetch("/api/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await resp.json();
    if (data.error) {
      appendMessage("bot", `[错误] ${data.error}`);
    } else {
      for (const r of data.replies || []) {
        appendMessage("bot", r.text || "(空回复)");
      }
    }
  } catch (e) {
    appendMessage("bot", `[请求失败] ${e}`);
  } finally {
    sendBtn.disabled = false;
    msgInput.focus();
  }
}

function setupSend() {
  sendBtn.addEventListener("click", send);
  msgInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") send();
  });
}

// ==================== 日志轮询（委托给 LogViewer） ====================

function startLogPolling() {
  if (logTimer) clearInterval(logTimer);
  LogViewer.poll();                                        // 立即拉一次
  logTimer = setInterval(() => LogViewer.poll(), pollInterval);  // 之后按配置间隔
}

// ==================== 初始化 ====================

async function init() {
  setupTheme();
  setupViewNav();
  setupSend();
  setupPluginSelect();
  LogViewer.init(logViewEl, logLevelSelect);   // ← 初始化日志组件
  await loadGlobalConfig();
  await loadPlugins();
  startLogPolling();
  msgInput.focus();
}

init();