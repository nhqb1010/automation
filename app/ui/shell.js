// LEARN: YOU ARE HERE
//   index.html loads THIS FILE last ▶ asks Python (bridge.py) for the tools
//   ▶ builds the sidebar ▶ opens a tool (its view.js) or the Settings page
//   read next → app/ui/settings.js

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
//
// LEARN: mount / unmount (industry term: "lifecycle")
//   mount   = "you're on screen now": draw, start timers
//   unmount = "you're leaving": stop timers, remove listeners
//   pause / resume = window hidden / shown again
//
// LEARN: (() => { … })() = run once now, keep names private (see icons.js)
(() => {
  // short name for the icons helper from icons.js
  const I = window.BaoIcons;
  // tool id → the object the tool registered ({ mount, unmount, … })
  const toolModules = {};
  // tool id → { html, css, js } from Python (fetched once, then reused)
  // industry term: "cache"
  const loadedViews = {};
  // everything the shell needs to remember while the app runs
  //   api = window.pywebview.api (the bridge)
  //   current / currentId = what's on screen now
  const state = { api: null, tools: [], current: null, currentId: null };

  // LEARN: the one global tool pages use to plug in
  //   called by → each tool's view.js, when it runs
  //   ≈ adding an app to Django's INSTALLED_APPS, but at run time
  //   industry term: "registry"
  window.BaoTools = {
    register(id, module) {
      toolModules[id] = module;
    },
  };

  // forward page errors to the Python log file
  // called by → the two error listeners below, and openView on a failed load
  // output → bridge.py log_client_error ▶ logs/app.log
  function forwardClientError(message, source, line) {
    // a || b → b when a is empty; Number(x) || 0 → 0 when x isn't a number
    if (state.api) state.api.log_client_error(String(message), String(source || "page"), Number(line) || 0);
  }

  // LEARN: addEventListener("name", f) → "when this happens, call f"
  //   "error" = any uncaught JS error on the page
  //   "unhandledrejection" = a Promise failed and nobody caught it
  //   (event) => … = arrow function that gets the event's details
  //   industry term: "event listener" / "event handler"
  window.addEventListener("error", (event) => forwardClientError(event.message, event.filename, event.lineno));
  // LEARN: a && b → b if a exists, else a ≈ Python "a and b"
  //   → the error's message if it has one, else the error itself
  window.addEventListener("unhandledrejection", (event) =>
    forwardClientError(event.reason && (event.reason.message || event.reason), "promise", 0),
  );

  // LEARN: the security policy (index.html) refused something → write it to
  //   the log, so a blocked attempt is visible in the Logs tool
  //   violatedDirective = which rule ("script-src"), blockedURI = what it was
  window.addEventListener("securitypolicyviolation", (event) =>
    forwardClientError(
      `Blocked by the security policy: ${event.violatedDirective} ${event.blockedURI || "inline code"}`,
      event.sourceFile || "security-policy",
      event.lineNumber,
    ),
  );

  // ---------- error badge ----------
  // LEARN: a red count on the Logs sidebar entry when errors were logged
  //   that you haven't looked at yet (Python counts them, see logging_setup.py)
  //   checked every few seconds; opening Logs marks them all as seen
  const ERROR_BADGE_TOOL_ID = "log_viewer";
  const ERROR_BADGE_CHECK_MS = 5000;
  let errorBadgeTimer = null;

  async function refreshErrorBadge() {
    if (!state.api) return;
    // looking at the Logs tool right now → everything on it counts as seen
    if (state.currentId === ERROR_BADGE_TOOL_ID) await state.api.mark_errors_seen();
    const unseen = await state.api.get_unseen_error_count();
    const badge = document.querySelector(`[data-view="${ERROR_BADGE_TOOL_ID}"] .nav-badge`);
    if (!badge) return;
    badge.hidden = unseen === 0;
    // "99+" so a flood of errors can't stretch the sidebar
    badge.textContent = unseen > 99 ? "99+" : String(unseen);
  }

  function startErrorBadgeTimer() {
    if (errorBadgeTimer) return;
    refreshErrorBadge();
    errorBadgeTimer = setInterval(refreshErrorBadge, ERROR_BADGE_CHECK_MS);
  }

  function stopErrorBadgeTimer() {
    clearInterval(errorBadgeTimer);
    errorBadgeTimer = null;
  }

  // a tool failed to load → draw a friendly card instead
  // called by → openView
  function renderErrorCard(container, title, detail) {
    container.innerHTML = `<div class="error-card">
      <div class="icon">${I.svg("alert", 28)}</div>
      <h2>${title}</h2><p>${detail}</p></div>`;
  }

  // LEARN: the "context" handed to a tool's mount(...)
  //   called by → openView
  //   gives back → small functions with the tool id already filled in
  //   → a tool calls ctx.call("get_live_stats") without knowing its own id
  //   { toolId } = short for { toolId: toolId }
  function buildToolContext(toolId) {
    const api = state.api;
    return {
      toolId,
      call: (action, params = {}) => api.call(toolId, action, params),
      getPreferences: () => api.get_tool_preferences(toolId),
      setPreference: (field, value) => api.update_tool_preference(toolId, field, value),
    };
  }

  // LEARN: async function = a function that can wait with "await"
  //   await x → pause HERE until the Promise x has its answer, page keeps running
  //   ≈ Python async def / await
  //   Promise = "the answer will come later" (every bridge call gives one)
  //
  //   called by → openView, the first time a tool opens
  //   gives back → the tool's registered object ({ mount, unmount, … })
  async function loadToolModule(toolId) {
    // already loaded once → reuse it
    if (toolModules[toolId]) return toolModules[toolId];
    if (!loadedViews[toolId]) loadedViews[toolId] = await state.api.load_tool_view(toolId);
    const view = loadedViews[toolId];
    // LEARN: document.createElement("style") → a new <style> tag (not on the page yet)
    //   appendChild(x) → put x on the page, at the end of head / body
    const style = document.createElement("style");
    // dataset.tool = … → adds data-tool="…" (marks which tool owns it)
    style.dataset.tool = toolId;
    style.textContent = view.css;
    document.head.appendChild(style);
    // LEARN: run the tool's script as a FILE, never as pasted-in text
    //   the security policy (index.html) refuses script text put on the page
    //   → the text is wrapped in a Blob (an in-memory file) with its own
    //   blob: address, and loaded like any script file
    //   "//# sourceURL=…" → error messages name the file "system_monitor/view.js"
    await runToolScript(`${view.js}\n//# sourceURL=${toolId}/view.js`);
    // LEARN: throw new Error(…) ≈ Python raise Exception(…)
    if (!toolModules[toolId]) throw new Error(`${toolId} did not register itself`);
    return toolModules[toolId];
  }

  // LEARN: load script text through a blob: address and wait until it ran
  //   new Promise((resolve, reject) => …) = make your own "answer later":
  //   call resolve() when done, reject(error) when it failed
  //   URL.revokeObjectURL → free the in-memory file afterwards
  function runToolScript(code) {
    const url = URL.createObjectURL(new Blob([code], { type: "text/javascript" }));
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = url;
      script.onload = () => {
        URL.revokeObjectURL(url);
        resolve();
      };
      script.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("tool script could not be loaded"));
      };
      document.body.appendChild(script);
    });
  }

  // highlight the sidebar entry of what's on screen
  function markActiveNavItem(viewId) {
    // querySelectorAll → every match; forEach(f) → call f on each
    document.querySelectorAll(".nav-item").forEach((item) => {
      // toggle("active", true / false) → add / remove the class
      // === → equal (always use === in JS; == has odd rules)
      item.classList.toggle("active", item.dataset.view === viewId);
    });
  }

  // LEARN: every await is a pause where the user can switch to another view.
  // After each one, isStillCurrent checks we are still wanted before touching
  // the page; otherwise a slow load would overwrite whatever is now on screen.
  //   industry term: "race condition"
  //
  //   called by → sidebar clicks, shortcuts, startShell
  //   output → the chosen tool / Settings drawn in the content area
  async function openView(viewId) {
    if (viewId === state.currentId) return;
    const container = document.getElementById("view");
    // tell the old view to stop its timers before it disappears
    if (state.current && state.current.unmount) state.current.unmount();
    state.current = null;
    state.currentId = viewId;
    markActiveNavItem(viewId);
    container.innerHTML = "";
    // remember it → reopens here at the next start (state.json)
    state.api.update_ui_state({ last_tool: viewId });
    // opening Logs clears its error badge straight away
    if (viewId === ERROR_BADGE_TOOL_ID) refreshErrorBadge();
    const isStillCurrent = () => state.currentId === viewId;

    if (viewId === "settings") {
      state.current = window.BaoSettingsView;
      await window.BaoSettingsView.mount(container, state.api);
      return;
    }

    // .find(f) → the first item where f is true (undefined if none)
    const tool = state.tools.find((t) => t.id === viewId);
    // LEARN: try / catch ≈ Python try / except
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

  // narrow / wide sidebar; save = false at startup (value came from the file)
  function setSidebarCollapsed(collapsed, save = true) {
    document.getElementById("app").classList.toggle("collapsed", collapsed);
    if (save) state.api.update_ui_state({ sidebar_collapsed: collapsed });
  }

  // draw the sidebar entries and hook up the clicks
  // called by → startShell, once
  function buildSidebar() {
    document.getElementById("collapse-btn").innerHTML = I.svg("panel-left", 16);
    // [data-icon] → every element that has a data-icon attribute
    document.querySelectorAll("[data-icon]").forEach((el) => {
      el.innerHTML = I.svg(el.dataset.icon);
    });
    const nav = document.getElementById("tool-nav");
    // one entry per tool; the first 9 show their shortcut ⌘1 … ⌘9
    //   .map((tool, index) => …) → index = position, 0, 1, 2, …
    nav.innerHTML = state.tools
      .map(
        (tool, index) => `<div class="nav-item" data-view="${tool.id}" title="${tool.name}">
          <span class="nav-icon">${I.svg(tool.icon)}</span>
          <span class="label">${tool.name}</span>
          <span class="nav-badge num" hidden></span>
          ${index < 9 ? `<span class="kbd">⌘${index + 1}</span>` : ""}
        </div>`,
      )
      .join("");
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.addEventListener("click", () => openView(item.dataset.view));
    });
    document.getElementById("collapse-btn").addEventListener("click", () => {
      // ! = not
      setSidebarCollapsed(!document.getElementById("app").classList.contains("collapsed"));
    });
  }

  // keyboard shortcuts: ⌘1–⌘9 tools, ⌘, Settings, ⌘\ sidebar
  // called by → the browser, on every key press (listener in startShell)
  function handleShortcut(event) {
    // metaKey = the ⌘ key is held
    if (!event.metaKey) return;
    if (event.key >= "1" && event.key <= "9") {
      const tool = state.tools[Number(event.key) - 1];
      if (tool) {
        // preventDefault() → stop the browser's own action for this key
        event.preventDefault();
        openView(tool.id);
      }
    } else if (event.key === ",") {
      event.preventDefault();
      openView("settings");
    } else if (event.key === "\\") {
      // "\\" = one backslash (\ must be doubled inside a string)
      event.preventDefault();
      setSidebarCollapsed(!document.getElementById("app").classList.contains("collapsed"));
    }
  }

  // LEARN: the page is "hidden" when the window is minimised or covered.
  // Tools pause their timers then, so nothing polls in the background.
  //   called by → the browser ("visibilitychange" event)
  function handleVisibilityChange() {
    // the badge check pauses too → nothing runs while the window is hidden
    if (document.hidden) stopErrorBadgeTimer();
    else startErrorBadgeTimer();
    const tool = state.current;
    if (!tool) return;
    if (document.hidden && tool.pause) tool.pause();
    if (!document.hidden && tool.resume) tool.resume();
  }

  // LEARN: start everything once the bridge is ready
  //   called by → the check at the bottom of this file
  async function startShell() {
    state.api = window.pywebview.api;
    // LEARN: Promise.all([a, b]) → ask both at once, wait for both answers
    //   const [tools, ui] = … → unpack ≈ Python tools, ui = …
    const [tools, ui, appInfo] = await Promise.all([
      state.api.list_tools(),
      state.api.get_ui_state(),
      state.api.get_app_info(),
    ]);
    state.tools = tools;
    buildSidebar();
    // "v0.1.0" quietly under Settings; the title shows the full stamp on hover
    const version = document.getElementById("app-version");
    version.textContent = appInfo.short_label;
    version.title = appInfo.label;
    setSidebarCollapsed(ui.sidebar_collapsed, false);
    document.addEventListener("keydown", handleShortcut);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    startErrorBadgeTimer();
    // reopen the last view if it still exists, else the first tool
    //   .some(f) → true if f is true for any item ≈ Python any(…)
    const known = ui.last_tool === "settings" || tools.some((t) => t.id === ui.last_tool);
    await openView(known ? ui.last_tool : tools[0].id);
  }

  // LEARN: pywebview injects window.pywebview.api after the page loads and
  // then fires "pywebviewready"; it may already be there by the time we run.
  //   already there → start now
  //   not yet → start when the event fires ({ once: true } → only one time)
  if (window.pywebview && window.pywebview.api && window.pywebview.api.list_tools) {
    startShell();
  } else {
    window.addEventListener("pywebviewready", startShell, { once: true });
  }
})();
