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
const welcomeEl = document.getElementById("welcome");
const chatActiveEl = document.getElementById("chat-active");
const homeBtn = document.getElementById("home-btn");

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

// ==================== 欢迎页 / 测试页切换 ====================

function updateChatView() {
  if (!currentPlugin) {
    welcomeEl.hidden = false;
    chatActiveEl.hidden = true;
    homeBtn.hidden = true;
  } else {
    welcomeEl.hidden = true;
    chatActiveEl.hidden = false;
    homeBtn.hidden = false;
  }
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
    currentPlugin = data.current || null;
    renderPluginSelect();
    renderPluginList();
    updateChatView();
  } catch (e) {
    console.error("加载插件列表失败:", e);
  }
}

function renderPluginSelect() {
  pluginSelect.innerHTML = "";
  if (pluginsData.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "(无插件)";
    pluginSelect.appendChild(opt);
    return;
  }
  // 无当前插件时，放一个占位项
  if (!currentPlugin) {
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "— 请选择插件 —";
    placeholder.selected = true;
    pluginSelect.appendChild(placeholder);
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
    // 当前激活的插件加 active 类
    card.className = "plugin-card" + (p.name === currentPlugin ? " active" : "");

    const logoSrc = p.logo || "/image/default_logo.svg";
    const logoHtml = `<img class="plugin-logo" src="${logoSrc}" alt="logo">`;

    // display_name 与目录名可能相同，相同时就只显示一个，避免重复
    const showId = p.display_name && p.display_name !== p.name;

    card.innerHTML = `
      <div class="plugin-card-main">
        ${logoHtml}
        <div class="plugin-info">
          <!-- 第一行：display_name + 版本号 -->
          <div class="plugin-title-row">
            <span class="plugin-name">${escapeHtml(p.display_name || p.name)}</span>
            <span class="plugin-version">v${escapeHtml(p.version || "?")}</span>
          </div>
          <!-- 第二行：描述，位于 logo 右侧 -->
          <div class="plugin-desc">${escapeHtml(p.desc || p.short_desc || "")}</div>
        </div>
      </div>
      <div class="plugin-actions">
        <button class="action-btn" data-plugin="${p.name}" data-action="readme" title="README">
          <img src="/image/readme.svg" alt="README">
        </button>
        <button class="action-btn" data-plugin="${p.name}" data-action="settings" title="设置">
          <img src="/image/settings.svg" alt="设置">
        </button>
        <button class="action-btn" data-plugin="${p.name}" data-action="action" title="行为">
          <img src="/image/action.svg" alt="行为">
        </button>
      </div>
    `;
    pluginList.appendChild(card);
  }
}

function setupPluginSelect() {
  pluginSelect.addEventListener("change", async (e) => {
    const newPlugin = e.target.value;
    if (!newPlugin || newPlugin === currentPlugin) return;

    let msg;
    if (currentPlugin) {
      msg = `切换插件会终止当前测试，是否继续？\n\n${currentPlugin} → ${newPlugin}`;
    } else {
      msg = `加载插件：${newPlugin}\n\n开始测试？`;
    }
    if (!confirm(msg)) {
      e.target.value = currentPlugin || "";
      return;
    }
    await switchPlugin(newPlugin);
  });
}

async function switchPlugin(name) {
  if (!name || name === currentPlugin) return;
  pluginSelect.disabled = true;
  try {
    const resp = await fetch("/api/plugins/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await resp.json();
    if (data.error) {
      alert(`切换失败：${data.error}`);
      renderPluginSelect();
      return;
    }
    currentPlugin = data.current;
    chatLog.innerHTML = "";
    appendMessage("bot", `已切换到插件：${name}`);
    updateChatView();
    renderPluginSelect();
    renderPluginList();
    LogViewer.clear();
    await LogViewer.poll();
  } catch (e) {
    alert(`切换请求失败：${e}`);
    renderPluginSelect();
  } finally {
    pluginSelect.disabled = false;
  }
}

async function goHome() {
  if (!currentPlugin) return;
  if (!confirm("切换回主页面会终止当前测试，是否继续？")) return;

  pluginSelect.disabled = true;
  try {
    const resp = await fetch("/api/plugins/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "" }),
    });
    const data = await resp.json();
    if (data.error) {
      alert(`失败：${data.error}`);
      return;
    }
    currentPlugin = null;
    chatLog.innerHTML = "";
    updateChatView();
    renderPluginSelect();
    renderPluginList();
    LogViewer.clear();
    await LogViewer.poll();
  } catch (e) {
    alert(`请求失败：${e}`);
  } finally {
    pluginSelect.disabled = false;
  }
}

