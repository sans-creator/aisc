"""
cli.py - Terminal version of the smart parking system (no Pygame, no browser).

Uses the same core modules as the GUI: parking_lot.py, allocator.py, astar.py.

Run interactively:
    python cli.py

Or pass commands as arguments (run in order, then exit):
    python cli.py map "park ev" "park regular" "trace P7" status
"""

import shlex
import sys

from allocator import AI, allocate
from astar import astar
from parking_lot import (ParkingLot, ROAD, WALL, OBSTACLE, ENTRANCE, EXIT, SPOT,
                         REGULAR, EV, ACCESSIBLE, AVAILABLE, RESERVED, OCCUPIED, SPOT_TYPE_NAMES)

VEHICLE_ALIASES = {"regular": REGULAR, "car": REGULAR, "ev": EV,
                   "accessible": ACCESSIBLE, "acc": ACCESSIBLE}

HELP = """
Commands:
  map                     show the parking lot
  park <type>             A* picks the closest spot and parks  (type: regular | ev | accessible)
  trace <spot>            A* step-by-step table from the entrance to a spot, e.g. trace P7
  leave <spot>            free a spot, e.g. leave P2
  block <row> <col>       close a road cell
  unblock <row> <col>     open a road cell
  status                  counts of free / occupied spots
  reset                   start again with the default lot
  help                    this list
  quit                    exit

Map symbols:
  #  wall      o  pillar   .  road     x  closed road   S entrance   X exit
  P/E/A  free regular / EV / accessible spot        *  occupied spot
  +  route of the last parked car                   @  its spot
"""


