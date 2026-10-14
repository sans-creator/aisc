"""
allocator.py - Chooses WHICH parking spot a vehicle gets (destination selection).

Pathfinding (HOW to get there) lives in astar.py. This module only decides the
destination, using A* as a tool to measure real route costs.

Two strategies are implemented so they can be compared fairly:

  AI        For every available, eligible spot run A* from the vehicle's
            position and pick the spot with the LOWEST REAL ROUTE COST
            (ties -> lower spot number). Unreachable spots are discarded.

  BASELINE  Pick the spot that is nearest by straight-line Manhattan distance
            (ignores walls, pillars and blocked roads), then run A* only to get
            a valid route to it. If that spot is unreachable, try the next one.

Both strategies follow the same eligibility policy (below), so the only
difference between them is the destination-selection rule.
"""

import time
from dataclasses import dataclass, field

from astar import astar, manhattan
from parking_lot import REGULAR, EV, ACCESSIBLE, SPOT_TYPE_NAMES

AI, BASELINE = "ai", "baseline"
STRATEGY_NAMES = {AI: "AI - lowest A* route cost", BASELINE: "Baseline - nearest by Manhattan"}
STRATEGY_SHORT = {AI: "AI", BASELINE: "Baseline"}

# Eligibility policy. Each vehicle type lists TIERS of spot types in order of
# preference. The next tier is used only if no spot of the previous tier is
# available AND reachable.
#   regular car  -> regular spots only (EV and accessible spots are protected)
#   EV           -> EV charging spots, otherwise a regular spot
#   accessible   -> accessible spots, otherwise a regular spot
ELIGIBILITY = {
    REGULAR: ((REGULAR,),),
    EV: ((EV,), (REGULAR,)),
    ACCESSIBLE: ((ACCESSIBLE,), (REGULAR,)),
}


@dataclass
class Allocation:
    strategy: str
    vehicle_type: str
    start: tuple
    spot: object = None            # chosen ParkingSpot (None = failed)
    search: object = None          # A* SearchResult of the route to the chosen spot
    candidates: list = field(default_factory=list)   # spots considered in the final tier
    scores: dict = field(default_factory=dict)       # spot id -> score shown on the map
    score_kind: str = ""           # "route" (A* moves, None = unreachable) or "manhattan"
    tier: tuple = ()
    used_fallback: bool = False
    skipped: list = field(default_factory=list)      # baseline: unreachable spots it tried
    astar_calls: int = 0           # number of A* searches run for this decision
    nodes_explored: int = 0        # total nodes expanded over all those searches
    pathfinding_ms: float = 0.0    # total time spent inside A*
    allocation_ms: float = 0.0     # total time of the whole decision (includes A*)
    reason: str = ""

    @property
    def success(self):
        return self.spot is not None

    @property
    def route_length(self):
        return self.search.cost if self.success else 0


def allocate(lot, vehicle_type, start, strategy=AI, vehicle_id=None, record_steps=True):
    """
    Pick a spot for a vehicle at `start`. If vehicle_id is given and a spot is
    found, the spot is RESERVED immediately so no other vehicle can get it.
    Never raises for "lot full" / "nothing reachable": returns success=False.
    """
    if vehicle_type not in ELIGIBILITY:
        raise ValueError(f"Unknown vehicle type {vehicle_type!r}")
    if strategy not in (AI, BASELINE):
        raise ValueError(f"Unknown strategy {strategy!r}")

    t0 = time.perf_counter()
    alloc = Allocation(strategy, vehicle_type, start)

    for tier_no, tier in enumerate(ELIGIBILITY[vehicle_type]):
        candidates = lot.available_spots(tier)       # constraint filtering
        if not candidates:
            continue
        alloc.candidates = candidates
        alloc.tier = tier
        if strategy == AI:
            choice = _choose_ai(lot, start, candidates, alloc, record_steps)
        else:
            choice = _choose_baseline(lot, start, candidates, alloc, record_steps)
        if choice is not None:
            alloc.spot, alloc.search = choice
            alloc.used_fallback = tier_no > 0
            break

    if alloc.success and vehicle_id is not None:
        lot.reserve(alloc.spot, vehicle_id)
    alloc.allocation_ms = (time.perf_counter() - t0) * 1000.0
    alloc.reason = explain(alloc)
    return alloc


def _search(lot, start, spot, alloc, record_steps):
    result = astar(start, spot.cell, lot.neighbours, record_steps=record_steps)
    alloc.astar_calls += 1
    alloc.nodes_explored += result.nodes_explored
    alloc.pathfinding_ms += result.time_ms
    return result


def _choose_ai(lot, start, candidates, alloc, record_steps):
    alloc.score_kind = "route"
    alloc.scores = {}
    best = None
    for spot in candidates:                         # candidates are in spot order
        result = _search(lot, start, spot, alloc, record_steps)
        alloc.scores[spot.id] = result.cost if result.found else None
        if not result.found:
            continue                                # discard unreachable spots
        if best is None or (result.cost, spot.index) < (best[1].cost, best[0].index):
            best = (spot, result)
    return best


def _choose_baseline(lot, start, candidates, alloc, record_steps):
    alloc.score_kind = "manhattan"
    alloc.scores = {s.id: manhattan(start, s.cell) for s in candidates}
    alloc.skipped = []
    ordered = sorted(candidates, key=lambda s: (manhattan(start, s.cell), s.index))
    for spot in ordered:
        result = _search(lot, start, spot, alloc, record_steps)
        if result.found:
            return spot, result
        alloc.skipped.append(spot.id)
    return None


def _tier_name(tier):
    return "/".join(SPOT_TYPE_NAMES[t] for t in tier)


def explain(alloc):
    """Human-readable reason for the decision (shown in the side panel)."""
    if not alloc.success:
        wanted = " or ".join(_tier_name(t) for t in ELIGIBILITY[alloc.vehicle_type])
        return f"No available {wanted} spot can be reached, so the vehicle is turned away."

    spot, cost = alloc.spot, alloc.route_length
    kind = _tier_name(alloc.tier)
    fallback = ""
    if alloc.used_fallback:
        preferred = _tier_name(ELIGIBILITY[alloc.vehicle_type][0])
        fallback = f" No {preferred} spot was free and reachable, so a {kind} spot was used."

    if alloc.strategy == AI:
        reachable = sorted((c, s.index, s.id) for s in alloc.candidates
                           for c in [alloc.scores.get(s.id)] if c is not None)
        text = (f"{spot.id} has the lowest real route cost: {cost} moves. "
                f"A* was run to all {len(alloc.candidates)} free {kind} spots "
                f"({len(reachable)} reachable).")
        if len(reachable) > 1:
            text += f" Next best: {reachable[1][2]} ({reachable[1][0]} moves)."
        nearest = min(alloc.candidates, key=lambda s: (manhattan(alloc.start, s.cell), s.index))
        if nearest is not spot:
            n_cost = alloc.scores.get(nearest.id)
            n_route = "unreachable" if n_cost is None else f"{n_cost} moves"
            text += (f" {nearest.id} looks nearer in a straight line "
                     f"({manhattan(alloc.start, nearest.cell)}) but its real route is {n_route}.")
        return text + fallback

    m = manhattan(alloc.start, spot.cell)
    text = (f"{spot.id} is the nearest free {kind} spot by straight-line (Manhattan) "
            f"distance = {m}. A* then found the route: {cost} moves.")
    if cost > m:
        text += f" Walls/pillars/blocks add {cost - m} extra moves."
    if alloc.skipped:
        text += f" Skipped unreachable: {', '.join(alloc.skipped)}."
    return text + fallback
