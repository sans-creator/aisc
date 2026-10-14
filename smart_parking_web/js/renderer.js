/*
 * renderer.js - Draws the parking lot and the search on an HTML <canvas>.
 * It only READS state; it never changes the simulation.
 */

const COLORS = {
  outside: "#EEF2F6", outsideDot: "#E1E7EE",
  road: "#FFFFFF", roadLine: "#E6E9ED", spotBase: "#F4F6F8",
  available: "#E6F4EA", availableEdge: "#34A853",
  occupied: "#FCE8E6", occupiedEdge: "#EA4335",
  reserved: "#D3E3FD", reservedEdge: "#1A73E8",
  pillar: "#5F6368", blocked: "#EA4335",
  explored: "rgba(251, 188, 4, 0.32)", frontier: "#F29900", current: "#202124",
  ink: "#202124", muted: "#5F6368", faint: "#A8AEB5",
  ev: "#12B5CB", accessible: "#1A73E8",
  start: "#188038", route: "#1A73E8", fail: "#D93025", parkedCar: "#9AA0A6",
};
const ROUTE_UNITS = 4;   // timeline units per route cell (the car drives slower than the replay)

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/** Size the canvas for the screen and work out where each cell goes. */
function layoutCanvas(canvas, lot) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const pad = 24;
  const size = Math.max(8, Math.floor(Math.min((w - 2 * pad) / lot.cols, (h - 2 * pad) / lot.rows)));
  const geom = { ctx, w, h, size,
    ox: Math.round((w - size * lot.cols) / 2), oy: Math.round((h - size * lot.rows) / 2) };
  canvas._geom = geom;
  return geom;
}

function cellFromPoint(canvas, lot, x, y) {
  const g = canvas._geom;
  if (!g) return null;
  return cellAt(lot, Math.floor((y - g.oy) / g.size), Math.floor((x - g.ox) / g.size));
}

/** What part of the search is visible at timeline position t. */
function searchView(run, t) {
  const k = Math.min(Math.floor(t), run.steps.length);
  const closed = new Map();       // cell -> step (in visiting order)
  const frontier = new Set();
  const gKnown = new Map();       // cell -> g, for every cell the search has reached
  for (let i = 0; i < k; i++) {
    const st = run.steps[i];
    closed.set(st.cell, st);
    gKnown.set(st.cell, st.g);
    for (const nb of st.added) {
      frontier.add(nb);
      if (!closed.has(nb)) gKnown.set(nb, st.g + 1);   // one more move than its parent
    }
  }
  for (const c of closed.keys()) frontier.delete(c);
  const routeProgress = run.found ? Math.max(0, Math.min(run.cost, (t - run.steps.length) / ROUTE_UNITS)) : 0;
  return { k, closed, frontier, gKnown, current: k > 0 ? run.steps[k - 1] : null,
           exploring: k < run.steps.length, routeProgress, done: run.found && routeProgress >= run.cost };
}

