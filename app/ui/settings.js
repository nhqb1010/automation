// LEARN: YOU ARE HERE
//   shell.js (Settings clicked / ⌘,) ▶ THIS FILE draws the Settings page
//   from what preferences.py describes ▶ clicks are saved via bridge.py
//   read next → app/tools/system_monitor/ui/view.html

// The Settings page, built from each tool's settings model.
// LEARN: nothing here knows about any specific tool. Python describes each
// field (title, choices, current value) and this page draws a row of buttons
// for it, so a new tool gets its settings section for free.
//
//   bridge get_settings_sections ──▶ [ { tool_name, fields: [...] }, … ]
//                                          │
//                                          ▼
//   ┌ System Monitor ─────────── Reset ┐
//   │ Refresh      [1 s] [2 s] [5 s]   │   click ──▶ update_tool_preference
//   └──────────────────────────────────┘          ──▶ page redrawn
//
// LEARN: (() => { … })() = run once now, keep names private (see icons.js)
(() => {
  // let = can change later; set by mount, cleared by unmount
  let api = null;
  let root = null;
  // the own-usage card refreshes on its own timer while Settings is open
  let usageTimer = null;
  let lastUsage = null;
  // own-usage sparkline: fixed 0–10 % scale, so changes are comparable
  const USAGE_SCALE = { min: 0, max: 10 };
  const USAGE_REFRESH_MS = 2000;
  // what the switch shows for each login item state (from login_item.py)
  const LOGIN_ON_STATES = new Set(["on"]);

  // how one choice reads on its button: true → "On", 2 + "s" → "2s",
  // 300 with labels {"300": "5 min"} → "5 min"
  function formatChoice(value, unit, labels = {}) {
    // typeof x → the kind of value as text: "boolean", "number", "string", …
    if (typeof value === "boolean") return value ? "On" : "Off";
    // labels are keyed by text ("300"), so look the value up as text
    if (labels[String(value)]) return labels[String(value)];
    return unit ? `${value}${unit}` : String(value);
  }

  // one setting → one row of buttons (HTML text)
  // called by → renderSettingsSections
  function renderSettingRow(section, field) {
    // LEARN: each button carries what to save in data-… attributes
    //   JSON.stringify(2) → "2", (true) → "true" → read back with JSON.parse
    //   → the value keeps its type (number stays number, not text)
    //   the button matching the saved value gets class "on" (highlighted)
    const buttons = field.choices
      .map(
        (choice) =>
          `<button data-tool="${section.tool_id}" data-field="${field.name}" data-value='${JSON.stringify(choice)}'
             class="${choice === field.value ? "on" : ""}">${formatChoice(choice, field.unit, field.choice_labels)}</button>`,
      )
      .join("");
    return `<div class="setting-row">
      <div><div class="setting-title">${field.title}</div>
        ${field.description ? `<div class="setting-desc">${field.description}</div>` : ""}</div>
      <div class="segmented">${buttons}</div>
    </div>`;
  }

  // LEARN: the "App" card at the top: Open at login + the app's own usage
  //   login = { state, note } from bridge get_open_at_login
  //   state "unavailable" (dev copy) → buttons disabled, note says why
  //   the usage numbers are filled in later by renderAppUsage
  function renderAppSection(login) {
    const isOn = LOGIN_ON_STATES.has(login.state);
    const disabled = login.state === "unavailable" ? "disabled" : "";
    return `<section class="card settings-section">
      <div class="settings-section-head"><h2>App</h2></div>
      <div class="setting-row">
        <div><div class="setting-title">Open at login</div>
          <div class="setting-desc login-note"></div></div>
        <div class="segmented">
          <button data-login="false" class="${isOn ? "" : "on"}" ${disabled}>Off</button>
          <button data-login="true" class="${isOn ? "on" : ""}" ${disabled}>On</button>
        </div>
      </div>
      <div class="setting-row usage-row">
        <div class="usage-text">
          <div class="setting-title">This app's own usage</div>
          <div class="setting-desc">Change a refresh setting below, then watch this line within a minute.</div>
          <svg class="spark usage-spark"></svg>
          <div class="legend"><span>CPU, last 60 s · 0–10 %</span></div>
          <div class="setting-desc usage-note"></div>
        </div>
        <div class="usage-stats num">
          <div><b class="usage-cpu">—</b><span>CPU now</span></div>
          <div><b class="usage-avg">—</b><span>CPU avg</span></div>
          <div><b class="usage-memory">—</b><span>Memory</span></div>
        </div>
      </div>
    </section>`;
  }

  // fill the own-usage card with one reading (from bridge get_app_usage)
  // called by → the usage timer, and after each full redraw
  function renderAppUsage(usage) {
    if (!root || !usage) return;
    const C = window.BaoCharts;
    root.querySelector(".usage-cpu").textContent = `${usage.cpu_percent.toFixed(1)}%`;
    root.querySelector(".usage-avg").textContent = `${usage.cpu_average.toFixed(1)}%`;
    root.querySelector(".usage-memory").textContent = C.formatBytes(usage.memory_bytes, 0);
    C.drawSparkline(root.querySelector(".usage-spark"), usage.history, {
      ...USAGE_SCALE,
      color: "var(--accent)",
      slots: C.sparklineSlots(60, USAGE_REFRESH_MS / 1000),
    });
    root.querySelector(".usage-note").textContent = usage.includes_display_processes
      ? `Includes the window's drawing helpers (${usage.process_count} processes).`
      : "Counts the app's own code; the window-drawing helpers weren't found.";
  }

  // one usage reading; errors end up in the log via the shell
  async function refreshAppUsage() {
    const page = root;
    const usage = await api.get_app_usage();
    if (root !== page || !root) return;
    lastUsage = usage;
    renderAppUsage(usage);
  }

  function startUsageTimer() {
    if (usageTimer || !root) return;
    refreshAppUsage();
    usageTimer = setInterval(refreshAppUsage, USAGE_REFRESH_MS);
  }

  function stopUsageTimer() {
    clearInterval(usageTimer);
    usageTimer = null;
  }

  // the whole page: a heading, the App card, then one card per tool
  // called by → refreshSettingsPage
  // appInfo = { label, is_dev } from bridge get_app_info → the footer line
  function renderSettingsSections(sections, appInfo, login) {
    const I = window.BaoIcons;
    root.innerHTML = `
      <div class="page-head"><h1>Settings</h1><div class="meta">Changes apply immediately</div></div>
      ${renderAppSection(login)}
      ${sections
        .map(
          (section) => `<section class="card settings-section">
            <div class="settings-section-head">
              <h2>${section.tool_name}</h2>
              <button class="text-btn" data-reset="${section.tool_id}">${I.svg("reset", 13)} Reset to defaults</button>
            </div>
            ${section.fields.map((field) => renderSettingRow(section, field)).join("")}
          </section>`,
        )
        .join("")}
      <div class="settings-footer num"></div>`;
    // textContent → plain text, never markup
    root.querySelector(".settings-footer").textContent = appInfo.label;
    applyLoginStatus(login);
    // the redraw replaced the usage card → put the last reading back
    renderAppUsage(lastUsage);
  }

  // LEARN: NO-JUMP RULE (see app/ui/README.md, "Pages must never jump")
  //   rebuilding the page (innerHTML) empties it for a moment → the browser
  //   snaps the scroll position → the page jumps under your mouse
  //   so: the page is drawn ONCE per visit; clicks and timers only change
  //   the bits that changed (a button's "on", a number, a note)
  //   keepScrollPosition is the safety net around the one full drawing

  // run a full drawing, then put the scroll position back where it was
  function keepScrollPosition(render) {
    const before = root.scrollTop;
    render();
    root.scrollTop = before;
  }

  // LEARN: show new saved values without redrawing
  //   values = { refresh_interval_seconds: 5, … } (what Python saved)
  //   every button of that tool gets "on" only if its value matches
  //   JSON.stringify(5) === "5" → the same text the button carries
  function applyToolValues(toolId, values) {
    root.querySelectorAll(`button[data-tool="${toolId}"]`).forEach((button) => {
      const saved = values[button.dataset.field];
      button.classList.toggle("on", JSON.stringify(saved) === button.dataset.value);
    });
  }

  // the Open at login switch + note, without redrawing
  function applyLoginStatus(login) {
    const isOn = LOGIN_ON_STATES.has(login.state);
    root.querySelectorAll("button[data-login]").forEach((button) => {
      button.classList.toggle("on", JSON.parse(button.dataset.login) === isOn);
      button.disabled = login.state === "unavailable";
    });
    root.querySelector(".login-note").textContent =
      login.note || "Opens Bao Internal Apps when you log in to your Mac.";
  }

  // ask Python for the current settings, then draw the page (once per visit)
  // called by → mount
  async function refreshSettingsPage() {
    // remember which page asked (see the check after the await)
    const page = root;
    // ask for both at once (see Promise.all in shell.js)
    const [sections, appInfo, login] = await Promise.all([
      api.get_settings_sections(),
      api.get_app_info(),
      api.get_open_at_login(),
    ]);
    // the user may have left Settings while this was loading
    if (root !== page || !root) return;
    keepScrollPosition(() => renderSettingsSections(sections, appInfo, login));
  }

  // LEARN: ONE click listener on the whole page, not one per button
  //   event.target = the exact element clicked
  //   .closest("button[data-field]") → that element or its nearest parent
  //     matching the selector (null if none) → clicks on the button's text
  //     still find the button
  //   industry term: "event delegation"
  async function onSettingsClick(event) {
    const choice = event.target.closest("button[data-field]");
    const reset = event.target.closest("button[data-reset]");
    const login = event.target.closest("button[data-login]");
    // each answer from Python is the saved state → shown in place (no redraw)
    if (login) {
      // data-login="true" → JSON.parse → the real true / false
      applyLoginStatus(await api.set_open_at_login(JSON.parse(login.dataset.login)));
    } else if (choice) {
      const toolId = choice.dataset.tool;
      const values = await api.update_tool_preference(toolId, choice.dataset.field, JSON.parse(choice.dataset.value));
      applyToolValues(toolId, values);
    } else if (reset) {
      const toolId = reset.dataset.reset;
      applyToolValues(toolId, await api.reset_tool_preferences(toolId));
    }
  }

  // LEARN: the same mount / unmount shape as a tool (see shell.js)
  //   called by → shell.js openView
  window.BaoSettingsView = {
    async mount(container, bridgeApi) {
      api = bridgeApi;
      root = container;
      root.addEventListener("click", onSettingsClick);
      await refreshSettingsPage();
      if (!document.hidden) startUsageTimer();
    },
    unmount() {
      stopUsageTimer();
      lastUsage = null;
      // removeEventListener → stop listening (must pass the same function)
      if (root) root.removeEventListener("click", onSettingsClick);
      root = null;
    },
    // window hidden / shown again (shell.js) → stop / restart the usage timer
    pause: stopUsageTimer,
    resume: startUsageTimer,
  };
})();
