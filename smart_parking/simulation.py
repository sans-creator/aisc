"""
simulation.py - The simulation state machine (no drawing code in here).

Life of a vehicle:
    WAITING     queued at the entrance
    ALLOCATING  allocator chose + RESERVED a spot; the A* search is replayed on screen
    DRIVING     following the A* path to its spot
    PARKED      spot becomes OCCUPIED
    LEAVING     spot released, car follows a new A* path to the exit

Only one vehicle is guided at a time (phase IDLE -> SEARCHING -> SEARCH_DONE ->
MOVING -> IDLE) so the evaluator can follow each A* search clearly. Leaving
cars move independently.
"""

import random
from collections import deque

from allocator import AI, BASELINE, STRATEGY_NAMES, allocate
from astar import astar
from benchmark import random_vehicle_type
from metrics import Metrics
from parking_lot import (ParkingLot, DEFAULT_BLOCKED, SPOT_TYPE_NAMES,
                         AVAILABLE, RESERVED, OCCUPIED, REGULAR)
from vehicle import Vehicle, WAITING, ALLOCATING, DRIVING, PARKED, LEAVING, GONE

# Guidance phases
IDLE, SEARCHING, SEARCH_DONE, MOVING = "idle", "searching", "search_done", "moving"

CAR_SPEED = 3.5               # cells per second at 1x speed
SEARCH_MIN_RATE = 18          # A* expansions replayed per second (at least)
SEARCH_TARGET_SECONDS = 2.5   # long searches are replayed faster to fit roughly this time
PATH_HOLD_SECONDS = 0.8       # pause on the finished path before the car starts
ARRIVAL_INTERVAL = 2.5        # seconds between random-arrival events
MAX_QUEUE = 6
SPEEDS = (0.5, 1.0, 2.0, 4.0)


