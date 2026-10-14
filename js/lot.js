/*
 * lot.js - The parking lot as a grid of cells.
 *
 * Every cell is an object { r, c, kind, blocked, spot }.
 *   kind:    "wall" | "road" | "pillar" | "spot" | "entrance" | "exit"
 *   blocked: road closed (cars cannot drive through)
 *   spot:    for parking cells, { id, index, type, status, cell }
 *
 * Every move (up / down / left / right) costs 1.
 */

// Legend:  W wall/grass   . road   # pillar   S entrance   X exit
//          P regular spot   E EV charging spot   A accessible spot
const LOT_LAYOUT = [
  "WWWWWWWWWWWWWWWWWW",
  "WWAPPPPEWWEPPPPWWW",
  "S................W",
  "W.PPPPP.#.PPPPP..W",
  "W.PPPPP...PPPPP#.W",
  "W................W",
  "W.#EPPP.#.PPPPA..W",
  "W....#...........X",
  "WWWWWWWWWWWWWWWWWW",
];

const DEFAULT_OCCUPIED = ["P2", "P4", "P9", "P13", "P16", "P19", "P23", "P28", "P34", "P37"];
const DEFAULT_BLOCKED = [[2, 9]];          // road works on the top lane

const SPOT_TYPE_NAMES = { regular: "Regular", ev: "EV charging", accessible: "Accessible" };
const VEHICLE_NAMES = { regular: "Car", ev: "EV", accessible: "Accessible" };

function createLot() {
  const kinds = { W: "wall", ".": "road", "#": "pillar", S: "entrance", X: "exit" };
  const spotTypes = { P: "regular", E: "ev", A: "accessible" };
  const lot = { rows: LOT_LAYOUT.length, cols: LOT_LAYOUT[0].length, cells: [], spots: [],
                entrance: null, exit: null };

  LOT_LAYOUT.forEach((line, r) => {
    const row = [];
    [...line].forEach((ch, c) => {
      const cell = { r, c, kind: spotTypes[ch] ? "spot" : kinds[ch], blocked: false, spot: null };
      if (spotTypes[ch]) {
        const index = lot.spots.length;
        cell.spot = { id: "P" + (index + 1), index, type: spotTypes[ch], status: "available", cell };
        lot.spots.push(cell.spot);
      }
      if (ch === "S") lot.entrance = cell;
      if (ch === "X") lot.exit = cell;
      row.push(cell);
    });
    lot.cells.push(row);
  });

  for (const spot of lot.spots) {
    if (DEFAULT_OCCUPIED.includes(spot.id)) spot.status = "occupied";
  }
  for (const [r, c] of DEFAULT_BLOCKED) lot.cells[r][c].blocked = true;
  return lot;
}

function cellAt(lot, r, c) {
  if (r < 0 || c < 0 || r >= lot.rows || c >= lot.cols) return null;
  return lot.cells[r][c];
}

/** Can a car drive THROUGH this cell? */
function isDrivable(cell) {
  return cell !== null &&
    (cell.kind === "road" || cell.kind === "entrance" || cell.kind === "exit") && !cell.blocked;
}

/**
 * The search space: cells a car can move to from `cell` (up, down, left, right).
 * Parking spots cannot be driven through - only entered when they are the goal.
 */
function neighbours(lot, cell, goal) {
  const result = [];
  for (const [dr, dc] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
    const nb = cellAt(lot, cell.r + dr, cell.c + dc);
    if (nb !== null && (nb === goal || isDrivable(nb))) result.push(nb);
  }
  return result;
}

/**
 * HEURISTIC h(n): Manhattan distance from cell n to the goal.
 *     h(n) = |n.row - goal.row| + |n.col - goal.col|
 * A car needs at least this many moves, so h never over-estimates (admissible).
 */
function heuristic(n, goal) {
  return Math.abs(n.r - goal.r) + Math.abs(n.c - goal.c);
}

function availableSpots(lot, types) {
  return lot.spots.filter((s) => s.status === "available" && types.includes(s.type));
}

function countSpots(lot, status) {
  return lot.spots.filter((s) => s.status === status).length;
}
