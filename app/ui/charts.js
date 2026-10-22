// Shared hand-drawn SVG charts for every tool: ring, arc gauge, sparkline.
//
// LEARN: a ring is one SVG circle with a dashed stroke. The dash is as long
// as the whole circle; shifting it (stroke-dashoffset) reveals only a part.
//
//   circumference = 2πr
//   visible part  = circumference × percent / 100
//   dashoffset    = circumference − visible part
//
// Updating the offset (instead of redrawing) lets a CSS transition glide the
// ring to its new value.
(() => {
  const SVG_NS = "http://www.w3.org/2000/svg";

  function statusColor(value, warnAt, criticalAt) {
    if (value >= criticalAt) return "var(--critical)";
    if (value >= warnAt) return "var(--warning)";
    return "var(--good)";
  }

  function clampPercent(value) {
    return Math.min(100, Math.max(0, value || 0));
  }

  // live ring that animates between values; built once, then only updated.
  // dashed draws a dotted track (muted drives); label: false leaves out the
  // number in the middle (the small rings in top apps rows).
  function createRing(container, { size, stroke, dashed = false, label = true }) {
    const r = (size - stroke) / 2;
    const c = 2 * Math.PI * r;
    const dash = dashed ? 'stroke-dasharray="3 3"' : "";
    container.classList.add("ring-wrap");
    container.innerHTML = `
      <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="transform:rotate(-90deg)">
        <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--track)" stroke-width="${stroke}" ${dash}/>
        <circle class="arc" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${stroke}"
          stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${c}"/>
      </svg>
      ${label ? '<div class="ring-label"><div><span class="big num"></span><span class="small"></span></div></div>' : ""}`;
    const arc = container.querySelector(".arc");
    const big = container.querySelector(".big");
    const small = container.querySelector(".small");
    return {
      update(percent, color, text = "", sublabel = "") {
        arc.style.strokeDashoffset = c * (1 - clampPercent(percent) / 100);
        arc.style.stroke = color;
        if (big) big.textContent = text;
        if (small) small.textContent = sublabel;
      },
    };
  }

  // speedometer style gauge (about 250 degrees of sweep)
  function createArcGauge(container, { min, max }) {
    const r = 52;
    const cx = 64;
    const cy = 64;
    const start = Math.PI * 0.8;
    const sweep = Math.PI * 1.4;
    const point = (angle) => [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
    const [x0, y0] = point(start);
    const [x1, y1] = point(start + sweep);
    const trackPath = `M${x0} ${y0} A${r} ${r} 0 1 1 ${x1} ${y1}`;
    container.innerHTML = `
      <svg width="128" height="104" viewBox="0 0 128 104">
        <path d="${trackPath}" fill="none" stroke="var(--track)" stroke-width="10" stroke-linecap="round"/>
        <path class="arc" d="${trackPath}" fill="none" stroke-width="10" stroke-linecap="round"/>
      </svg>
      <div class="g-val num"></div>
      <div class="g-sub num"></div>
      <div class="g-name"></div>`;
    const arc = container.querySelector(".arc");
    const length = arc.getTotalLength();
    arc.style.strokeDasharray = `${length}`;
    arc.style.strokeDashoffset = `${length}`;
    return {
      // value null means "no reading this time": the gauge stays in place and shows a dash
      update(value, color, name, sub) {
        const fraction = value == null ? 0 : Math.min(1, Math.max(0, (value - min) / (max - min)));
        arc.style.strokeDashoffset = `${length * (1 - fraction)}`;
        arc.style.stroke = color;
        container.querySelector(".g-val").textContent = value == null ? "—" : `${Math.round(value)}°C`;
        container.querySelector(".g-sub").textContent = sub;
        container.querySelector(".g-name").textContent = name;
      },
    };
  }

  // LEARN: how many points a sparkline holds. A fixed number of slots keeps
  // the gap between points the same on every refresh, so the line steps
  // left by one slot instead of squeezing or wobbling as the history grows.
  //
  //   60 s of history at a 2 s refresh ──▶ 31 slots (both ends included)
  function sparklineSlots(historySeconds, refreshSeconds) {
    return Math.max(2, Math.round(historySeconds / refreshSeconds) + 1);
  }

  // one line; see drawSparklines for slots and the right-aligned time axis
  function drawSparkline(svg, values, { min, max, color, slots, fill = true, name = "" }) {
    drawSparklines(svg, [{ name, values, color, fill }], { min, max, slots });
  }

  // LEARN: several lines in one small chart, all on the same fixed scale.
  // Each series is { name, values, color, fill }. The chart has a fixed
  // number of slots and the newest point always sits at the right edge, so a
  // history that is still filling up grows in from the right instead of being
  // stretched across the full width. preserveAspectRatio="none" stretches
  // the drawing to the element's width, so the same path fits any card size.
  //
  //   CPU ───────────────────────●   (31 of 31 slots)
  //   GPU             ───────────●   (12 of 31 slots)
  function drawSparklines(svg, series, { min, max, slots }) {
    const width = svg.clientWidth || 200;
    const height = svg.clientHeight || 40;
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("preserveAspectRatio", "none");
    const drawn = series
      .map((s) => ({ ...s, values: slots ? (s.values || []).slice(-slots) : s.values || [] }))
      .filter((s) => s.values.length >= 2);
    const slotCount = slots || Math.max(2, ...drawn.map((s) => s.values.length));
    const span = max - min || 1;
    const y = (v) => height - 2 - ((Math.min(max, Math.max(min, v)) - min) / span) * (height - 4);
    svg.innerHTML = drawn
      .map((s) => {
        const offset = slotCount - s.values.length;
        const x = (i) => ((offset + i) / (slotCount - 1)) * width;
        const line = s.values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
        const area = s.fill
          ? `<path d="${line} L${width} ${height} L${x(0).toFixed(1)} ${height} Z" fill="${s.color}" opacity="0.12"/>`
          : "";
        return `${area}<path d="${line}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
      })
      .join("");
    svg.setAttribute("role", "img");
    svg.setAttribute(
      "aria-label",
      drawn
        .map((s) => {
          const reading = `now ${s.values[s.values.length - 1].toFixed(1)}, peak ${Math.max(...s.values).toFixed(1)}`;
          return s.name ? `${s.name} ${reading}` : reading;
        })
        .join(" · "),
    );
  }

  // LEARN: names from the system (process names, drive names) can contain
  // characters like < and ". Escaping turns them into plain text, so a crafted
  // name can never become markup or script on the page.
  function escapeHtml(text) {
    return String(text ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatBytes(bytes, digits = 1) {
    if (bytes == null) return "—";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = bytes;
    let unit = 0;
    while (value >= 1000 && unit < units.length - 1) {
      value /= 1000;
      unit += 1;
    }
    return `${value.toFixed(unit >= 3 ? digits : 0)} ${units[unit]}`;
  }

  window.BaoCharts = {
    SVG_NS,
    statusColor,
    createRing,
    createArcGauge,
    sparklineSlots,
    drawSparkline,
    drawSparklines,
    escapeHtml,
    formatBytes,
  };
})();