function drawLot(canvas, lot, view) {
  const { ctx, w, h, size: s, ox, oy } = layoutCanvas(canvas, lot);
  const X = (c) => ox + c * s, Y = (r) => oy + r * s;
  const center = (cell) => [X(cell.c) + s / 2, Y(cell.r) + s / 2];
  const fontSize = Math.max(9, Math.round(s * 0.2));

  // 1. Ground
  ctx.fillStyle = COLORS.outside;
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = COLORS.outsideDot;
  for (let x = 10; x < w; x += 18) for (let y = 10; y < h; y += 18) ctx.fillRect(x, y, 1.5, 1.5);

  // 2. Cells
  for (const row of lot.cells) {
    for (const cell of row) {
      if (cell.kind === "wall") continue;
      const x = X(cell.c), y = Y(cell.r);
      ctx.fillStyle = cell.kind === "spot" ? COLORS.spotBase : COLORS.road;
      ctx.fillRect(x, y, s, s);
      if (cell.kind === "spot") { drawSpotBase(ctx, cell.spot, x, y, s); continue; }
      ctx.strokeStyle = COLORS.roadLine;
      ctx.lineWidth = 1;
      ctx.strokeRect(x + 0.5, y + 0.5, s - 1, s - 1);
      if (cell.kind === "pillar") {
        ctx.fillStyle = COLORS.pillar;
        roundRect(ctx, x + s * 0.28, y + s * 0.28, s * 0.44, s * 0.44, s * 0.08);
        ctx.fill();
      } else if (cell.blocked) {
        drawBlocked(ctx, x, y, s);
      }
    }
  }

  // 3. Search overlay
  const run = view.run;
  const sv = run ? searchView(run, view.t) : null;
  if (sv) {
    for (const cell of sv.closed.keys()) {
      if (cell.kind === "spot") continue;
      ctx.fillStyle = COLORS.explored;
      ctx.fillRect(X(cell.c) + 1, Y(cell.r) + 1, s - 2, s - 2);
    }
    ctx.strokeStyle = COLORS.frontier;
    ctx.lineWidth = 2;
    for (const cell of sv.frontier) {
      if (cell.kind === "spot") continue;
      roundRect(ctx, X(cell.c) + 4, Y(cell.r) + 4, s - 8, s - 8, 4);
      ctx.stroke();
    }
  }

  // 4. Values on cells
  //    top-left  : g(n)  (only once the search has reached the cell)
  //    top-right : h(n)  (heuristic searches only - it is known for every cell)
  //    centre    : the value the algorithm sorts by (A*: f = g + h, Best-First / Hill: h,
  //                DFS: visit order)
  if (view.target && view.labels) {
    const goal = view.target.cell;
    const small = `600 ${Math.max(8, Math.round(s * 0.17))}px "Cascadia Mono", Consolas, monospace`;
    const order = new Map();
    if (sv) [...sv.closed.keys()].forEach((c, i) => order.set(c, i + 1));
    for (const row of lot.cells) {
      for (const cell of row) {
        if (!isDrivable(cell)) continue;
        const x = X(cell.c), y = Y(cell.r);
        const seen = sv && sv.closed.has(cell);
        const g = sv ? sv.gKnown.get(cell) : undefined;
        const h = heuristic(cell, goal);

        // A*: once g is known, the centre shows "g+h" (e.g. 3+4) instead of the sum
        const astarSum = view.algo === "astar" && g !== undefined;

        ctx.font = small;
        ctx.textBaseline = "top";
        if (g !== undefined && !astarSum) {
          ctx.textAlign = "left";
          ctx.fillStyle = "#188038";
          ctx.fillText(`g${g}`, x + 3, y + 3);
        }
        if (view.labels === "h" && !astarSum) {
          ctx.textAlign = "right";
          ctx.fillStyle = "#C5221F";
          ctx.fillText(`h${h}`, x + s - 3, y + 3);
        }

        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        const weight = seen ? 700 : 500;
        if (astarSum) {
          // "g" in green, "+", "h" in red
          ctx.font = `${weight} ${fontSize + 1}px "Cascadia Mono", Consolas, monospace`;
          const gs = String(g), hs = String(h);
          const wG = ctx.measureText(gs).width, wP = ctx.measureText("+").width, wH = ctx.measureText(hs).width;
          let cx = x + s / 2 - (wG + wP + wH) / 2;
          const cy = y + s / 2;
          ctx.textAlign = "left";
          ctx.fillStyle = "#188038"; ctx.fillText(gs, cx, cy); cx += wG;
          ctx.fillStyle = COLORS.ink; ctx.fillText("+", cx, cy); cx += wP;
          ctx.fillStyle = "#C5221F"; ctx.fillText(hs, cx, cy);
        } else {
          const main = view.labels === "order" ? order.get(cell) : view.algo === "astar" ? null : h;
          if (main !== null && main !== undefined) {
            ctx.font = `${weight} ${fontSize + 1}px "Cascadia Mono", Consolas, monospace`;
            ctx.fillStyle = seen ? COLORS.ink : COLORS.faint;
            ctx.fillText(String(main), x + s / 2, y + s * 0.6);
          }
        }
      }
    }
  }

  if (sv && sv.current && sv.exploring) {
    ctx.strokeStyle = COLORS.current;
    ctx.lineWidth = 2.5;
    roundRect(ctx, X(sv.current.cell.c) + 2, Y(sv.current.cell.r) + 2, s - 4, s - 4, 5);
    ctx.stroke();
  }

  // 5. Route (white casing + blue line), or the failed hill-climbing walk in red
  if (sv && sv.routeProgress > 0) {
    drawLine(ctx, partialPath(run.path, sv.routeProgress).map(center), s, COLORS.route, false);
  }
  if (sv && !run.found && !sv.exploring && run.stuckAt) {
    drawLine(ctx, run.path.map(center), s, COLORS.fail, true);
    const [cx, cy] = center(run.stuckAt);
    ctx.strokeStyle = COLORS.fail;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(cx, cy, s * 0.42, 0, Math.PI * 2);
    ctx.stroke();
  }

  // 6. Spot labels and parked cars
  for (const spot of lot.spots) {
    const x = X(spot.cell.c), y = Y(spot.cell.r);
    if (spot.status === "occupied") {
      const roadAbove = isDrivable(cellAt(lot, spot.cell.r - 1, spot.cell.c));
      drawCar(ctx, x + s / 2, y + s / 2, s, roadAbove ? -90 : 90, COLORS.parkedCar);
    }
    drawSpotLabels(ctx, spot, x, y, s);
  }

  // 7. Entrance / exit pins, target ring, moving car
  drawPin(ctx, ...center(lot.entrance), s, COLORS.start, "IN");
  drawPin(ctx, ...center(lot.exit), s, COLORS.muted, "OUT");
  if (view.target && view.target.status !== "occupied") {
    const [tx, ty] = center(view.target.cell);
    const pulse = 1 + 0.08 * Math.sin(performance.now() / 180);
    ctx.strokeStyle = COLORS.route;
    ctx.lineWidth = 2.5;
    roundRect(ctx, tx - (s / 2) * pulse, ty - (s / 2) * pulse, s * pulse, s * pulse, 8);
    ctx.stroke();
  }
  if (sv && sv.routeProgress > 0 && !view.parked) {
    const [pos, heading] = pointOnPath(run.path, sv.routeProgress);
    drawCar(ctx, ...center(pos), s, heading, COLORS.route);
  }

  if (view.hover && view.hover.kind !== "wall") {
    ctx.strokeStyle = COLORS.ink;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(X(view.hover.c) + 0.5, Y(view.hover.r) + 0.5, s - 1, s - 1);
  }
  return sv;
}