class Simulation:
    def __init__(self, seed=2024):
        self.seed = seed
        # User settings (kept across resets)
        self.strategy = AI
        self.step_mode = False
        self.auto_allocate = True
        self.speed_index = 1
        self.reset()

    # ------------------------------------------------------------- set-up
    def reset(self):
        self.rng = random.Random(self.seed)
        self.lot = ParkingLot(blocked=DEFAULT_BLOCKED)
        self.vehicles = {}            # every vehicle inside the lot, by id
        for spot, vehicle_id in self.lot.place_initial_cars():
            v = Vehicle(vehicle_id, REGULAR, spot.cell)
            v.state = PARKED
            v.spot = spot
            v.heading = self._parked_heading(spot.cell)
            self.vehicles[vehicle_id] = v
        self.queue = deque()          # vehicles waiting at the entrance
        self.active = None            # vehicle currently being guided
        self.leaving = []
        self.phase = IDLE
        self.search_shown = 0         # how many A* expansions are visible so far
        self._search_accum = 0.0
        self._search_rate = SEARCH_MIN_RATE
        self._hold = 0.0
        self.display_alloc = None     # allocation whose search/path is drawn on the map
        self.last_vehicle = None
        self.selected_id = None
        self.metrics = {AI: Metrics(), BASELINE: Metrics()}
        self.paused = False
        self.random_arrivals = False
        self._arrival_timer = 0.0
        self.next_number = 1
        self.message, self.message_level = "", "info"
        self.say("Simulation reset. Add a vehicle with 1 / 2 / 3 (or the buttons) to start.")

    def _parked_heading(self, cell):
        above = (cell[0] - 1, cell[1])
        return -90.0 if self.lot.is_drivable(above) else 90.0

    def say(self, text, level="info"):
        self.message, self.message_level = text, level

    @property
    def speed(self):
        return SPEEDS[self.speed_index]

    # ------------------------------------------------------------ arrivals
    def add_vehicle(self, vehicle_type):
        if len(self.queue) >= MAX_QUEUE:
            self.say(f"Entrance queue is full ({MAX_QUEUE} cars). Allocate or wait.", "warn")
            return None
        v = Vehicle(f"V{self.next_number}", vehicle_type, self.lot.entrance)
        self.next_number += 1
        self.queue.append(v)
        hint = "" if self.auto_allocate else " Press ENTER (Allocate) to assign a spot."
        self.say(f"{v.label} {v.id} arrived at the entrance.{hint}")
        return v

    def allocate_next(self):
        if self.phase != IDLE:
            self.say("Please wait - the current vehicle is still being guided.", "warn")
            return False
        if not self.queue:
            self.say("No vehicle is waiting. Add one first (1 / 2 / 3).", "warn")
            return False
        self._start_allocation(self.queue.popleft())
        return True

    def _start_allocation(self, v):
        alloc = allocate(self.lot, v.type, self.lot.entrance, self.strategy, vehicle_id=v.id)
        self.metrics[self.strategy].record(alloc)
        v.allocation = alloc
        self.last_vehicle = v
        if not alloc.success:
            v.state = GONE
            self.display_alloc = None
            self.say(f"{v.id} ({v.label}): {alloc.reason}", "error")
            return
        v.spot = alloc.spot
        v.state = ALLOCATING
        self.vehicles[v.id] = v
        self.active = v
        self.display_alloc = alloc
        self.phase = SEARCHING
        self.search_shown = 0
        self._search_accum = 0.0
        n = len(alloc.search.steps)
        self._search_rate = max(SEARCH_MIN_RATE, n / SEARCH_TARGET_SECONDS)
        how = "Press SPACE to expand nodes one by one." if self.step_mode else "Replaying the A* search..."
        self.say(f"{v.id} -> {alloc.spot.id} RESERVED ({STRATEGY_NAMES[self.strategy]}). {how}")

    # -------------------------------------------------------- A* replay
    def visible_steps(self):
        """Number of A* expansions currently drawn for display_alloc."""
        if self.display_alloc is None:
            return 0
        if self.phase == SEARCHING and self.active is not None \
                and self.active.allocation is self.display_alloc:
            return self.search_shown
        return len(self.display_alloc.search.steps)

    def next_step(self):
        if self.phase == SEARCHING:
            self.search_shown += 1
            if self.search_shown >= len(self.display_alloc.search.steps):
                self._finish_search()
        elif self.phase == SEARCH_DONE:
            self._begin_driving()
        elif self.phase == IDLE and self.queue:
            self.allocate_next()
        elif self.phase == MOVING:
            self.say("The vehicle is already driving along its A* path.")
        else:
            self.say("Nothing to step through. Add a vehicle first (1 / 2 / 3).", "warn")

    def _finish_search(self):
        self.phase = SEARCH_DONE
        self._hold = PATH_HOLD_SECONDS
        a = self.display_alloc
        tail = " Press SPACE to start driving." if self.step_mode else ""
        self.say(f"A* complete: route to {a.spot.id} = {a.route_length} moves, "
                 f"{a.search.nodes_explored} nodes explored.{tail}", "ok")

    def _begin_driving(self):
        v = self.active
        v.state = DRIVING
        v.set_route(v.allocation.search.path)
        self.phase = MOVING

    # ------------------------------------------------------------ update
    def update(self, dt):
        if self.paused:
            return
        dt *= self.speed

        if self.random_arrivals:
            self._arrival_timer -= dt
            if self._arrival_timer <= 0:
                self._arrival_timer = ARRIVAL_INTERVAL
                self._random_event()

        for v in list(self.leaving):
            if v.update(dt, CAR_SPEED):
                v.state = GONE
                self.leaving.remove(v)
                self.vehicles.pop(v.id, None)

        if self.phase == IDLE:
            if self.queue and self.auto_allocate:
                self._start_allocation(self.queue.popleft())
        elif self.phase == SEARCHING:
            if not self.step_mode:
                self._search_accum += dt * self._search_rate
                n = int(self._search_accum)
                if n:
                    self._search_accum -= n
                    self.search_shown += n
            if self.search_shown >= len(self.display_alloc.search.steps):
                self.search_shown = len(self.display_alloc.search.steps)
                self._finish_search()
        elif self.phase == SEARCH_DONE:
            if not self.step_mode:
                self._hold -= dt
                if self._hold <= 0:
                    self._begin_driving()
        elif self.phase == MOVING:
            v = self.active
            if v.update(dt, CAR_SPEED):
                self.lot.occupy(v.spot, v.id)
                v.state = PARKED
                self.active = None
                self.phase = IDLE
                self.say(f"{v.id} parked in {v.spot.id} ({SPOT_TYPE_NAMES[v.spot.type]}). "
                         f"The spot is now OCCUPIED.", "ok")

    def _random_event(self):
        occupied = [s for s in self.lot.spots if s.status == OCCUPIED]
        if occupied and self.rng.random() < 0.25 + 0.5 * len(occupied) / len(self.lot.spots):
            self.release_spot(self.rng.choice(occupied))
        if len(self.queue) < MAX_QUEUE and self.rng.random() < 0.85:
            self.add_vehicle(random_vehicle_type(self.rng))

    # ----------------------------------------------------------- toggles
    def toggle_strategy(self):
        self.strategy = BASELINE if self.strategy == AI else AI
        self.say(f"Strategy: {STRATEGY_NAMES[self.strategy]} (used for the next vehicle).")

    def toggle_step_mode(self):
        self.step_mode = not self.step_mode
        if self.step_mode:
            self.say("Step mode ON: each SPACE press expands one A* node.")
        else:
            self.say("Step mode OFF: the A* search is replayed automatically.")

    def toggle_pause(self):
        self.paused = not self.paused
        self.say("Paused." if self.paused else "Resumed.")

    def toggle_auto(self):
        self.auto_allocate = not self.auto_allocate
        self.say("Auto-allocate ON." if self.auto_allocate
                 else "Auto-allocate OFF: press ENTER to allocate each waiting vehicle.")

    def toggle_random_arrivals(self):
        self.random_arrivals = not self.random_arrivals
        if self.random_arrivals:
            self.auto_allocate = True
            self._arrival_timer = 0.0
            self.say("Random arrivals ON: vehicles arrive and leave automatically.")
        else:
            self.say("Random arrivals OFF.")

    def cycle_speed(self):
        self.speed_index = (self.speed_index + 1) % len(SPEEDS)
        self.say(f"Speed {self.speed:g}x")

    def change_speed(self, step):
        self.speed_index = max(0, min(len(SPEEDS) - 1, self.speed_index + step))
        self.say(f"Speed {self.speed:g}x")

    # ------------------------------------------------- selection / leave
    def spot_clicked(self, spot):
        if spot.vehicle_id in self.vehicles:
            self.selected_id = spot.vehicle_id
            extra = " Press D or right-click to release it." if spot.status == OCCUPIED else ""
            self.say(f"Selected {spot.vehicle_id} ({spot.status} {spot.id}).{extra}")
        else:
            self.selected_id = None
            self.say(f"{spot.id} ({SPOT_TYPE_NAMES[spot.type]}) is {spot.status}.")

    def focus_vehicle(self):
        """Vehicle whose details are shown in the side panel."""
        if self.selected_id in self.vehicles:
            return self.vehicles[self.selected_id]
        return self.active or self.last_vehicle

    def release_spot(self, spot):
        if spot.status == RESERVED:
            self.say(f"{spot.id} is reserved for {spot.vehicle_id}, which is on its way.", "warn")
            return False
        if spot.status == AVAILABLE:
            self.say(f"{spot.id} is already free.", "warn")
            return False
        v = self.vehicles[spot.vehicle_id]
        route = astar(spot.cell, self.lot.exit, self.lot.neighbours, record_steps=False)
        if not route.found:
            self.say(f"{v.id} cannot reach the exit from {spot.id} (roads blocked). "
                     f"Unblock a road first.", "warn")
            return False
        self.lot.release(spot)
        v.state = LEAVING
        v.spot = None
        v.set_route(route.path)
        self.leaving.append(v)
        if self.selected_id == v.id:
            self.selected_id = None
        self.say(f"{v.id} left {spot.id} and drives to the EXIT ({route.cost} moves). "
                 f"{spot.id} is available again.")
        return True

    def release_selected_or_random(self):
        v = self.vehicles.get(self.selected_id)
        if v is not None and v.state == PARKED:
            return self.release_spot(v.spot)
        occupied = [s for s in self.lot.spots if s.status == OCCUPIED]
        if not occupied:
            self.say("There are no parked cars to release.", "warn")
            return False
        return self.release_spot(self.rng.choice(occupied))

    # ------------------------------------------------- roads / obstacles
    def _moving_vehicles(self):
        moving = list(self.leaving)
        if self.phase == MOVING and self.active is not None:
            moving.append(self.active)
        return moving

    def toggle_block(self, cell):
        if not self.lot.is_blockable(cell):
            return False
        if cell in self.lot.blocked:
            self.lot.blocked.discard(cell)
            self.say(f"Road {cell} unblocked.")
            self._layout_changed()
            return True
        return self.block_cell(cell)

    def block_cell(self, cell, notify=True):
        """Block a road cell. Refused if it would trap a car or cut the entrance off."""
        lot = self.lot
        if not lot.is_blockable(cell) or cell in lot.blocked:
            return False
        moving = self._moving_vehicles()
        for v in moving:
            if cell in (v.cell, v.next_cell()):
                if notify:
                    self.say(f"Cannot block {cell}: {v.id} is driving over it right now.", "warn")
                return False

        lot.blocked.add(cell)
        if lot.exit not in lot.reachable_from(lot.entrance):
            lot.blocked.discard(cell)
            if notify:
                self.say("Cannot block that road: it would cut the entrance off from the exit.", "warn")
            return False

        # Cars already driving through this cell get a new A* route from the
        # cell they are entering (dynamic re-routing).
        reroutes = []
        for v in moving:
            if cell in v.remaining_cells():
                result = astar(v.next_cell(), v.path[-1], lot.neighbours, record_steps=False)
                if not result.found:
                    lot.blocked.discard(cell)
                    if notify:
                        self.say(f"Cannot block {cell}: {v.id} would have no route left.", "warn")
                    return False
                reroutes.append((v, result))
        for v, result in reroutes:
            v.reroute(result.path)

        if notify:
            note = ""
            if reroutes:
                note = f" A* re-routed {', '.join(v.id for v, _ in reroutes)} around it."
            self.say(f"Road {cell} blocked.{note}")
            self._layout_changed()
        return True

    def add_random_obstacles(self, count=3):
        cells = [c for c in self.lot.road_cells() if c not in self.lot.blocked]
        self.rng.shuffle(cells)
        added = []
        for cell in cells:
            if len(added) == count:
                break
            if self.block_cell(cell, notify=False):
                added.append(cell)
        if added:
            self.say(f"Added {len(added)} random road blocks: {', '.join(map(str, added))}.")
            self._layout_changed()
        else:
            self.say("No road cell could be blocked safely.", "warn")

    def clear_blocks(self):
        self.lot.blocked.clear()
        self.say("All road blocks cleared.")
        self._layout_changed()

    def _layout_changed(self):
        """If a search is on screen, its route may now be wrong: re-run the allocation."""
        if self.phase in (SEARCHING, SEARCH_DONE) and self.active is not None:
            v = self.active
            old = v.allocation
            self.metrics[old.strategy].record(old, sign=-1)   # replace, don't double count
            self.lot.release(old.spot)
            v.spot, v.allocation, v.state = None, None, WAITING
            self.vehicles.pop(v.id, None)
            self.active = None
            self.phase = IDLE
            self._start_allocation(v)
            if v.allocation.success:
                self.say(f"Layout changed during the search - A* re-planned {v.id} -> "
                         f"{v.spot.id} ({v.allocation.route_length} moves).")
