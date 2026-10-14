/*
 * app.js - Connects the sidebar, the playback timeline and the map.
 *
 * Flow when "Find Parking" is pressed:
 *   1. allocator.js picks the spot (shortest real route, using A*)
 *   2. search.js runs the selected algorithm from the entrance to that spot
 *   3. the timeline replays every node it looked at, then the car drives the route
 */
(() => {
  const $ = (id) => document.getElementById(id);
  const RATE = 2;   // timeline units per second at 1x speed

  const state = {
    algo: "astar",
    vehicle: "regular",
    tool: "dest",                // "dest" = pick a destination spot, "block" = close/open roads
    showValues: true,
    lot: createLot(),
    target: null,                // spot the car is going to
    reason: "",
    run: null,                   // result of the selected algorithm
    all: null,                   // results of all four algorithms (comparison table)
    parked: false,
    t: 0, playing: false, speed: 6,
    hover: null,
  };

  // ------------------------------------------------------------------ controls
  function segmented(el, options, get, set) {
    for (const o of options) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = o.label;
      b.dataset.value = o.value;
      b.addEventListener("click", () => { set(o.value); refresh(); });
      el.appendChild(b);
    }
    el.sync = () => {
      for (const b of el.children) b.setAttribute("aria-pressed", String(b.dataset.value === get()));
    };
    return el;
  }

  const pickers = [
    segmented($("algo-picker"), ALGO_ORDER.map((id) => ({ value: id, label: ALGORITHMS[id].label })),
      () => state.algo, selectAlgorithm),
    segmented($("vehicle-picker"), Object.keys(VEHICLE_NAMES).map((v) => ({ value: v, label: VEHICLE_NAMES[v] })),
      () => state.vehicle, (v) => { state.vehicle = v; }),
    segmented($("tool-picker"), [{ value: "dest", label: "Pick destination" }, { value: "block", label: "Close / open road" }],
      () => state.tool, (v) => { state.tool = v; }),
  ];

  $("run-btn").addEventListener("click", () => findParking(null));
  $("pb-start").addEventListener("click", startFromBeginning);
  $("pb-play").addEventListener("click", togglePlay);
  $("pb-back").addEventListener("click", () => step(-1));
  $("pb-fwd").addEventListener("click", () => step(1));
  $("pb-scrub").addEventListener("input", (e) => { state.playing = false; state.t = Number(e.target.value); });
  $("pb-speed").addEventListener("input", (e) => { state.speed = Number(e.target.value); });
  $("show-values").addEventListener("change", (e) => { state.showValues = e.target.checked; });
  $("reset-btn").addEventListener("click", () => {
    state.lot = createLot();
    clearRun();
    setMessage("Parking lot reset.");
    refresh();
  });

  document.addEventListener("keydown", (e) => {
    if (e.code === "Space") { e.preventDefault(); togglePlay(); }
    else if (e.key === "Enter") { e.preventDefault(); findParking(null); }
    else if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
  });

  // ---------------------------------------------------------------- running
  /** Choose a spot (or use the clicked one) and start the search. */
  function findParking(clickedSpot) {
    clearRun();
    let spot, reason;
    if (clickedSpot) {
      spot = clickedSpot;
      reason = `You picked ${spot.id} on the map.`;
    } else {
      const alloc = allocate(state.lot, state.vehicle);
      if (!alloc.ok) { setMessage(alloc.reason, "error"); refresh(); return; }
      spot = alloc.spot;
      reason = alloc.reason;
    }
    if (runSearch(state.lot, state.lot.entrance, spot.cell, "astar").cost === Infinity) {
      setMessage(`${spot.id} cannot be reached from the entrance (roads closed).`, "error");
      refresh();
      return;
    }
    spot.status = "reserved";               // nobody else can take it now
    state.target = spot;
    state.reason = reason;
    state.all = {};
    for (const id of ALGO_ORDER) state.all[id] = runSearch(state.lot, state.lot.entrance, spot.cell, id);
    state.run = state.all[state.algo];
    setMessage(null);
    startFromBeginning();
  }

  /** Switching algorithm replays the search to the same spot. */
  function selectAlgorithm(id) {
    state.algo = id;
    if (state.all && !state.parked) {
      state.run = state.all[id];
      startFromBeginning();
    }
  }

  function startFromBeginning() {
    if (!state.run) { setMessage("Press Find Parking first.", ""); refresh(); return; }
    state.t = 0;
    state.playing = true;
    refresh();
  }

  /** Free a reserved (not yet parked) spot and clear the search from the map. */
  function clearRun() {
    if (state.target && !state.parked && state.target.status === "reserved") state.target.status = "available";
    Object.assign(state, { target: null, run: null, all: null, parked: false, t: 0, playing: false });
  }

  const total = () => (state.run ? state.run.steps.length + (state.run.found ? state.run.cost * ROUTE_UNITS : 0) : 0);

  function togglePlay() {
    if (!state.run) { findParking(null); return; }
    if (!state.playing && state.t >= total()) state.t = 0;
    state.playing = !state.playing;
    refresh();
  }

  function step(dir) {
    if (!state.run) return;
    state.playing = false;
    const exploring = state.t < state.run.steps.length || (dir < 0 && state.t <= state.run.steps.length);
    const unit = exploring ? 1 : ROUTE_UNITS;
    state.t = Math.max(0, Math.min(total(), Math.round(state.t) + dir * unit));
    if (state.t >= total()) finish();
    refresh();
  }

  function finish() {
    if (state.parked) return;
    if (state.run.found) {
      state.target.status = "occupied";
      state.parked = true;
      setMessage(`Parked in ${state.target.id}. Press Find Parking for the next car.`, "ok");
    } else {
      state.target.status = "available";     // the car never arrived, so free the spot again
      const s = state.run.stuckAt;
      setMessage(`Hill climbing got stuck at (${s.r}, ${s.c}): no neighbour has a smaller h(n). ` +
                 `This is a local minimum. Try A*.`, "error");
    }
  }

  // ------------------------------------------------------------- map clicks
  const canvas = $("canvas");
  canvas.addEventListener("click", (e) => onMapClick(cellFromPoint(canvas, state.lot, e.offsetX, e.offsetY)));
  canvas.addEventListener("mousemove", (e) => {
    state.hover = { cell: cellFromPoint(canvas, state.lot, e.offsetX, e.offsetY), x: e.clientX, y: e.clientY };
  });
  canvas.addEventListener("mouseleave", () => { state.hover = null; });

  function onMapClick(cell) {
    if (!cell) return;
    if (state.tool === "dest" && cell.kind === "spot") {
      if (cell.spot.status === "available" || (cell.spot === state.target && !state.parked)) findParking(cell.spot);
      else setMessage(`${cell.spot.id} is occupied. Pick a green (free) spot.`, "error");
    } else if (state.tool === "block" && cell.kind === "road") {
      clearRun();
      cell.blocked = !cell.blocked;
      setMessage(`Road (${cell.r}, ${cell.c}) ${cell.blocked ? "closed" : "opened"}. Press Find Parking to search again.`);
    } else if (state.tool === "block") {
      setMessage("Click a road cell to close or open it.");
    } else {
      setMessage("Click a green parking spot to send the car there.");
    }
    refresh();
  }

  // ----------------------------------------------------------------- panels
  function setMessage(text, kind = "") {
    const el = $("message");
    el.hidden = !text;
    el.textContent = text || "";
    el.className = "message-banner " + kind;
  }

  /** Re-render the parts that change only when the user does something. */
  function refresh() {
    pickers.forEach((p) => p.sync());
    const info = ALGORITHMS[state.algo];
    $("algo-rule").textContent = info.rule;
    $("algo-desc").textContent = info.desc;
    $("caption").textContent = info.name;
    $("calc-title").textContent = info.usesHeuristic ? "Heuristic function h(n)" : "How DFS chooses";
    $("show-values-label").textContent = "Show g, h values on the map";
    $("value-key").innerHTML = {
      astar: `Each cell shows <b class="kg">g</b> + <b class="kh">h</b> · <b class="kg">g</b> = moves so far · <b class="kh">h</b> = estimate to goal · f is their sum`,
      bestfirst: `<b class="kg">g</b> moves so far · <b class="kh">h</b> estimate to goal · <b>centre</b> = h (what it sorts by)`,
      hill: `<b class="kg">g</b> moves so far · <b class="kh">h</b> estimate to goal · <b>centre</b> = h (what it compares)`,
      dfs: `<b class="kg">g</b> depth (moves so far) · <b>centre</b> = visit order · DFS has no h`,
    }[state.algo];
    renderSummary();
    renderCompare();
    const lot = state.lot;
    $("footer-stats").textContent = `${lot.spots.length} spots · ${countSpots(lot, "available")} free · ` +
      `${countSpots(lot, "occupied")} occupied`;
  }

  function renderSummary() {
    const el = $("summary");
    if (!state.run) { el.hidden = true; return; }
    el.hidden = false;
    const r = state.run, spot = state.target;
    el.innerHTML = `
      <div class="summary-top">
        <div class="summary-spot">${spot.id}<small>${SPOT_TYPE_NAMES[spot.type]} spot</small></div>
        ${r.found ? `<span class="badge">Route found</span>` : `<span class="badge red">Stuck</span>`}
      </div>
      <div class="summary-meta">${ALGORITHMS[state.algo].name}: route <b>${r.found ? r.cost + " moves" : "—"}</b>
        · <b>${r.expanded}</b> nodes explored</div>
      <div class="summary-why">${state.reason}</div>`;
  }

  function renderCompare() {
    const sec = $("sec-compare");
    if (!state.all) { sec.hidden = true; return; }
    sec.hidden = false;
    const best = state.all.astar.cost;      // A* is optimal, so it is the reference
    const rows = ALGO_ORDER.map((id) => {
      const r = state.all[id];
      const result = !r.found ? `<span class="no">Stuck ✗</span>`
        : r.cost === best ? `<span class="yes">Shortest ✓</span>`
        : `<span class="warn">+${r.cost - best} longer</span>`;
      return `<tr data-algo="${id}" class="${id === state.algo ? "active" : ""}">
        <td>${ALGORITHMS[id].label}</td><td class="num">${r.expanded}</td>
        <td class="num">${r.found ? r.cost : "—"}</td><td>${result}</td></tr>`;
    }).join("");
    $("compare-table").innerHTML =
      `<thead><tr><th>Algorithm</th><th class="num">Explored</th><th class="num">Route</th><th>Result</th></tr></thead>` +
      `<tbody>${rows}</tbody>`;
    for (const tr of $("compare-table").querySelectorAll("tbody tr")) {
      tr.addEventListener("click", () => { selectAlgorithm(tr.dataset.algo); refresh(); });
    }
  }

  /** The live "calculation" box: shows h(n) being computed for the current node. */
  function renderCalc(view) {
    const info = ALGORITHMS[state.algo];
    const goal = state.target ? state.target.cell : null;
    const formula = `<div class="formula">h(n) = |n.row − goal.row| + |n.col − goal.col|</div>`;
    let html;
    if (!goal) {
      html = info.usesHeuristic
        ? `${formula}<p class="hint">Manhattan distance: the fewest moves if there were no obstacles. ` +
          `Press <b>Find Parking</b> to see it live.</p>`
        : `<p class="hint">DFS uses <b>no heuristic</b>. It keeps a stack and always continues from the newest node.</p>`;
    } else {
      const st = view && view.current;
      const g = `Goal: <b>${state.target.id}</b> at (${goal.r}, ${goal.c})`;
      if (!st) {
        html = (info.usesHeuristic ? formula : "") + `<div class="calc-line">${g}</div>` +
               `<p class="hint">Press play or → to start.</p>`;
      } else if (!info.usesHeuristic) {
        html = `<div class="calc-line">${g}</div>
          <div class="calc-line">Visiting node <b>#${view.k}</b> = (${st.cell.r}, ${st.cell.c})</div>
          <div class="calc-line">Depth (moves from entrance) = <b>${st.g}</b></div>
          <div class="calc-line">Stack size = <b>${st.openSize ?? 0}</b></div>
          <p class="hint">No h(n) used: DFS does not know where the goal is.</p>`;
      } else {
        const n = st.cell;
        let lines = `${formula}<div class="calc-line">${g}</div>
          <div class="calc-line">Current n = (${n.r}, ${n.c})</div>
          <div class="calc-line big">h(n) = |${n.r} − ${goal.r}| + |${n.c} − ${goal.c}| = <b>${st.h}</b></div>`;
        if (state.algo === "astar") {
          lines += `<div class="calc-line big">f(n) = g + h = ${st.g} + ${st.h} = <b>${st.g + st.h}</b></div>`;
        } else if (state.algo === "bestfirst") {
          lines += `<div class="calc-line big">f(n) = h(n) = <b>${st.h}</b></div>`;
        } else if (state.algo === "hill") {
          const opts = st.options.map((o) =>
            `<span class="${o.cell === st.chosen ? "chosen" : ""}">(${o.cell.r},${o.cell.c}) h=${o.h}</span>`).join(" ");
          lines += `<div class="calc-line">Neighbours: ${opts || "none"}</div>` +
            (st.stuck ? `<div class="calc-line no">No neighbour has h &lt; ${st.h}: stuck (local minimum)</div>`
             : st.chosen ? `<div class="calc-line">Move to the smallest h</div>` : "");
        }
        html = lines;
      }
    }
    if ($("calc").dataset.html !== html) { $("calc").innerHTML = html; $("calc").dataset.html = html; }
  }

  function renderLive(view) {
    const T = total();
    const scrub = $("pb-scrub");
    scrub.max = Math.max(1, T);
    scrub.value = state.t;
    for (const id of ["pb-back", "pb-fwd", "pb-scrub", "pb-start"]) $(id).disabled = !state.run;
    $("pb-play-icon").innerHTML = state.playing ? '<path d="M6 5h4v14H6zm8 0h4v14h-4z"/>' : '<path d="M8 5v14l11-7z"/>';
    $("pb-speed-value").textContent = `${state.speed}x`;
    const n = state.run ? state.run.steps.length : 0;
    $("pb-step").textContent = !state.run ? "—" : `${Math.min(n, Math.floor(state.t))}/${n}`;
    $("status").innerHTML = !view ? `<b>${countSpots(state.lot, "available")}</b> free spots`
      : view.exploring ? `Exploring · <b>${view.k}</b> nodes`
      : state.run.found ? `Route · <b>${state.run.cost}</b> moves · ${state.run.expanded} nodes explored`
      : `Stuck after <b>${view.k}</b> nodes`;
    renderCalc(view);
  }

  function renderTooltip(view) {
    const tip = $("tooltip");
    const h = state.hover;
    if (!h || !h.cell || h.cell.kind === "wall") { tip.hidden = true; return; }
    const c = h.cell;
    let text = c.kind === "spot" ? `${c.spot.id} · ${SPOT_TYPE_NAMES[c.spot.type]} · ${c.spot.status}`
      : c.kind === "pillar" ? "Pillar" : c.kind === "entrance" ? "Entrance" : c.kind === "exit" ? "Exit"
      : c.blocked ? "Road closed" : `Road (${c.r}, ${c.c})`;
    if (state.target && isDrivable(c)) text += ` · <code>h = ${heuristic(c, state.target.cell)}</code>`;
    const st = view && view.closed.get(c);
    if (st && state.algo === "astar") text += ` <code>g = ${st.g}  f = ${st.g + st.h}</code>`;
    tip.innerHTML = text;
    tip.hidden = false;
    const stage = $("stage").getBoundingClientRect();
    let x = h.x - stage.left + 14;
    if (x + tip.offsetWidth > stage.width - 8) x = h.x - stage.left - tip.offsetWidth - 10;
    tip.style.left = x + "px";
    tip.style.top = h.y - stage.top + 16 + "px";
  }

  // --------------------------------------------------------------- main loop
  let last = performance.now();
  function frame(now) {
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    const T = total();
    if (state.playing && T) {
      state.t = Math.min(T, state.t + dt * RATE * state.speed);
      if (state.t >= T) { state.playing = false; finish(); refresh(); }
    }
    const labels = state.showValues ? (ALGORITHMS[state.algo].usesHeuristic ? "h" : "order") : null;
    const view = drawLot(canvas, state.lot, {
      run: state.run, t: state.t, target: state.target, parked: state.parked, algo: state.algo,
      labels, hover: state.hover ? state.hover.cell : null,
    });
    renderLive(view);
    renderTooltip(view);
    requestAnimationFrame(frame);
  }

  refresh();
  setMessage("Choose an algorithm and press Find Parking, or click any green spot on the map.");
  requestAnimationFrame(frame);
})();