function setupHomeBtn() {
  homeBtn.addEventListener("click", goHome);
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = String(s || "");
  return div.innerHTML;
}

// ==================== 测试 ====================

function appendMessage(who, text) {
  const div = document.createElement("div");
  div.className = `msg ${who}`;
  div.innerHTML = `<div class="who">${who === "user" ? "输入" : "插件输出"}</div>
                   <div class="body"></div>`;
  div.querySelector(".body").textContent = text;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
}

async function send() {
  const text = msgInput.value.trim();
  if (!text) return;
  if (!currentPlugin) {
    alert("请先选择插件");
    return;
  }

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
  LogViewer.poll();
  logTimer = setInterval(() => LogViewer.poll(), pollInterval);
}

// ==================== 插件详情弹窗 ====================

function setupPluginListActions() {
  pluginList.addEventListener("click", (e) => {
    const btn = e.target.closest(".action-btn");
    if (!btn) return;
    e.stopPropagation();
    const pluginName = btn.dataset.plugin;
    const action = btn.dataset.action;
    if (action === "readme") openReadmeDialog(pluginName);
    else if (action === "settings") ConfigForm.open(pluginName);  // 配置表单已拆分到 components/config_form.js
    else if (action === "action") openBehaviorsDialog(pluginName);

  });
}

function renderMarkdown(text) {
  if (window.marked) return window.marked.parse(text);
  // 无 marked 时的降级：纯文本
  const div = document.createElement("div");
  div.textContent = text;
  return `<pre style="white-space:pre-wrap">${div.innerHTML}</pre>`;
}

async function openReadmeDialog(pluginName) {
  const dialog = document.getElementById("dialog-readme");
  dialog.querySelector(".dialog-title").textContent = `${pluginName} - README`;
  const body = dialog.querySelector(".dialog-body");
  body.innerHTML = `<div class="loading">加载中...</div>`;
  dialog.showModal();
  try {
    const resp = await fetch(`/api/plugin/${encodeURIComponent(pluginName)}/readme`);
    const data = await resp.json();
    body.innerHTML = data.error
      ? `<p class="error">${escapeHtml(data.error)}</p>`
      : `<div class="markdown-body">${renderMarkdown(data.content)}</div>`;
  } catch (err) {
    body.innerHTML = `<p class="error">加载失败: ${escapeHtml(String(err))}</p>`;
  }
}

async function openBehaviorsDialog(pluginName) {
  const dialog = document.getElementById("dialog-behaviors");
  dialog.querySelector(".dialog-title").textContent = `${pluginName} - 行为`;
  const body = dialog.querySelector(".dialog-body");
  body.innerHTML = `<div class="loading">加载中...</div>`;
  dialog.showModal();
  try {
    const resp = await fetch(`/api/plugin/${encodeURIComponent(pluginName)}/behaviors`);
    const data = await resp.json();
    if (data.error) {
      body.innerHTML = `<p class="error">${escapeHtml(data.error)}</p>`;
    } else if (!data.behaviors || data.behaviors.length === 0) {
      body.innerHTML = `<p class="muted">该插件没有注册指令</p>`;
    } else {
      const list = document.createElement("div");
      list.className = "behavior-list";
      data.behaviors.forEach(b => {
        const item = document.createElement("div");
        item.className = "behavior-item";
        item.innerHTML = `<span class="behavior-type">${escapeHtml(b.type)}</span><code>/${escapeHtml(b.name)}</code>`;
        list.appendChild(item);
      });
      body.innerHTML = "";
      body.appendChild(list);
    }
  } catch (err) {
    body.innerHTML = `<p class="error">加载失败: ${escapeHtml(String(err))}</p>`;
  }
}

// ==================== 初始化 ====================

async function init() {
  setupTheme();
  setupViewNav();
  setupSend();
  setupPluginSelect();
  setupHomeBtn();
  setupPluginListActions();
  LogViewer.init(logViewEl, logLevelSelect);
  await loadGlobalConfig();
  await loadPlugins();
  startLogPolling();
  msgInput.focus();
}

init();