class ParkingCLI:
    def __init__(self):
        self.reset()

    def reset(self):
        self.lot = ParkingLot()
        self.lot.place_initial_cars()
        self.next_vehicle = 1
        self.last_route = []
        self.last_spot = None

    # ------------------------------------------------------------- drawing
    def draw_map(self, route=(), target=None):
        route = set(route)
        letters = {REGULAR: "P", EV: "E", ACCESSIBLE: "A"}
        lines = ["    " + "".join(str(c % 10) for c in range(self.lot.cols))]
        for r in range(self.lot.rows):
            row = []
            for c in range(self.lot.cols):
                cell = (r, c)
                kind = self.lot.grid[cell]
                if cell == target:
                    ch = "@"
                elif kind == SPOT:
                    spot = self.lot.spot_at[cell]
                    ch = letters[spot.type] if spot.status == AVAILABLE else "*"
                elif cell in self.lot.blocked:
                    ch = "x"
                elif kind in (ENTRANCE, EXIT):
                    ch = "S" if kind == ENTRANCE else "X"
                elif cell in route:
                    ch = "+"
                else:
                    ch = {WALL: "#", OBSTACLE: "o", ROAD: "."}[kind]
                row.append(ch)
            lines.append(f"{r:>3} " + "".join(row))
        print("\n".join(lines))

    # ------------------------------------------------------------ commands
    def cmd_map(self):
        self.draw_map(self.last_route, self.last_spot)

    def cmd_park(self, vtype=None):
        vehicle_type = self._vehicle(vtype)
        if vehicle_type is None:
            return
        vehicle_id = f"V{self.next_vehicle}"
        alloc = allocate(self.lot, vehicle_type, self.lot.entrance, AI,
                         vehicle_id=vehicle_id, record_steps=False)
        print(f"Vehicle {vehicle_id} ({SPOT_TYPE_NAMES[vehicle_type]})")
        if not alloc.success:
            print("  Result : turned away")
            print(f"  Reason : {alloc.reason}")
            return
        self.lot.occupy(alloc.spot, vehicle_id)
        self.next_vehicle += 1
        self.last_route, self.last_spot = alloc.search.path, alloc.spot.cell
        print(f"  Spot   : {alloc.spot.id} {alloc.spot.cell}")
        print(f"  Route  : {alloc.route_length} moves")
        print(f"  A*     : {alloc.astar_calls} searches, {alloc.nodes_explored} nodes explored, "
              f"{alloc.pathfinding_ms:.2f} ms")
        print(f"  Reason : {alloc.reason}")
        print("  Path   : " + " -> ".join(f"({r},{c})" for r, c in alloc.search.path))
        self.draw_map(self.last_route, self.last_spot)

    def cmd_trace(self, spot_id=None):
        spot = self._spot(spot_id)
        if spot is None:
            return
        result = astar(self.lot.entrance, spot.cell, self.lot.neighbours, record_steps=True)
        print(f"A* from entrance {self.lot.entrance} to {spot.id} {spot.cell}")
        print(f"{'step':>4}  {'node':<9}{'g':>3}{'h':>4}{'f':>4}   added to open list (cell g+h)")
        for i, s in enumerate(result.steps, 1):
            added = ", ".join(f"{n} {g}+{h}" for n, g, h in s.added) or "-"
            print(f"{i:>4}  {str(s.node):<9}{s.g:>3}{s.h:>4}{s.f:>4}   {added}")
        if result.found:
            print(f"Found: {result.cost} moves, {result.nodes_explored} nodes explored")
            self.draw_map(result.path, spot.cell)
        else:
            print(f"No route: {spot.id} is unreachable ({result.nodes_explored} nodes explored)")

    def cmd_leave(self, spot_id=None):
        spot = self._spot(spot_id)
        if spot is None:
            return
        if spot.status == AVAILABLE:
            print(f"{spot.id} is already free")
            return
        self.lot.release(spot)
        if spot.cell == self.last_spot:
            self.last_route, self.last_spot = [], None
        print(f"{spot.id} is now free")

    def cmd_block(self, r=None, c=None, block=True):
        try:
            cell = (int(r), int(c))
        except (TypeError, ValueError):
            print("Usage: block <row> <col>   (see the numbers around the map)")
            return
        if not self.lot.is_blockable(cell):
            print(f"{cell} is not a road cell")
            return
        if block:
            self.lot.blocked.add(cell)
        else:
            self.lot.blocked.discard(cell)
        print(f"Road {cell} {'closed' if block else 'opened'}")
        self.draw_map()

    def cmd_status(self):
        print(f"Spots: {len(self.lot.spots)} total, {self.lot.count(AVAILABLE)} free, "
              f"{self.lot.count(OCCUPIED)} occupied, {self.lot.count(RESERVED)} reserved")
        for t in (REGULAR, EV, ACCESSIBLE):
            free = [s.id for s in self.lot.available_spots((t,))]
            print(f"  {SPOT_TYPE_NAMES[t]:<12} free: {', '.join(free) or 'none'}")
        if self.lot.blocked:
            print(f"  Closed roads: {', '.join(map(str, sorted(self.lot.blocked)))}")

    # ------------------------------------------------------------- helpers
    def _vehicle(self, name):
        vehicle_type = VEHICLE_ALIASES.get((name or "").lower())
        if vehicle_type is None:
            print("Vehicle type must be one of: regular, ev, accessible")
        return vehicle_type

    def _spot(self, spot_id):
        spot = self.lot.spot_by_id.get((spot_id or "").upper())
        if spot is None:
            print(f"Unknown spot {spot_id!r}. Spots are P1 to P{len(self.lot.spots)}")
        return spot

    def run(self, line):
        """Execute one command line. Returns False when the user wants to quit."""
        parts = shlex.split(line)
        if not parts:
            return True
        cmd, args = parts[0].lower(), parts[1:]
        if cmd in ("quit", "exit", "q"):
            return False
        commands = {
            "map": self.cmd_map, "park": self.cmd_park,
            "trace": self.cmd_trace, "leave": self.cmd_leave, "status": self.cmd_status,
            "block": self.cmd_block,
            "unblock": lambda r=None, c=None: self.cmd_block(r, c, block=False),
            "reset": lambda: (self.reset(), print("Lot reset")),
            "help": lambda: print(HELP),
        }
        if cmd not in commands:
            print(f"Unknown command {cmd!r}. Type 'help'.")
            return True
        try:
            commands[cmd](*args)
        except TypeError:
            print(f"Wrong arguments for {cmd!r}. Type 'help'.")
        return True


def main():
    cli = ParkingCLI()
    if len(sys.argv) > 1:
        for line in sys.argv[1:]:
            print(f"\n> {line}")
            if not cli.run(line):
                break
        return
    print("Smart Parking Allocation - terminal version. Type 'help' for commands.")
    cli.cmd_map()
    while True:
        try:
            line = input("\nparking> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not cli.run(line):
            break


if __name__ == "__main__":
    main()
