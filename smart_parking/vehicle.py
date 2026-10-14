"""
vehicle.py - Vehicle state and smooth movement along a route.

A vehicle stores the A* path it must follow. Its drawn position (x, y) is in
grid units and is interpolated between path cells so the car glides smoothly.
"""

import math

from parking_lot import REGULAR, EV, ACCESSIBLE

VEHICLE_LABELS = {REGULAR: "Car", EV: "EV", ACCESSIBLE: "Accessible"}

# Vehicle states
WAITING = "waiting"         # queued at the entrance
ALLOCATING = "allocating"   # spot reserved, A* search being shown
DRIVING = "driving"         # following the path to its spot
PARKED = "parked"
LEAVING = "leaving"         # driving to the exit
GONE = "gone"               # left the lot (or was turned away)

STATE_NAMES = {
    WAITING: "Waiting at entrance", ALLOCATING: "Spot reserved - A* search",
    DRIVING: "Driving to spot", PARKED: "Parked", LEAVING: "Leaving the lot",
    GONE: "Gone / turned away",
}


class Vehicle:
    def __init__(self, vehicle_id, vehicle_type, cell):
        self.id = vehicle_id
        self.type = vehicle_type
        self.state = WAITING
        self.cell = cell                 # last grid cell reached
        self.x = float(cell[1])          # drawn position in grid units (column)
        self.y = float(cell[0])          # drawn position in grid units (row)
        self.heading = 0.0               # degrees: 0 = right, 90 = up, -90 = down, 180 = left
        self.path = []
        self.seg = 0                     # moving from path[seg] to path[seg + 1]
        self.progress = 0.0              # 0..1 along the current segment
        self.spot = None                 # reserved / occupied ParkingSpot
        self.allocation = None           # Allocation record that chose the spot

    @property
    def label(self):
        return VEHICLE_LABELS[self.type]

    @property
    def moving(self):
        return bool(self.path) and self.seg < len(self.path) - 1

    def set_route(self, path):
        self.path = list(path)
        self.seg = 0
        self.progress = 0.0
        if self.path:
            self.cell = self.path[0]
            self.x, self.y = float(self.cell[1]), float(self.cell[0])
            if len(self.path) > 1:
                self._face(self.path[0], self.path[1])

    def next_cell(self):
        return self.path[self.seg + 1] if self.moving else self.cell

    def remaining_cells(self):
        """Cells still ahead of the car (including the one it is entering)."""
        return self.path[self.seg + 1:] if self.moving else []

    def reroute(self, new_tail):
        """Replace the route after the cell the car is entering. new_tail[0] == next_cell()."""
        self.path = self.path[:self.seg + 1] + list(new_tail)

    def update(self, dt, cells_per_second):
        """Advance along the path. Returns True on the frame the route is completed."""
        if not self.moving:
            return False
        self.progress += dt * cells_per_second
        while self.progress >= 1.0 and self.moving:
            self.progress -= 1.0
            self.seg += 1
            self.cell = self.path[self.seg]
        if not self.moving:
            self.progress = 0.0
            self.x, self.y = float(self.cell[1]), float(self.cell[0])
            self._face(self.path[-2], self.path[-1])
            return True
        a, b = self.path[self.seg], self.path[self.seg + 1]
        self.x = a[1] + (b[1] - a[1]) * self.progress
        self.y = a[0] + (b[0] - a[0]) * self.progress
        self._face(a, b)
        return False

    def _face(self, a, b):
        dr, dc = b[0] - a[0], b[1] - a[1]
        self.heading = math.degrees(math.atan2(-dr, dc))