function drawLine(ctx, pts, s, color, dashed) {
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const [width, stroke] of [[s * 0.3, "#FFFFFF"], [s * 0.16, color]]) {
    ctx.setLineDash(dashed && stroke !== "#FFFFFF" ? [s * 0.2, s * 0.2] : []);
    ctx.strokeStyle = stroke;
    ctx.lineWidth = width;
    ctx.beginPath();
    pts.forEach(([px, py], i) => (i ? ctx.lineTo(px, py) : ctx.moveTo(px, py)));
    ctx.stroke();
  }
  ctx.setLineDash([]);
}

function partialPath(path, progress) {
  const whole = Math.floor(progress);
  const pts = path.slice(0, whole + 1);
  const frac = progress - whole;
  if (frac > 0 && whole + 1 < path.length) {
    const a = path[whole], b = path[whole + 1];
    pts.push({ r: a.r + (b.r - a.r) * frac, c: a.c + (b.c - a.c) * frac });
  }
  return pts;
}

function pointOnPath(path, progress) {
  const i = Math.min(Math.floor(progress), path.length - 2);
  const a = path[i], b = path[i + 1];
  const frac = Math.min(1, progress - i);
  const heading = Math.atan2(-(b.r - a.r), b.c - a.c) * 180 / Math.PI;
  return [{ r: a.r + (b.r - a.r) * frac, c: a.c + (b.c - a.c) * frac }, heading];
}

function drawSpotBase(ctx, spot, x, y, s) {
  const inset = Math.max(2, s * 0.06);
  ctx.fillStyle = COLORS[spot.status];
  roundRect(ctx, x + inset, y + inset, s - 2 * inset, s - 2 * inset, s * 0.12);
  ctx.fill();
  ctx.strokeStyle = COLORS[spot.status + "Edge"];
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

function drawSpotLabels(ctx, spot, x, y, s) {
  const fs = Math.max(8, Math.round(s * 0.19));
  ctx.font = `600 ${fs}px "Segoe UI", Roboto, sans-serif`;
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  ctx.fillStyle = COLORS.muted;
  ctx.fillText(spot.id, x + s * 0.12, y + s * 0.1);
  if (spot.type !== "regular") {
    ctx.fillStyle = spot.type === "ev" ? COLORS.ev : COLORS.accessible;
    roundRect(ctx, x + s * 0.1, y + s - fs - s * 0.18, fs * 1.9, fs + 4, 3);
    ctx.fill();
    ctx.fillStyle = "#FFFFFF";
    ctx.textAlign = "center";
    ctx.fillText(spot.type === "ev" ? "EV" : "♿", x + s * 0.1 + fs * 0.95, y + s - fs - s * 0.18 + 2);
  }
}

function drawBlocked(ctx, x, y, s) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(x + 2, y + 2, s - 4, s - 4);
  ctx.clip();
  ctx.strokeStyle = COLORS.blocked;
  ctx.lineWidth = s * 0.12;
  for (let d = -s; d < s * 2; d += s * 0.32) {
    ctx.beginPath();
    ctx.moveTo(x + d, y + s);
    ctx.lineTo(x + d + s, y);
    ctx.stroke();
  }
  ctx.restore();
}

function drawPin(ctx, cx, cy, s, color, label) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(cx, cy, s * 0.3, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "#FFFFFF";
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.fillStyle = "#FFFFFF";
  ctx.font = `700 ${Math.max(7, s * 0.17)}px "Segoe UI", sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, cx, cy + 0.5);
}

function drawCar(ctx, cx, cy, s, heading, color) {
  const L = s * 0.62, W = s * 0.36;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(-heading * Math.PI / 180);
  ctx.shadowColor = "rgba(60,64,67,0.35)";
  ctx.shadowBlur = 4;
  ctx.shadowOffsetY = 1;
  ctx.fillStyle = color;
  roundRect(ctx, -L / 2, -W / 2, L, W, W * 0.35);
  ctx.fill();
  ctx.shadowColor = "transparent";
  ctx.fillStyle = "rgba(255,255,255,0.85)";
  roundRect(ctx, L * 0.12, -W * 0.36, L * 0.16, W * 0.72, 2);
  ctx.fill();
  ctx.fillStyle = "rgba(255,255,255,0.55)";
  roundRect(ctx, -L * 0.36, -W * 0.32, L * 0.1, W * 0.64, 2);
  ctx.fill();
  ctx.restore();
}
