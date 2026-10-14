const ALGORITHMS = {
  astar: {
    name: "A* Search",
    label: "A*",
    usesHeuristic: true,
    rule: "f(n) = g(n) + h(n)",
    desc: "Real cost so far (g) + estimate to the spot (h). Always finds the shortest route.",
  },
  bestfirst: {
    name: "Best-First Search",
    label: "Best-First",
    usesHeuristic: true,
    rule: "f(n) = h(n)",
    desc: "Always expands the node that looks closest to the spot. Fast, but not always shortest.",
  },
  hill: {
    name: "Hill Climbing",
    label: "Hill Climb",
    usesHeuristic: true,
    rule: "next = neighbour with smallest h(n)",
    desc: "Looks only at its neighbours and never goes back. Can get stuck (local minimum).",
  },
  dfs: {
    name: "Depth-First Search",
    label: "DFS",
    usesHeuristic: false,
    rule: "stack: last in, first out",
    desc: "No heuristic. Goes as deep as possible, then backtracks. Route is usually long.",
  },
};
const ALGO_ORDER = ["astar", "bestfirst", "hill", "dfs"];

function runSearch(lot, start, goal, algoId) {
  const t0 = performance.now();
  const result =
    algoId === "hill"
      ? hillClimbing(lot, start, goal)
      : algoId === "dfs"
        ? depthFirst(lot, start, goal)
        : bestFirst(lot, start, goal, algoId === "astar");
  result.algoId = algoId;
  result.cost = result.found ? result.path.length - 1 : Infinity;
  result.timeMs = performance.now() - t0;
  return result;
}

function buildPath(parent, goal) {
  const path = [];
  for (let c = goal; c !== undefined; c = parent.get(c)) path.push(c);
  return path.reverse();
}

/* ---------------------------------------------------------------- A* and Best-First
 * Same loop; the only difference is the priority:
 *   A*          priority = g + h
 *   Best-First  priority = h
 */
function bestFirst(lot, start, goal, useG) {
  const open = []; // open set: nodes waiting to be expanded
  const g = new Map([[start, 0]]); // cost from start
  const parent = new Map();
  const closed = new Set(); // already expanded
  const steps = [];
  const priority = (node) => (useG ? g.get(node) : 0) + heuristic(node, goal);

  open.push(start);
  while (open.length > 0) {
    // pick the open node with the smallest priority (ties: smaller h)
    open.sort(
      (a, b) =>
        priority(a) - priority(b) || heuristic(a, goal) - heuristic(b, goal),
    );
    const cur = open.shift();
    closed.add(cur);
    const step = {
      cell: cur,
      g: g.get(cur),
      h: heuristic(cur, goal),
      added: [],
    };
    step.f = useG ? step.g + step.h : step.h;
    steps.push(step);
    if (cur === goal) {
      return {
        found: true,
        path: buildPath(parent, goal),
        expanded: closed.size,
        steps,
      };
    }
    for (const nb of neighbours(lot, cur, goal)) {
      if (closed.has(nb)) continue;
      const newG = g.get(cur) + 1;
      if (!open.includes(nb)) {
        open.push(nb);
      } else if (!useG || newG >= g.get(nb)) {
        continue; // already queued with an equal or better g
      }
      g.set(nb, newG);
      parent.set(nb, cur);
      step.added.push(nb);
    }
    step.openSize = open.length;
  }
  return { found: false, path: [], expanded: closed.size, steps };
}

/* ---------------------------------------------------------------- Hill Climbing
 * Steepest descent on h: from the current node, look at all neighbours and move
 * to the one with the smallest h. If no neighbour has a smaller h than the
 * current node, we are stuck at a local minimum and the search fails.
 */
function hillClimbing(lot, start, goal) {
  const steps = [];
  const path = [start];
  let cur = start;
  for (;;) {
    const h = heuristic(cur, goal);
    const options = neighbours(lot, cur, goal).filter((n) => !path.includes(n));
    const step = {
      cell: cur,
      g: path.length - 1,
      h,
      f: h,
      added: options,
      options: options.map((n) => ({ cell: n, h: heuristic(n, goal) })),
    };
    steps.push(step);
    if (cur === goal)
      return { found: true, path, expanded: path.length, steps };

    let best = null;
    for (const o of step.options) if (best === null || o.h < best.h) best = o;
    if (best === null || best.h >= h) {
      step.stuck = true; // local minimum: no neighbour is better
      return { found: false, path, expanded: path.length, steps, stuckAt: cur };
    }
    step.chosen = best.cell;
    cur = best.cell;
    path.push(cur);
  }
}

/* ---------------------------------------------------------------- Depth-First Search
 * Uses a stack. The most recently discovered node is expanded first.
 */
function depthFirst(lot, start, goal) {
  const stack = [start];
  const parent = new Map();
  const depth = new Map([[start, 0]]);
  const visited = new Set();
  const steps = [];
  while (stack.length > 0) {
    const cur = stack.pop();
    if (visited.has(cur)) continue;
    visited.add(cur);
    const step = {
      cell: cur,
      g: depth.get(cur),
      h: heuristic(cur, goal),
      added: [],
    };
    step.f = step.h;
    steps.push(step);
    if (cur === goal) {
      return {
        found: true,
        path: buildPath(parent, goal),
        expanded: visited.size,
        steps,
      };
    }
    // push in reverse so the first neighbour (up) is explored first
    for (const nb of neighbours(lot, cur, goal).reverse()) {
      if (visited.has(nb)) continue;
      parent.set(nb, cur);
      depth.set(nb, depth.get(cur) + 1);
      stack.push(nb);
      step.added.push(nb);
    }
    step.openSize = stack.length;
  }
  return { found: false, path: [], expanded: visited.size, steps };
}
