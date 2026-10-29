// LEARN: YOU ARE HERE
//   index.html loads THIS FILE ▶ sets window.BaoCharts
//   ▶ each tool's view.js draws its rings, gauges and line charts with it
//   read next → app/ui/shell.js

// Shared hand-drawn SVG charts for every tool: ring, arc gauge, sparkline.
//
// LEARN: a ring is one SVG circle with a dashed stroke. The dash is as long
// as the whole circle; shifting it (stroke-dashoffset) reveals only a part.
//
//   circumference = 2πr
//   visible part  = circumference × percent / 100
//   dashoffset    = circumference − visible part
//
//   0 %  ○  offset = whole circle (nothing shows)
//   50 % ◐  offset = half
//   100% ●  offset = 0 (all shows)
//
// Updating the offset (instead of redrawing) lets a CSS transition glide the
// ring to its new value.
//
// LEARN: (() => { … })() = run once now, keep names private (see icons.js)
(() => {
  const SVG_NS = "http://www.w3.org/2000/svg";

  // LEARN: pick green / yellow / red for a value
  //   called by → tool pages (e.g. CPU 85 % → warning colour)
  //   gives back → a CSS colour, e.g. "var(--warning)"
  function statusColor(value, warnAt, criticalAt) {
    // if with one line and no { } → only that line belongs to the if
    if (value >= criticalAt) return "var(--critical)";
    if (value >= warnAt) return "var(--warning)";
    return "var(--good)";
  }

  // keep a percent between 0 and 100; missing value → 0
  function clampPercent(value) {
    return Math.min(100, Math.max(0, value || 0));
  }

  // live ring that animates between values; built once, then only updated.
  // dashed draws a dotted track (muted drives); label: false leaves out the
  // number in the middle (the small rings in top apps rows).
  //
  // LEARN: called by → tool pages, once per ring when the page is built
  //   gives back → an object with update(...) to call on every refresh
  //   industry term: "factory function" (a function that builds an object)
  //
  // LEARN: { size, stroke, dashed = false, label = true } in the inputs
  //   = "destructuring": the caller passes ONE object, the fields become names
  //   createRing(el, { size: 120, stroke: 10 })
  //   ≈ Python def create_ring(el, *, size, stroke, dashed=False, label=True)
  function createRing(container, { size, stroke, dashed = false, label = true }) {
    const r = (size - stroke) / 2;
    const c = 2 * Math.PI * r;
    // LEARN: cond ? a : b → a if cond, else b ≈ Python "a if cond else b"
    const dash = dashed ? 'stroke-dasharray="3 3"' : "";
    container.classList.add("ring-wrap");
    // LEARN: innerHTML = replace what's inside the element with this HTML text
    //   SVG starts at 3 o'clock → rotate(-90deg) → the ring starts at 12
    //   circle 1 = grey track, circle 2 (class "arc") = coloured part
    container.innerHTML = `
      <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="transform:rotate(-90deg)">
        <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--track)" stroke-width="${stroke}" ${dash}/>
        <circle class="arc" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${stroke}"
          stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${c}"/>
      </svg>
      ${label ? '<div class="ring-label"><div><span class="big num"></span><span class="small"></span></div></div>' : ""}`;
    // LEARN: querySelector(".arc") → the first element inside with class arc
    //   (null if there's none, e.g. no label → big / small are null)
    const arc = container.querySelector(".arc");
    const big = container.querySelector(".big");
    const small = container.querySelector(".small");
    // LEARN: the elements are found ONCE here; update() keeps using them
    //   industry term: "closure" (an inner function remembers outer names)
    return {
      // update(…) { … } inside an object = a method on it
      update(percent, color, text = "", sublabel = "") {
        // LEARN: element.style.x = … → set one CSS property on that element
        arc.style.strokeDashoffset = c * (1 - clampPercent(percent) / 100);
        arc.style.stroke = color;
        // textContent = the plain text inside (never read as HTML → safe)
        if (big) big.textContent = text;
        if (small) small.textContent = sublabel;
      },
    };
  }

  // speedometer style gauge (about 250 degrees of sweep)
  //
  // LEARN: called by → tool pages (temperature)
  //   gives back → { update(value, color, name, sub) }
  //
  //        ╭───────╮
  //       ╱         ╲      starts bottom-left, ends bottom-right
  //      ●           ●     angles in radians: π = 180°
  //
  function createArcGauge(container, { min, max }) {
    const r = 52;
    const cx = 64;
    const cy = 64;
    const start = Math.PI * 0.8;
    const sweep = Math.PI * 1.4;
    // LEARN: (angle) => [...] = arrow function: angle in, [x, y] point out
    //   const [x0, y0] = point(...) → unpack the two values ≈ Python x0, y0 = …
    const point = (angle) => [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
    const [x0, y0] = point(start);
    const [x1, y1] = point(start + sweep);
    // SVG path text: M = move to the start, A = draw an arc to the end
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
    // same dash trick as the ring, with the arc's measured length
    const length = arc.getTotalLength();
    arc.style.strokeDasharray = `${length}`;
    arc.style.strokeDashoffset = `${length}`;
    return {
      // value null means "no reading this time": the gauge stays in place and shows a dash
      update(value, color, name, sub) {
        // LEARN: == null → true for both null and undefined (JS's two "None"s)
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
  //
  //   sparkline (industry term) = a tiny line chart with no axes
  function sparklineSlots(historySeconds, refreshSeconds) {
    return Math.max(2, Math.round(historySeconds / refreshSeconds) + 1);
  }

  // one line; see drawSparklines for slots and the right-aligned time axis
  // called by → tool pages, every refresh
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
  //
  //   called by → drawSparkline, and tool pages, every refresh
  //   output → redraws the <svg> it was given (nothing returned)
  function drawSparklines(svg, series, { min, max, slots }) {
    // clientWidth = the element's width on screen right now (0 if hidden)
    const width = svg.clientWidth || 200;
    const height = svg.clientHeight || 40;
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("preserveAspectRatio", "none");
    // LEARN: .map(f) → a new array with f applied to each item
    //   ≈ Python [f(s) for s in series]
    //   .filter(f) → keep only items where f is true
    //   ≈ Python [s for s in series if f(s)]
    //   { ...s, values: … } = copy of s with "values" replaced ≈ {**s, "values": …}
    //   .slice(-slots) → the last "slots" items ≈ Python values[-slots:]
    //   step by step:
    //     for each series → keep only its newest points that fit
    //     then drop series with fewer than 2 points (can't draw a line)
    const drawn = series
      .map((s) => ({ ...s, values: slots ? (s.values || []).slice(-slots) : s.values || [] }))
      .filter((s) => s.values.length >= 2);
    // ...array inside Math.max(…) → spread the array into separate arguments
    const slotCount = slots || Math.max(2, ...drawn.map((s) => s.values.length));
    const span = max - min || 1;
    // value → y on screen (SVG y grows DOWN, so bigger value = smaller y)
    //   2 px kept free at the top and bottom so the line isn't cut
    const y = (v) => height - 2 - ((Math.min(max, Math.max(min, v)) - min) / span) * (height - 4);
    svg.innerHTML = drawn
      .map((s) => {
        // empty slots on the left → the line starts further right
        const offset = slotCount - s.values.length;
        const x = (i) => ((offset + i) / (slotCount - 1)) * width;
        // path text: "M x y" for the first point, "L x y" (line to) for the rest
        //   .join(" ") → glue the pieces with spaces ≈ Python " ".join(…)
        const line = s.values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
        // optional faint fill: the line, then down to the bottom, back, close (Z)
        const area = s.fill
          ? `<path d="${line} L${width} ${height} L${x(0).toFixed(1)} ${height} Z" fill="${s.color}" opacity="0.12"/>`
          : "";
        return `${area}<path d="${line}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
      })
      .join("");
    // LEARN: role + aria-label = a text version of the chart for screen
    //   readers (industry term: "accessibility", a11y)
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
  //
  //   industry term: "HTML escaping" (stops "XSS" = injected script)
  //   called by → tool pages, before putting any name into innerHTML
  //   a ?? b → b only when a is null / undefined
  function escapeHtml(text) {
    return String(text ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  // LEARN: 1234567890 → "1.2 GB" (1000-based, like macOS Finder)
  //   called by → tool pages (storage sizes)
  function formatBytes(bytes, digits = 1) {
    if (bytes == null) return "—";
    const units = ["B", "KB", "MB", "GB", "TB"];
    // let = a name that CAN change later (const can't)
    let value = bytes;
    let unit = 0;
    // divide by 1000 until the number is small, moving up one unit each time
    while (value >= 1000 && unit < units.length - 1) {
      value /= 1000;
      unit += 1;
    }
    // GB and up → 1 decimal; smaller units → whole numbers
    return `${value.toFixed(unit >= 3 ? digits : 0)} ${units[unit]}`;
  }

  // the only names other files can use (see icons.js for how window works)
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
