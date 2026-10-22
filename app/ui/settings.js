// The Settings page, built from each tool's settings model.
// LEARN: nothing here knows about any specific tool. Python describes each
// field (title, choices, current value) and this page draws a row of buttons
// for it, so a new tool gets its settings section for free.
(() => {
  let api = null;
  let root = null;

  function formatChoice(value, unit) {
    if (typeof value === "boolean") return value ? "On" : "Off";
    return unit ? `${value}${unit}` : String(value);
  }

  function renderSettingRow(section, field) {
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

  async function refreshSettingsPage() {
    const page = root;
    const sections = await api.get_settings_sections();
    // the user may have left Settings while this was loading
    if (root !== page || !root) return;
    renderSettingsSections(sections);
  }

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

  window.BaoSettingsView = {
    async mount(container, bridgeApi) {
      api = bridgeApi;
      root = container;
      root.addEventListener("click", onSettingsClick);
      await refreshSettingsPage();
    },
    unmount() {
      if (root) root.removeEventListener("click", onSettingsClick);
      root = null;
    },
  };
})();
