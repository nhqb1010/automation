// The app shell: sidebar, switching tools, shortcuts, error forwarding.
//
// LEARN: how a tool page gets on screen.
//
//   click sidebar ──▶ api.load_tool_view(id) ──▶ { html, css, js } from Python
//        │
//        ├─ html  ──▶ put into the content area
//        ├─ css   ──▶ added once as a <style> tag
//        └─ js    ──▶ run once; it calls BaoTools.register(id, { mount, unmount })
//                     then the shell calls mount(container, context)
(() => {
  const I = window.BaoIcons;
  const toolModules = {};
  const loadedViews = {};
  const state = { api: null, tools: [], current: null, currentId: null };

  window.BaoTools = {
    register(id, module) {
      toolModules[id] = module;
    },
  };

  // forward page errors to the Python log file
  function forwardClientError(message, source, line) {
    if (state.api) state.api.log_client_error(String(message), String(source || "page"), Number(line) || 0);
  }

  window.addEventListener("error", (event) => forwardClientError(event.message, event.filename, event.lineno));
  window.addEventListener("unhandledrejection", (event) =>
    forwardClientError(event.reason && (event.reason.message || event.reason), "promise", 0),
  );

  function renderErrorCard(container, title, detail) {
    container.innerHTML = `<div class="error-card">
      <div class="icon">${I.svg("alert", 28)}</div>
      <h2>${title}</h2><p>${detail}</p></div>`;
  }

  function buildToolContext(toolId) {
    const api = state.api;
    return {
      toolId,
      call: (action, params = {}) => api.call(toolId, action, params),
      getPreferences: () => api.get_tool_preferences(toolId),
      setPreference: (field, value) => api.update_tool_preference(toolId, field, value),
    };
  }

  async function loadToolModule(toolId) {
    if (toolModules[toolId]) return toolModules[toolId];
    if (!loadedViews[toolId]) loadedViews[toolId] = await state.api.load_tool_view(toolId);
    const view = loadedViews[toolId];
    const style = document.createElement("style");
    style.dataset.tool = toolId;
    style.textContent = view.css;
    document.head.appendChild(style);
    const script = document.createElement("script");
    script.textContent = `${view.js}\n//# sourceURL=${toolId}/view.js`;
    document.body.appendChild(script);
    if (!toolModules[toolId]) throw new Error(`${toolId} did not register itself`);
    return toolModules[toolId];
  }

  function markActiveNavItem(viewId) {
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.classList.toggle("active", item.dataset.view === viewId);
    });
  }

  // LEARN: every await is a pause where the user can switch to another view.
  // After each one, isStillCurrent checks we are still wanted before touching
  // the page; otherwise a slow load would overwrite whatever is now on screen.
  async function openView(viewId) {
    if (viewId === state.currentId) return;
    const container = document.getElementById("view");
    if (state.current && state.current.unmount) state.current.unmount();
    state.current = null;
    state.currentId = viewId;
    markActiveNavItem(viewId);
    container.innerHTML = "";
    state.api.update_ui_state({ last_tool: viewId });
    const isStillCurrent = () => state.currentId === viewId;

    if (viewId === "settings") {
      state.current = window.BaoSettingsView;
      await window.BaoSettingsView.mount(container, state.api);
      return;
    }

    const tool = state.tools.find((t) => t.id === viewId);
    try {
      const module = await loadToolModule(viewId);
      if (!isStillCurrent()) return;
      container.innerHTML = loadedViews[viewId].html;
      state.current = module;
      await module.mount(container, buildToolContext(viewId));
    } catch (error) {
      forwardClientError(`${viewId} failed to load: ${error.message || error}`, "shell", 0);
      // one broken tool shows its own error card, but only if it is still on screen
      if (isStillCurrent()) {
        renderErrorCard(container, `${tool ? tool.name : viewId} could not load`, "Details are in logs/app.log.");
      }
    }
  }

  function setSidebarCollapsed(collapsed, save = true) {
    document.getElementById("app").classList.toggle("collapsed", collapsed);
    if (save) state.api.update_ui_state({ sidebar_collapsed: collapsed });
  }

  function buildSidebar() {
    document.getElementById("collapse-btn").innerHTML = I.svg("panel-left", 16);
    document.querySelectorAll("[data-icon]").forEach((el) => {
      el.innerHTML = I.svg(el.dataset.icon);
    });
    const nav = document.getElementById("tool-nav");
    nav.innerHTML = state.tools
      .map(
        (tool, index) => `<div class="nav-item" data-view="${tool.id}" title="${tool.name}">
          <span class="nav-icon">${I.svg(tool.icon)}</span>
          <span class="label">${tool.name}</span>
          ${index < 9 ? `<span class="kbd">⌘${index + 1}</span>` : ""}
        </div>`,
      )
      .join("");
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.addEventListener("click", () => openView(item.dataset.view));
    });
    document.getElementById("collapse-btn").addEventListener("click", () => {
      setSidebarCollapsed(!document.getElementById("app").classList.contains("collapsed"));
    });
  }

  function handleShortcut(event) {
    if (!event.metaKey) return;
    if (event.key >= "1" && event.key <= "9") {
      const tool = state.tools[Number(event.key) - 1];
      if (tool) {
        event.preventDefault();
        openView(tool.id);
      }
    } else if (event.key === ",") {
      event.preventDefault();
      openView("settings");
    } else if (event.key === "\\") {
      event.preventDefault();
      setSidebarCollapsed(!document.getElementById("app").classList.contains("collapsed"));
    }
  }

  // LEARN: the page is "hidden" when the window is minimised or covered.
  // Tools pause their timers then, so nothing polls in the background.
  function handleVisibilityChange() {
    const tool = state.current;
    if (!tool) return;
    if (document.hidden && tool.pause) tool.pause();
    if (!document.hidden && tool.resume) tool.resume();
  }

  async function startShell() {
    state.api = window.pywebview.api;
    const [tools, ui] = await Promise.all([state.api.list_tools(), state.api.get_ui_state()]);
    state.tools = tools;
    buildSidebar();
    setSidebarCollapsed(ui.sidebar_collapsed, false);
    document.addEventListener("keydown", handleShortcut);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    const known = ui.last_tool === "settings" || tools.some((t) => t.id === ui.last_tool);
    await openView(known ? ui.last_tool : tools[0].id);
  }

  // LEARN: pywebview injects window.pywebview.api after the page loads and
  // then fires "pywebviewready"; it may already be there by the time we run.
  if (window.pywebview && window.pywebview.api && window.pywebview.api.list_tools) {
    startShell();
  } else {
    window.addEventListener("pywebviewready", startShell, { once: true });
  }
})();
