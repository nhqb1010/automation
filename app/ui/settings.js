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

  // how one choice reads on its button: true → "On", 2 + "s" → "2s"
  function formatChoice(value, unit) {
    // typeof x → the kind of value as text: "boolean", "number", "string", …
    if (typeof value === "boolean") return value ? "On" : "Off";
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
             class="${choice === field.value ? "on" : ""}">${formatChoice(choice, field.unit)}</button>`,
      )
      .join("");
    return `<div class="setting-row">
      <div><div class="setting-title">${field.title}</div>
        ${field.description ? `<div class="setting-desc">${field.description}</div>` : ""}</div>
      <div class="segmented">${buttons}</div>
    </div>`;
  }

  // the whole page: a heading, then one card per tool
  // called by → refreshSettingsPage
  function renderSettingsSections(sections) {
    const I = window.BaoIcons;
    root.innerHTML = `
      <div class="page-head"><h1>Settings</h1><div class="meta">Changes apply immediately</div></div>
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
        .join("")}`;
  }

  // ask Python for the current settings, then redraw
  // called by → mount, and after every click
  async function refreshSettingsPage() {
    // remember which page asked (see the check after the await)
    const page = root;
    const sections = await api.get_settings_sections();
    // the user may have left Settings while this was loading
    if (root !== page || !root) return;
    renderSettingsSections(sections);
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
    if (choice) {
      await api.update_tool_preference(choice.dataset.tool, choice.dataset.field, JSON.parse(choice.dataset.value));
      await refreshSettingsPage();
    } else if (reset) {
      await api.reset_tool_preferences(reset.dataset.reset);
      await refreshSettingsPage();
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
    },
    unmount() {
      // removeEventListener → stop listening (must pass the same function)
      if (root) root.removeEventListener("click", onSettingsClick);
      root = null;
    },
  };
})();
