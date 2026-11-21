const ConfigForm = (() => {
  // 本地 HTML 转义：不依赖 app.js 里的 escapeHtml，避免脚本加载顺序问题
  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = String(s || "");
    return div.innerHTML;
  }

  /** 按类型给出默认值（schema 没写 default 时用） */
  function getDefaultForType(type) {
    switch (type) {
      case "int": return 0;
      case "float": return 0.0;
      case "bool": return false;
      case "object": return {};
      case "list": return [];
      case "text": return "";
      default: return "";
    }
  }

  /**
   * 生成单个配置字段（一个 .config-field 块）
   * @param {string} key          配置项 key
   * @param {object} prop         schema 里该项的定义
   * @param {*} currentValue      已保存的当前值（可能 undefined）
   */
  function createField(key, prop, currentValue) {
    const div = document.createElement("div");
    div.className = "config-field";
    div.dataset.key = key;      // 保存时靠这个取 key

    const type = prop.type || "string";
    const defaultVal = prop.default !== undefined ? prop.default : getDefaultForType(type);
    const val = currentValue !== undefined ? currentValue : defaultVal;
    div.dataset.value = val;    // 保存时靠这个取值

    // 字段标题行：描述 + 提示 + 恢复默认按钮
    const header = document.createElement("div");
    header.className = "field-header";
    header.innerHTML = `
      <span class="field-label">${escapeHtml(prop.description || key)}</span>
      ${prop.hint ? `<span class="field-hint" title="${escapeHtml(prop.hint)}">❓</span>` : ""}
      <button class="field-reset" title="恢复默认值">↺</button>
    `;
    div.appendChild(header);

    const inputWrapper = document.createElement("div");
    inputWrapper.className = "field-input";

    // 根据类型生成不同控件
    if (type === "bool") {
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !!val;
      cb.onchange = () => div.dataset.value = cb.checked;
      inputWrapper.appendChild(cb);
    } else if (type === "int" || type === "float") {
      const inp = document.createElement("input");
      inp.type = "number";
      inp.value = val;
      if (type === "int") inp.step = "1";
      inp.oninput = () => div.dataset.value = inp.value;
      inputWrapper.appendChild(inp);
    } else if (prop.options) {
      // schema 里给了 options 就用下拉框
      const sel = document.createElement("select");
      prop.options.forEach(opt => {
        const o = document.createElement("option");
        o.value = opt;
        o.textContent = opt;
        if (opt == val) o.selected = true;
        sel.appendChild(o);
      });
      sel.onchange = () => div.dataset.value = sel.value;
      inputWrapper.appendChild(sel);
    } else if (type === "text") {
      const ta = document.createElement("textarea");
      ta.value = val;
      ta.rows = 4;
      ta.oninput = () => div.dataset.value = ta.value;
      inputWrapper.appendChild(ta);
    } else {
      // 兜底：普通文本框
      const inp = document.createElement("input");
      inp.type = "text";
      inp.value = val;
      inp.oninput = () => div.dataset.value = inp.value;
      inputWrapper.appendChild(inp);
    }
    div.appendChild(inputWrapper);

    // “恢复默认值”按钮
    header.querySelector(".field-reset").onclick = () => {
      const defVal = prop.default !== undefined ? prop.default : getDefaultForType(type);
      div.dataset.value = defVal;
      const ctrl = inputWrapper.querySelector("input, select, textarea");
      if (ctrl) {
        if (ctrl.type === "checkbox") ctrl.checked = !!defVal;
        else ctrl.value = defVal;
      }
    };

    return div;
  }

  /**
   * 打开配置弹窗（原 app.js 的 openConfigDialog）
   * @param {string} pluginName 插件目录名
   */
  async function open(pluginName) {
    const dialog = document.getElementById("dialog-config");
    dialog.querySelector(".dialog-title").textContent = `${pluginName} - 设置`;
    const body = dialog.querySelector(".dialog-body");
    const saveBtn = dialog.querySelector(".dialog-save");
    body.innerHTML = `<div class="loading">加载中...</div>`;
    dialog.showModal();

    try {
      const resp = await fetch(`/api/plugin/${encodeURIComponent(pluginName)}/config`);
      const { schema, config } = await resp.json();

      // 插件没有 _conf_schema.json
      if (!schema) {
        body.innerHTML = `<p class="muted">该插件没有提供 _conf_schema.json</p>`;
        saveBtn.disabled = true;
        return;
      }

      saveBtn.disabled = false;
      body.innerHTML = "";

      // 逐项生成字段
      const form = document.createElement("div");
      form.className = "config-form";
      for (const [key, prop] of Object.entries(schema)) {
        if (prop.invisible) continue;   // 跳过隐藏项
        form.appendChild(createField(key, prop, config[key]));
      }
      body.appendChild(form);

      // 保存：从每个 .config-field 收集 key/value
      saveBtn.onclick = async () => {
        const newConfig = {};
        form.querySelectorAll(".config-field").forEach(field => {
          newConfig[field.dataset.key] = field.dataset.value;
        });
        const r = await fetch(`/api/plugin/${encodeURIComponent(pluginName)}/config`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ config: newConfig }),
        });
        const result = await r.json();
        if (result.error) alert(`保存失败: ${result.error}`);
        else alert("保存成功");
        dialog.close();
      };
    } catch (err) {
      body.innerHTML = `<p class="error">加载失败: ${escapeHtml(String(err))}</p>`;
    }
  }

  // 对外暴露的 API
  return { open, createField, getDefaultForType };
})();
