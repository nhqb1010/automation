// System Monitor page: polls Python on a timer and redraws the cards.
//
// LEARN: the refresh loop.
//
//   every N s (Settings) ──▶ call("get_live_stats") ──▶ rings, cores, gauges
//        └─ if a top apps list is open ──▶ call("get_top_apps") ──▶ rows
//   every 30 s          ──▶ call("get_storage")    ──▶ donuts
//
//   tool hidden / window minimised ──▶ timers stop; back on screen ──▶ restart
(() => {
  const C = window.BaoCharts;
  const I = window.BaoIcons;
  const STORAGE_REFRESH_MS = 30000;
  const CPU_WARN = 60;
  const CPU_CRITICAL = 85;
  const TEMP_WARN = 70;
  const TEMP_CRITICAL = 90;
  const TEMP_SCALE = { min: 30, max: 100 };
  const DISK_WARN = 75;
  const DISK_CRITICAL = 90;
  // matches the 60 s rolling history kept in Python (history.py)
  const HISTORY_SECONDS = 60;
  const DRIVE_TAGS = {
    external: ["usb", "External"],
    network: ["network", "Network"],
    image: ["disc", "Disk image"],
  };

  let root = null;
  let ctx = null;
  let prefs = null;
  let parts = null;
  let liveTimer = null;
  let storageTimer = null;
  let running = false;
  // true only once mount has fully finished (preferences loaded)
  let mounted = false;
  // LEARN: counters instead of plain true/false flags. Each mount and each
  // start of the timers gets a new number; a reply that comes back carrying an
  // old number belongs to a previous visit and is ignored, so it can neither
  // draw on the new page nor block the new page's first refresh.
  let mountGeneration = 0;
  let refreshSession = 0;
  let liveInFlightSession = null;
  let storageInFlightSession = null;
  // LEARN: rows and donuts are built once and then only updated, so values
  // animate instead of the whole list being redrawn (which made it jump).
  // Rebuilt on every mount, because the shell gives the tool fresh markup.
  let topRows = { cpu: new Map(), memory: new Map() };
  let storageView = null;
  // set once a GPU reading has been seen, so one missed reading does not
  // collapse the card to a single gauge and back
  let gpuSeen = false;

  const $ = (selector) => root.querySelector(selector);

  // LEARN: keeps the page still while cards redraw. Reading layout in the
  // middle of a redraw (sparklines measure their width) can make the browser
  // move the scroll position; if it moved, it is put back before the screen
  // is painted. The first correction per part is written to the log, so the
  // cause can be traced.
  const reportedScrollMoves = new Set();

  function renderKeepingScrollPosition(part, render) {
    const before = root.scrollTop;
    render();
    const after = root.scrollTop;
    if (after === before) return;
    root.scrollTop = before;
    if (reportedScrollMoves.has(part)) return;
    reportedScrollMoves.add(part);
    window.pywebview.api.log_client_error(
      `Scroll position moved during ${part} redraw (${before} to ${after}), restored`,
      "system_monitor",
      0,
    );
  }

  function historySlots() {
    return C.sparklineSlots(HISTORY_SECONDS, prefs.refresh_interval_seconds);
  }

  function markCardLoaded(selector) {
    $(selector).classList.remove("loading");
  }

  // ---------- CPU and memory ----------

  function renderCpuCard(cpu) {
    const color = C.statusColor(cpu.percent, CPU_WARN, CPU_CRITICAL);
    parts.cpuRing.update(cpu.percent, color, `${Math.round(cpu.percent)}%`, "in use");
    $(".sm-load").textContent = cpu.load_average.map((v) => v.toFixed(2)).join(" · ");
    const hasLayout = cpu.performance_cores + cpu.efficiency_cores > 0;
    $(".sm-core-summary").innerHTML = hasLayout
      ? `<b>${cpu.performance_cores}P + ${cpu.efficiency_cores}E</b> cores`
      : `<b>${cpu.cores.length}</b> cores`;
    $(".sm-core-legend").style.display = hasLayout ? "" : "none";
    C.drawSparkline($(".sm-cpu-spark"), cpu.history, { min: 0, max: 100, color: "var(--accent)", slots: historySlots() });
    renderCoreColumns(cpu.cores);
    markCardLoaded(".sm-cpu");
  }

  function renderCoreColumns(cores) {
    const container = $(".sm-cores");
    if (container.children.length !== cores.length) {
      container.innerHTML = cores
        .map(
          (core) => `<div class="sm-core" title="Core ${core.index}">
            <div class="col"><div class="fill"></div></div><div class="tag">${core.kind === "?" ? "" : core.kind}</div></div>`,
        )
        .join("");
    }
    // update heights in place so the CSS transition animates them
    cores.forEach((core, i) => {
      const fill = container.children[i].querySelector(".fill");
      fill.style.height = `${core.percent}%`;
      fill.style.background = core.kind === "E" ? "var(--e-core)" : "var(--p-core)";
      container.children[i].title = `Core ${core.index} ${core.kind === "E" ? "Efficiency" : core.kind === "P" ? "Performance" : ""} ${Math.round(core.percent)}%`;
    });
  }

  function renderMemoryCard(memory) {
    const color = C.statusColor(memory.percent, CPU_WARN, CPU_CRITICAL);
    parts.memoryRing.update(memory.percent, color, `${Math.round(memory.percent)}%`, "used");
    $(".sm-memory-used").textContent = C.formatBytes(memory.used_bytes);
    $(".sm-memory-total").textContent = C.formatBytes(memory.total_bytes, 0);
    $(".sm-swap").textContent = C.formatBytes(memory.swap_used_bytes);
    C.drawSparkline($(".sm-memory-spark"), memory.history, {
      min: 0,
      max: 100,
      color: "var(--accent)",
      slots: historySlots(),
    });
    markCardLoaded(".sm-memory");
  }

  // ---------- temperature ----------

  function renderTemperatureCard(temperature) {
    const card = $(".sm-temperature");
    card.classList.toggle("unavailable", !temperature.available);
    markCardLoaded(".sm-temperature");
    if (!temperature.available) {
      $(".sm-unavailable-reason").textContent = temperature.reason || "";
      return;
    }
    const isChip = temperature.source === "chip";
    if (!isChip && temperature.gpu_hottest != null) gpuSeen = true;
    const showGpu = !isChip && gpuSeen;
    const cpuName = isChip ? "Chip" : "CPU";
    parts.cpuGauge.update(
      temperature.cpu_hottest,
      C.statusColor(temperature.cpu_hottest, TEMP_WARN, TEMP_CRITICAL),
      cpuName,
      `avg ${Math.round(temperature.cpu_average)}°C`,
    );
    $(".sm-gauges").classList.toggle("single", !showGpu);
    $(".sm-gpu-gauge").style.display = showGpu ? "" : "none";
    if (showGpu) {
      const gpu = temperature.gpu_hottest;
      parts.gpuGauge.update(
        gpu,
        gpu == null ? "var(--text-muted)" : C.statusColor(gpu, TEMP_WARN, TEMP_CRITICAL),
        "GPU",
        gpu == null ? "no reading" : "hottest",
      );
    }
    $(".sm-temp-legend").textContent = cpuName;
    $(".sm-legend-gpu").style.display = showGpu ? "" : "none";
    C.drawSparklines(
      $(".sm-temp-spark"),
      [
        { name: cpuName, values: temperature.cpu_history, color: "var(--series-1)" },
        { name: "GPU", values: showGpu ? temperature.gpu_history : [], color: "var(--series-2)" },
      ],
      { ...TEMP_SCALE, slots: historySlots() },
    );
  }

  // ---------- top apps ----------

  function createAppRow(app) {
    const el = document.createElement("div");
    el.className = "app-row entering";
    el.title = app.name;
    el.innerHTML = `
      <div class="app-icon">${app.icon ? `<img src="${app.icon}" alt="">` : I.svg("terminal", 16)}</div>
      <div class="app-name">${C.escapeHtml(app.name)}</div>
      <div><div class="bar"><div></div></div><div class="mini-ring"></div></div>
      <div class="app-val num"></div>
      <svg class="app-spark"></svg>`;
    el.addEventListener("animationend", () => el.classList.remove("entering"), { once: true });
    return {
      el,
      bar: el.querySelector(".bar > div"),
      ring: C.createRing(el.querySelector(".mini-ring"), { size: 22, stroke: 4, label: false }),
      value: el.querySelector(".app-val"),
      spark: el.querySelector(".app-spark"),
    };
  }

  function updateAppRow(row, app, kind, memoryTotal) {
    const share = kind === "cpu" ? app.cpu_percent : (app.memory_bytes / memoryTotal) * 100;
    const color = C.statusColor(share, CPU_WARN, CPU_CRITICAL);
    row.bar.style.width = `${Math.min(100, share)}%`;
    row.bar.style.background = color;
    row.ring.update(share, color);
    row.value.textContent = kind === "cpu" ? `${share.toFixed(share < 10 ? 1 : 0)}%` : C.formatBytes(app.memory_bytes);
    // fixed scale (whole CPU, or all of RAM) so the line never rescales between refreshes
    C.drawSparkline(row.spark, app.history, {
      min: 0,
      max: kind === "cpu" ? 100 : memoryTotal,
      color: "var(--text-secondary)",
      fill: false,
      slots: historySlots(),
    });
  }

  function measureRowTops(list) {
    return new Map([...list.querySelectorAll(".app-row")].map((el) => [el, el.getBoundingClientRect().top]));
  }

  // LEARN: a FLIP animation. Note where each row was (First), put the rows in
  // their new order (Last), shift each one back to where it was (Invert),
  // then let the CSS transition slide it home (Play). Nothing moves unless
  // the ranking actually changed.
  function placeRowsInOrder(list, ordered, topsBefore) {
    const current = [...list.children];
    if (current.length === ordered.length && current.every((el, i) => el === ordered[i])) return;
    ordered.forEach((el) => list.appendChild(el));
    ordered.forEach((el) => {
      const before = topsBefore.get(el);
      if (before === undefined) return;
      const delta = before - el.getBoundingClientRect().top;
      if (!delta) return;
      el.style.transition = "none";
      el.style.transform = `translateY(${delta}px)`;
      // reading the layout applies the shift before the transition is restored
      el.getBoundingClientRect();
      el.style.transition = "";
      el.style.transform = "";
    });
  }

  function renderAppRows(list, rows, apps, kind, memoryTotal) {
    if (!apps.length) {
      rows.clear();
      list.innerHTML = '<div class="top-empty">Collecting…</div>';
      return;
    }
    const topsBefore = measureRowTops(list);
    list.querySelector(".top-empty")?.remove();
    const keys = new Set(apps.map((app) => app.key));
    rows.forEach((row, key) => {
      if (!keys.has(key)) {
        row.el.remove();
        rows.delete(key);
      }
    });
    const ordered = apps.map((app) => {
      if (!rows.has(app.key)) rows.set(app.key, createAppRow(app));
      const row = rows.get(app.key);
      updateAppRow(row, app, kind, memoryTotal);
      return row.el;
    });
    placeRowsInOrder(list, ordered, topsBefore);
  }

  function isTopListOpen(kind) {
    return kind === "cpu" ? prefs.cpu_top_apps_open : prefs.memory_top_apps_open;
  }

  function applyTopListOpenState() {
    root.querySelectorAll(".top-toggle").forEach((button) => {
      const open = isTopListOpen(button.dataset.list);
      button.classList.toggle("open", open);
      $(`.sm-${button.dataset.list}-top`).classList.toggle("open", open);
    });
  }

  async function onTopToggleClick(event) {
    const button = event.target.closest(".top-toggle");
    if (!button) return;
    const kind = button.dataset.list;
    const field = kind === "cpu" ? "cpu_top_apps_open" : "memory_top_apps_open";
    const generation = mountGeneration;
    const updated = await ctx.setPreference(field, !isTopListOpen(kind));
    // the user may have left the tool while the preference was saving
    if (generation !== mountGeneration || !root) return;
    prefs = updated;
    applyTopListOpenState();
    refreshLiveStats();
  }

  // ---------- storage ----------

  function isSecondaryDrive(drive) {
    return drive.kind === "network" || drive.kind === "image";
  }

  function createDriveView(drive) {
    const isMain = drive.kind === "main";
    const isSecondary = isSecondaryDrive(drive);
    const tag = DRIVE_TAGS[drive.kind];
    const el = document.createElement("div");
    el.className = "drive";
    el.classList.toggle("main", isMain);
    el.classList.toggle("secondary", isSecondary);
    el.innerHTML = `<div class="drive-ring"></div>
      <div class="drive-text"><div class="d-name"></div>
        <div class="d-meta num"></div>
        ${tag ? `<span class="d-tag">${I.svg(tag[0], 11)}${tag[1]}</span>` : ""}</div>`;
    return {
      el,
      ring: C.createRing(el.querySelector(".drive-ring"), {
        size: isMain ? 120 : drive.kind === "external" ? 76 : 52,
        stroke: isMain ? 14 : drive.kind === "external" ? 10 : 7,
        dashed: isSecondary,
      }),
      name: el.querySelector(".d-name"),
      meta: el.querySelector(".d-meta"),
    };
  }

  function updateDriveView(view, drive) {
    const percent = drive.used_percent ?? 0;
    const color =
      !drive.responding || isSecondaryDrive(drive) ? "var(--text-muted)" : C.statusColor(percent, DISK_WARN, DISK_CRITICAL);
    view.ring.update(percent, color, drive.responding ? `${Math.round(percent)}%` : "—");
    view.name.textContent = drive.name;
    // built only from formatted numbers, never from system names
    view.meta.innerHTML = !drive.responding
      ? "Not responding"
      : drive.kind === "main"
        ? `<b>${C.formatBytes(drive.free_bytes)}</b> free · ${C.formatBytes(drive.used_bytes)} of ${C.formatBytes(drive.total_bytes)}`
        : `${C.formatBytes(drive.free_bytes)} free of ${C.formatBytes(drive.total_bytes)}`;
    view.el.classList.toggle("not-responding", !drive.responding);
  }

  // the donuts are rebuilt only when drives are plugged in or removed;
  // otherwise each one just animates to its new value
  function renderStorageCard(storage) {
    const drives = storage.drives;
    const signature = drives.map((drive) => `${drive.kind}:${drive.mountpoint}`).join("|");
    if (!storageView || storageView.signature !== signature) {
      const container = $(".sm-drives");
      container.innerHTML = "";
      storageView = { signature, views: drives.map(createDriveView) };
      storageView.views.forEach((view, i) => {
        if (i === 1 && drives[0].kind === "main") container.insertAdjacentHTML("beforeend", '<div class="drives-divider"></div>');
        container.appendChild(view.el);
      });
    }
    drives.forEach((drive, i) => updateDriveView(storageView.views[i], drive));
    markCardLoaded(".sm-storage");
  }

  // ---------- refresh loop ----------

  function isRefreshSessionCurrent(session) {
    return running && session === refreshSession;
  }

  async function refreshLiveStats() {
    const session = refreshSession;
    if (!running || liveInFlightSession === session) return;
    liveInFlightSession = session;
    try {
      const stats = await ctx.call("get_live_stats");
      if (!isRefreshSessionCurrent(session)) return;
      renderKeepingScrollPosition("live stats", () => {
        renderCpuCard(stats.cpu);
        renderMemoryCard(stats.memory);
        renderTemperatureCard(stats.temperature);
      });
      if (prefs.cpu_top_apps_open || prefs.memory_top_apps_open) {
        const top = await ctx.call("get_top_apps", { limit: prefs.top_apps_count });
        if (!isRefreshSessionCurrent(session)) return;
        renderKeepingScrollPosition("top apps", () => {
          if (prefs.cpu_top_apps_open) {
            renderAppRows($(".sm-cpu-top"), topRows.cpu, top.by_cpu, "cpu", top.memory_total_bytes);
          }
          if (prefs.memory_top_apps_open) {
            renderAppRows($(".sm-memory-top"), topRows.memory, top.by_memory, "memory", top.memory_total_bytes);
          }
        });
      }
    } finally {
      if (liveInFlightSession === session) liveInFlightSession = null;
    }
  }

  async function refreshStorage() {
    const session = refreshSession;
    if (!running || storageInFlightSession === session) return;
    storageInFlightSession = session;
    try {
      const storage = await ctx.call("get_storage");
      if (isRefreshSessionCurrent(session)) renderKeepingScrollPosition("storage", () => renderStorageCard(storage));
    } finally {
      if (storageInFlightSession === session) storageInFlightSession = null;
    }
  }

  function startRefreshTimers() {
    if (running || !mounted || document.hidden) return;
    running = true;
    refreshSession += 1;
    refreshLiveStats();
    refreshStorage();
    liveTimer = setInterval(refreshLiveStats, prefs.refresh_interval_seconds * 1000);
    storageTimer = setInterval(refreshStorage, STORAGE_REFRESH_MS);
  }

  function stopRefreshTimers() {
    running = false;
    clearInterval(liveTimer);
    clearInterval(storageTimer);
  }

  async function mount(container, context) {
    mountGeneration += 1;
    const generation = mountGeneration;
    root = container;
    ctx = context;
    topRows = { cpu: new Map(), memory: new Map() };
    storageView = null;
    root.querySelectorAll("[data-icon]").forEach((el) => {
      el.innerHTML = I.svg(el.dataset.icon, el.classList.contains("sm-unavailable-icon") ? 28 : 14);
    });
    parts = {
      cpuRing: C.createRing($(".sm-cpu-ring"), { size: 108, stroke: 12 }),
      memoryRing: C.createRing($(".sm-memory-ring"), { size: 108, stroke: 12 }),
      cpuGauge: C.createArcGauge($(".sm-cpu-gauge"), TEMP_SCALE),
      gpuGauge: C.createArcGauge($(".sm-gpu-gauge"), TEMP_SCALE),
    };
    prefs = await ctx.getPreferences();
    // the user may have switched away (unmount) while preferences were loading
    if (generation !== mountGeneration || !root) return;
    $(".sm-refresh-label").textContent = `Live · every ${prefs.refresh_interval_seconds}s`;
    // an open list reserves room for every row up front, so it never grows as rows arrive
    $(".sm").style.setProperty("--sm-top-count", prefs.top_apps_count);
    applyTopListOpenState();
    root.addEventListener("click", onTopToggleClick);
    mounted = true;
    // LEARN: if the window was hidden while mount was waiting, the timers stay
    // off; the shell's next "shown" event calls resume and starts them.
    startRefreshTimers();
  }

  function unmount() {
    mountGeneration += 1;
    mounted = false;
    stopRefreshTimers();
    if (root) root.removeEventListener("click", onTopToggleClick);
    root = null;
  }

  window.BaoTools.register("system_monitor", {
    mount,
    unmount,
    pause: stopRefreshTimers,
    resume: startRefreshTimers,
  });
})();
