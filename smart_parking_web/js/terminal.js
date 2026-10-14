/*
 * terminal.js - Command-line style page for the parking system (A* only).
 * Same commands as smart_parking/cli.py. Uses lot.js, search.js and allocator.js.
 */

(() => {
  const out = document.getElementById("out");
  const input = document.getElementById("in");
  const VEHICLES = { regular: "regular", car: "regular", ev: "ev", accessible: "accessible", acc: "accessible" };

  const HELP = `Commands:
  map                 show the parking lot
  park <type>         A* picks the closest spot and parks  (type: regular | ev | accessible)
  trace <spot>        A* step-by-step table from the entrance to a spot, e.g. trace P7
  leave <spot>        free a spot, e.g. leave P2
  block <row> <col>   close a road cell
  unblock <row> <col> open a road cell
  status              counts of free / occupied spots
  reset               start again with the default lot
  clear               clear the screen
  help                this list

Map symbols:
  #  wall      o  pillar   .  road     x  closed road   S entrance   X exit
  P/E/A  free regular / EV / accessible spot        *  occupied spot
  +  route of the last parked car                   @  its spot`;

  let lot, nextVehicle, lastRoute, lastSpot;
  const history = [];
  let historyPos = 0;

  function reset() {
    lot = createLot();
    nextVehicle = 1;
    lastRoute = [];
    lastSpot = null;
  }

  // ------------------------------------------------------------ output
  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  function print(text = "", cls = "") {
    const div = document.createElement("div");
    if (cls) div.className = cls;
    div.textContent = text;
    out.appendChild(div);
  }

  function printHtml(html) {
    const div = document.createElement("div");
    div.innerHTML = html;
    out.appendChild(div);
  }

  const pos = (cell) => `(${cell.r},${cell.c})`;

  function drawMap(route = [], target = null) {
    const onRoute = new Set(route);
    const letters = { regular: "P", ev: "E", accessible: "A" };
    let header = "    ";
    for (let c = 0; c < lot.cols; c++) header += c % 10;
    const lines = [esc(header)];
    for (const row of lot.cells) {
      let line = String(row[0].r).padStart(3) + " ";
      for (const cell of row) {
        if (cell === target) line += `<span class="target">@</span>`;
        else if (cell.kind === "spot") {
          line += cell.spot.status === "available" ? letters[cell.spot.type] : `<span class="occ">*</span>`;
        } else if (cell.blocked) line += `<span class="blk">x</span>`;
        else if (cell.kind === "entrance") line += "S";
        else if (cell.kind === "exit") line += "X";
        else if (onRoute.has(cell)) line += `<span class="route">+</span>`;
        else line += { wall: "#", pillar: "o", road: "." }[cell.kind];
      }
      lines.push(line);
    }
    printHtml(lines.join("\n"));
  }

  // ----------------------------------------------------------- commands
  function findSpot(id) {
    const spot = lot.spots.find((s) => s.id === String(id || "").toUpperCase());
    if (!spot) print(`Unknown spot '${id ?? ""}'. Spots are P1 to P${lot.spots.length}`, "err");
    return spot;
  }

  function vehicleType(name) {
    const type = VEHICLES[String(name || "").toLowerCase()];
    if (!type) print("Vehicle type must be one of: regular, ev, accessible", "err");
    return type;
  }

  const commands = {
    map() { drawMap(lastRoute, lastSpot); },

    park(name) {
      const type = vehicleType(name);
      if (!type) return;
      const id = "V" + nextVehicle;
      const result = allocate(lot, type);
      print(`Vehicle ${id} (${VEHICLE_NAMES[type]})`);
      if (!result.ok) {
        print("  Result : turned away", "err");
        print(`  Reason : ${result.reason}`);
        return;
      }
      const route = runSearch(lot, lot.entrance, result.spot.cell, "astar");
      result.spot.status = "occupied";
      nextVehicle++;
      lastRoute = route.path;
      lastSpot = result.spot.cell;
      print(`  Spot   : ${result.spot.id} ${pos(result.spot.cell)}`, "ok");
      print(`  Route  : ${route.cost} moves, ${route.expanded} nodes explored, ${route.timeMs.toFixed(2)} ms`);
      print(`  Reason : ${result.reason}`);
      print(`  Path   : ${route.path.map(pos).join(" -> ")}`);
      drawMap(lastRoute, lastSpot);
    },

    trace(id) {
      const spot = findSpot(id);
      if (!spot) return;
      const goal = spot.cell;
      const r = runSearch(lot, lot.entrance, goal, "astar");
      print(`A* from entrance ${pos(lot.entrance)} to ${spot.id} ${pos(goal)}`);
      print(`step  node       g   h   f   added to open list (cell g+h)`);
      r.steps.forEach((s, i) => {
        const added = s.added.map((n) => `${pos(n)} ${s.g + 1}+${heuristic(n, goal)}`).join(", ") || "-";
        print(`${String(i + 1).padStart(4)}  ${pos(s.cell).padEnd(9)}${String(s.g).padStart(3)}` +
              `${String(s.h).padStart(4)}${String(s.f).padStart(4)}   ${added}`);
      });
      if (r.found) {
        print(`Found: ${r.cost} moves, ${r.expanded} nodes explored`, "ok");
        drawMap(r.path, goal);
      } else {
        print(`No route: ${spot.id} is unreachable (${r.expanded} nodes explored)`, "err");
      }
    },

    leave(id) {
      const spot = findSpot(id);
      if (!spot) return;
      if (spot.status === "available") return print(`${spot.id} is already free`);
      spot.status = "available";
      if (spot.cell === lastSpot) { lastRoute = []; lastSpot = null; }
      print(`${spot.id} is now free`, "ok");
    },

    block(r, c, close = true) {
      const cell = cellAt(lot, Number(r), Number(c));
      if (r === undefined || c === undefined || Number.isNaN(Number(r)) || Number.isNaN(Number(c))) {
        return print("Usage: block <row> <col>   (see the numbers around the map)", "err");
      }
      if (!cell || cell.kind !== "road") return print(`(${r}, ${c}) is not a road cell`, "err");
      cell.blocked = close;
      print(`Road (${r}, ${c}) ${close ? "closed" : "opened"}`, "ok");
      drawMap();
    },

    unblock(r, c) { commands.block(r, c, false); },

    status() {
      const occupied = lot.spots.length - countSpots(lot, "available");
      print(`Spots: ${lot.spots.length} total, ${countSpots(lot, "available")} free, ${occupied} occupied`);
      for (const t of ["regular", "ev", "accessible"]) {
        const free = availableSpots(lot, [t]).map((s) => s.id);
        print(`  ${SPOT_TYPE_NAMES[t].padEnd(12)} free: ${free.join(", ") || "none"}`);
      }
      const closed = lot.cells.flat().filter((c) => c.blocked).map(pos);
      if (closed.length) print(`  Closed roads: ${closed.join(", ")}`);
    },

    reset() { reset(); print("Lot reset", "ok"); },
    clear() { out.innerHTML = ""; },
    help() { print(HELP); },
  };

  function run(line) {
    print(`parking> ${line}`, "cmd");
    const [cmd, ...args] = line.trim().split(/\s+/);
    if (!cmd) return;
    const fn = commands[cmd.toLowerCase()];
    if (!fn) print(`Unknown command '${cmd}'. Type 'help'.`, "err");
    else fn(...args);
    print();
  }

  // -------------------------------------------------------------- input
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const line = input.value;
      input.value = "";
      if (line.trim()) history.push(line);
      historyPos = history.length;
      run(line);
      out.scrollTop = out.scrollHeight;
    } else if (e.key === "ArrowUp" && historyPos > 0) {
      input.value = history[--historyPos];
      e.preventDefault();
    } else if (e.key === "ArrowDown") {
      historyPos = Math.min(history.length, historyPos + 1);
      input.value = history[historyPos] ?? "";
      e.preventDefault();
    }
  });
  document.addEventListener("click", () => {
    if (!window.getSelection().toString()) input.focus();
  });

  reset();
  print("Smart Parking Allocation - terminal version (A* search). Type 'help' for commands.");
  print();
  drawMap();
  print();
})();
