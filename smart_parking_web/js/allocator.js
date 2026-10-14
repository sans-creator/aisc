/*
 * allocator.js - Decides WHICH spot a vehicle gets.
 *
 * 1. Constraint filtering: keep only free spots the vehicle may use.
 * 2. Run A* from the entrance to every candidate spot.
 * 3. Choose the spot with the shortest real route (ties -> lower spot number).
 *
 * Then search.js shows HOW the chosen algorithm drives to that spot.
 */

// Eligibility: try the first list of spot types, fall back to the next.
const ELIGIBILITY = {
  regular: [["regular"]],
  ev: [["ev"], ["regular"]],
  accessible: [["accessible"], ["regular"]],
};

function allocate(lot, vehicleType) {
  const start = lot.entrance;
  for (const types of ELIGIBILITY[vehicleType]) {
    const candidates = availableSpots(lot, types);
    const reachable = candidates
      .map((spot) => ({ spot, cost: runSearch(lot, start, spot.cell, "astar").cost }))
      .filter((c) => c.cost !== Infinity)
      .sort((a, b) => a.cost - b.cost || a.spot.index - b.spot.index);
    if (reachable.length > 0) {
      const best = reachable[0];
      return {
        ok: true, spot: best.spot,
        reason: `${best.spot.id} is the closest free ${SPOT_TYPE_NAMES[best.spot.type]} spot by real route ` +
                `(${best.cost} moves). A* checked all ${reachable.length} reachable candidates.`,
      };
    }
  }
  return { ok: false, reason: "No suitable free spot can be reached. The vehicle is turned away." };
}
