"""
parking_lot.py - The parking lot environment (grid, spots, roads, obstacles).

Every grid cell is one of:
    wall      outside the lot / grass        (never drivable)
    road      driving lane                   (drivable unless blocked)
    obstacle  static pillar                  (never drivable)
    spot      parking space                  (a car may enter it only as its destination)
    entrance  where vehicles enter           (drivable)
    exit      where vehicles leave           (drivable)

Road cells can also be BLOCKED at run time (maintenance, accident ...). A blocked
road behaves like an obstacle until it is unblocked.

Spot status life-cycle:   available -> reserved -> occupied -> available
"""

from collections import deque

WALL, ROAD, OBSTACLE, SPOT, ENTRANCE, EXIT = "wall", "road", "obstacle", "spot", "entrance", "exit"

REGULAR, EV, ACCESSIBLE = "regular", "ev", "accessible"
SPOT_TYPE_NAMES = {REGULAR: "Regular", EV: "EV charging", ACCESSIBLE: "Accessible"}

AVAILABLE, RESERVED, OCCUPIED = "available", "reserved", "occupied"

DIRECTIONS = ((-1, 0), (1, 0), (0, -1), (0, 1))   # up, down, left, right

# Layout legend:
#   W wall/grass   . road   # pillar   S entrance   X exit
#   P regular spot   E EV charging spot   A accessible spot
# Three horizontal lanes (rows 2, 5, 7) joined by several vertical lanes give
# many loops, so most spots can be reached by more than one route.
DEFAULT_LAYOUT = (
    "WWWWWWWWWWWWWWWWWW",
    "WWAPPPPEWWEPPPPWWW",
    "S................W",
    "W.PPPPP.#.PPPPP..W",
    "W.PPPPP...PPPPP#.W",
    "W................W",
    "W.#EPPP.#.PPPPA..W",
    "W....#...........X",
    "WWWWWWWWWWWWWWWWWW",
)

# Spots that already hold a car when the simulation starts.
DEFAULT_OCCUPIED = ("P2", "P4", "P9", "P13", "P16", "P19", "P23", "P28", "P34", "P37")

# Road cells blocked at the start (a "maintenance" block on the top lane).
# It makes the top-right spots look close in a straight line but far by road,
# which is exactly where real route cost (A*) beats straight-line distance.
DEFAULT_BLOCKED = ((2, 9),)


class ParkingSpot:
    def __init__(self, index, spot_id, cell, spot_type):
        self.index = index          # 0-based position, used for deterministic tie-breaking
        self.id = spot_id           # "P1", "P2", ...
        self.cell = cell            # (row, col)
        self.type = spot_type       # REGULAR / EV / ACCESSIBLE
        self.status = AVAILABLE
        self.vehicle_id = None      # vehicle that reserved / occupies the spot

    def __repr__(self):
        return f"ParkingSpot({self.id}, {self.cell}, {self.type}, {self.status})"


class ParkingLot:
    def __init__(self, layout=DEFAULT_LAYOUT, blocked=DEFAULT_BLOCKED):
        self.layout = tuple(layout)
        self.rows = len(self.layout)
        self.cols = len(self.layout[0])
        self.grid = {}              # (row, col) -> cell kind
        self.spots = []
        self.spot_at = {}           # (row, col) -> ParkingSpot
        self.spot_by_id = {}        # "P7" -> ParkingSpot
        self.entrance = None
        self.exit = None

        kinds = {"W": WALL, ".": ROAD, "#": OBSTACLE, "S": ENTRANCE, "X": EXIT}
        spot_types = {"P": REGULAR, "E": EV, "A": ACCESSIBLE}

        for r, line in enumerate(self.layout):
            if len(line) != self.cols:
                raise ValueError(f"Layout row {r} has length {len(line)}, expected {self.cols}")
            for c, ch in enumerate(line):
                cell = (r, c)
                if ch in spot_types:
                    self.grid[cell] = SPOT
                    spot = ParkingSpot(len(self.spots), f"P{len(self.spots) + 1}", cell, spot_types[ch])
                    self.spots.append(spot)
                    self.spot_at[cell] = spot
                    self.spot_by_id[spot.id] = spot
                elif ch in kinds:
                    self.grid[cell] = kinds[ch]
                    if ch == "S":
                        self.entrance = cell
                    elif ch == "X":
                        self.exit = cell
                else:
                    raise ValueError(f"Unknown layout character {ch!r} at {cell}")

        if self.entrance is None or self.exit is None:
            raise ValueError("Layout needs one entrance 'S' and one exit 'X'")

        self.blocked = {cell for cell in blocked if self.grid.get(cell) == ROAD}

    # ------------------------------------------------------------------ grid
    def is_drivable(self, cell):
        """Can a car drive THROUGH this cell?"""
        return self.grid.get(cell) in (ROAD, ENTRANCE, EXIT) and cell not in self.blocked

    def is_blockable(self, cell):
        """Only plain road cells can be blocked (not the entrance/exit)."""
        return self.grid.get(cell) == ROAD

    def neighbours(self, cell, goal=None):
        """
        Cells a car can move to from `cell` (4 directions).
        Parking spots, pillars, walls and blocked roads are not drivable;
        the only exception is the goal cell itself (e.g. the target spot).
        This function defines the A* search space.
        """
        r, c = cell
        result = []
        for dr, dc in DIRECTIONS:
            nb = (r + dr, c + dc)
            if nb == goal or self.is_drivable(nb):
                result.append(nb)
        return result

    def road_cells(self):
        return [cell for cell, kind in self.grid.items() if kind == ROAD]

    def reachable_from(self, start):
        """All drivable cells reachable from start (breadth-first flood fill)."""
        seen = {start}
        queue = deque([start])
        while queue:
            cell = queue.popleft()
            for nb in self.neighbours(cell):
                if nb not in seen:
                    seen.add(nb)
                    queue.append(nb)
        return seen

    # ----------------------------------------------------------------- spots
    def available_spots(self, types=None):
        return [s for s in self.spots
                if s.status == AVAILABLE and (types is None or s.type in types)]

    def count(self, status):
        return sum(1 for s in self.spots if s.status == status)

    def reserve(self, spot, vehicle_id):
        if spot.status != AVAILABLE:
            raise ValueError(f"{spot.id} is {spot.status}; it cannot be reserved again")
        spot.status = RESERVED
        spot.vehicle_id = vehicle_id

    def occupy(self, spot, vehicle_id):
        if spot.status == OCCUPIED or (spot.status == RESERVED and spot.vehicle_id != vehicle_id):
            raise ValueError(f"{spot.id} belongs to {spot.vehicle_id}; {vehicle_id} cannot park there")
        spot.status = OCCUPIED
        spot.vehicle_id = vehicle_id

    def release(self, spot):
        spot.status = AVAILABLE
        spot.vehicle_id = None

    def place_initial_cars(self, spot_ids=DEFAULT_OCCUPIED, prefix="C"):
        """Occupy the starting spots. Returns [(spot, vehicle_id), ...]."""
        placed = []
        for i, sid in enumerate(spot_ids, start=1):
            spot = self.spot_by_id[sid]
            vehicle_id = f"{prefix}{i}"
            self.occupy(spot, vehicle_id)
            placed.append((spot, vehicle_id))
        return placed
