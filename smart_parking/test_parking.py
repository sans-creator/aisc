"""
test_parking.py - Correctness checks for A*, allocation and the simulation.

Run:  python -m unittest -v test_parking
"""

import math
import random
import unittest
from collections import deque

from allocator import AI, BASELINE, allocate
from astar import astar, manhattan
from benchmark import run_benchmark
from parking_lot import (ParkingLot, SPOT, OBSTACLE, WALL, AVAILABLE, RESERVED, OCCUPIED,
                         REGULAR, EV, ACCESSIBLE)
from simulation import Simulation, IDLE, MOVING
from vehicle import PARKED


def grid_neighbours(rows, cols, walls=frozenset()):
    def neighbours(cell, goal):
        r, c = cell
        out = []
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nb = (r + dr, c + dc)
            if 0 <= nb[0] < rows and 0 <= nb[1] < cols and nb not in walls:
                out.append(nb)
        return out
    return neighbours


def bfs_distance(start, goal, neighbours):
    """Ground-truth shortest distance (unit costs) for checking A*."""
    dist = {start: 0}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        if cell == goal:
            return dist[cell]
        for nb in neighbours(cell, goal):
            if nb not in dist:
                dist[nb] = dist[cell] + 1
                queue.append(nb)
    return math.inf


class PathAssertions(unittest.TestCase):
    def assertValidPath(self, path, start, goal):
        self.assertEqual(path[0], start)
        self.assertEqual(path[-1], goal)
        for a, b in zip(path, path[1:]):
            self.assertEqual(manhattan(a, b), 1, f"{a} -> {b} is not a single 4-direction move")


class TestAStar(PathAssertions):
    def test_shortest_path_in_open_grid(self):
        res = astar((0, 0), (4, 4), grid_neighbours(5, 5))
        self.assertTrue(res.found)
        self.assertEqual(res.cost, 8)
        self.assertEqual(len(res.path), 9)
        self.assertValidPath(res.path, (0, 0), (4, 4))

    def test_avoids_obstacles(self):
        walls = frozenset({(0, 2), (1, 2), (2, 2), (3, 2)})   # wall with a gap at the bottom
        nb = grid_neighbours(5, 5, walls)
        res = astar((0, 0), (0, 4), nb)
        self.assertTrue(res.found)
        self.assertFalse(set(res.path) & walls)
        self.assertEqual(res.cost, 12)
        self.assertEqual(res.cost, bfs_distance((0, 0), (0, 4), nb))
        self.assertValidPath(res.path, (0, 0), (0, 4))

    def test_unreachable_goal_returns_no_path(self):
        walls = frozenset({(1, 2), (3, 2), (2, 1), (2, 3)})    # goal (2,2) boxed in
        res = astar((0, 0), (2, 2), grid_neighbours(5, 5, walls))
        self.assertFalse(res.found)
        self.assertEqual(res.path, [])
        self.assertEqual(res.cost, math.inf)

    def test_start_equals_goal(self):
        res = astar((1, 1), (1, 1), grid_neighbours(3, 3))
        self.assertEqual(res.path, [(1, 1)])
        self.assertEqual(res.cost, 0)

    def test_optimal_and_valid_on_parking_lot(self):
        lot = ParkingLot()
        for spot in lot.spots:
            res = astar(lot.entrance, spot.cell, lot.neighbours)
            self.assertEqual(res.cost, bfs_distance(lot.entrance, spot.cell, lot.neighbours), spot.id)
            if res.found:
                self.assertValidPath(res.path, lot.entrance, spot.cell)
                for cell in res.path[1:-1]:   # only roads in between
                    self.assertTrue(lot.is_drivable(cell), f"{spot.id}: path crosses {cell}")

    def test_manhattan_is_admissible_and_consistent(self):
        lot = ParkingLot()
        drivable = [c for c in lot.grid if lot.is_drivable(c)]
        for spot in lot.spots[::4]:
            goal = spot.cell
            for cell in drivable:
                true_cost = bfs_distance(cell, goal, lot.neighbours)
                self.assertLessEqual(manhattan(cell, goal), true_cost)          # admissible
                for nb in lot.neighbours(cell, goal):                          # consistent
                    self.assertLessEqual(manhattan(cell, goal), 1 + manhattan(nb, goal))

    def test_layout_offers_alternative_routes(self):
        """Blocking one lane cell must still leave a route (the lot is not a tree)."""
        lot = ParkingLot(blocked=())
        target = lot.spot_by_id["P27"].cell
        first = astar(lot.entrance, target, lot.neighbours)
        lot.blocked.add(first.path[len(first.path) // 2])
        second = astar(lot.entrance, target, lot.neighbours)
        self.assertTrue(second.found)
        self.assertNotEqual(first.path, second.path)


class TestAllocator(PathAssertions):
    def test_never_assigns_occupied_or_reserved_spot(self):
        for strategy in (AI, BASELINE):
            lot = ParkingLot()
            lot.place_initial_cars()
            initially_taken = {s.id for s in lot.spots if s.status == OCCUPIED}
            assigned = []
            for i in range(60):
                before = {s.id: s.status for s in lot.spots}
                alloc = allocate(lot, REGULAR, lot.entrance, strategy, vehicle_id=f"T{i}")
                if not alloc.success:
                    break
                self.assertEqual(before[alloc.spot.id], AVAILABLE)
                self.assertEqual(alloc.spot.status, RESERVED)
                self.assertEqual(alloc.spot.vehicle_id, f"T{i}")
                assigned.append(alloc.spot.id)
            self.assertEqual(len(assigned), len(set(assigned)), "a spot was assigned twice")
            self.assertFalse(set(assigned) & initially_taken)

    def test_reserving_twice_is_rejected(self):
        lot = ParkingLot()
        spot = lot.spots[0]
        lot.reserve(spot, "A")
        with self.assertRaises(ValueError):
            lot.reserve(spot, "B")
        with self.assertRaises(ValueError):
            lot.occupy(spot, "B")

    def test_eligibility_rules(self):
        for strategy in (AI, BASELINE):
            lot = ParkingLot()
            # Regular cars never take EV or accessible spots
            for i in range(60):
                alloc = allocate(lot, REGULAR, lot.entrance, strategy, vehicle_id=f"R{i}")
                if not alloc.success:
                    break
                self.assertEqual(alloc.spot.type, REGULAR)
            # Lot is now full of regular cars: EV gets an EV spot while one is free
            n_ev = sum(1 for s in lot.spots if s.type == EV)
            for i in range(n_ev):
                alloc = allocate(lot, EV, lot.entrance, strategy, vehicle_id=f"E{i}")
                self.assertTrue(alloc.success)
                self.assertEqual(alloc.spot.type, EV)
                self.assertFalse(alloc.used_fallback)
            # No EV spot and no regular spot left -> graceful failure
            alloc = allocate(lot, EV, lot.entrance, strategy, vehicle_id="E-extra")
            self.assertFalse(alloc.success)
            self.assertIn("turned away", alloc.reason)

    def test_fallback_to_regular_spot(self):
        lot = ParkingLot()
        for s in lot.spots:
            if s.type == ACCESSIBLE:
                lot.occupy(s, "X")
        alloc = allocate(lot, ACCESSIBLE, lot.entrance, AI, vehicle_id="A1")
        self.assertTrue(alloc.success)
        self.assertEqual(alloc.spot.type, REGULAR)
        self.assertTrue(alloc.used_fallback)

    def test_both_strategies_work_and_ai_route_is_never_longer(self):
        rng = random.Random(7)
        for trial in range(25):
            blocked = rng.sample(ParkingLot().road_cells(), 3)
            occupied = rng.sample(range(40), rng.randint(0, 30))
            vtype = rng.choice([REGULAR, EV, ACCESSIBLE])
            results = {}
            for strategy in (AI, BASELINE):
                lot = ParkingLot(blocked=blocked)
                for i in occupied:
                    lot.occupy(lot.spots[i], "X")
                results[strategy] = allocate(lot, vtype, lot.entrance, strategy)
            ai, base = results[AI], results[BASELINE]
            self.assertEqual(ai.success, base.success, f"trial {trial}")
            if ai.success:
                self.assertValidPath(ai.search.path, ai.start, ai.spot.cell)
                self.assertValidPath(base.search.path, base.start, base.spot.cell)
                self.assertLessEqual(ai.route_length, base.route_length, f"trial {trial}")

    def test_unreachable_spots_are_handled(self):
        lot = ParkingLot()
        lot.blocked.add((2, 1))            # the only road leaving the entrance
        for strategy in (AI, BASELINE):
            alloc = allocate(lot, REGULAR, lot.entrance, strategy, vehicle_id="U")
            self.assertFalse(alloc.success)
            self.assertTrue(all(s.status != RESERVED for s in lot.spots))


class TestSimulation(unittest.TestCase):
    def run_until_idle(self, sim, max_seconds=120):
        for _ in range(int(max_seconds * 60)):
            sim.update(1 / 60)
            if sim.phase == IDLE and not sim.queue and not sim.leaving:
                return
        self.fail("simulation did not settle")

    def assertConsistent(self, sim):
        owners = {}
        for spot in sim.lot.spots:
            if spot.status in (RESERVED, OCCUPIED):
                self.assertIn(spot.vehicle_id, sim.vehicles, spot.id)
                self.assertIs(sim.vehicles[spot.vehicle_id].spot, spot)
                self.assertNotIn(spot.vehicle_id, owners, "vehicle holds two spots")
                owners[spot.vehicle_id] = spot.id
            else:
                self.assertIsNone(spot.vehicle_id)

    def test_arrivals_departures_and_repeated_arrivals(self):
        for strategy in (AI, BASELINE):
            sim = Simulation()
            sim.strategy = strategy
            for vtype in (REGULAR, EV, ACCESSIBLE, REGULAR, REGULAR):
                sim.add_vehicle(vtype)
            self.run_until_idle(sim)
            self.assertConsistent(sim)
            for vid in ("V1", "V2", "V3", "V4", "V5"):
                self.assertEqual(sim.vehicles[vid].state, PARKED)
            spot = sim.vehicles["V2"].spot
            self.assertTrue(sim.release_spot(spot))
            self.run_until_idle(sim)
            self.assertNotIn("V2", sim.vehicles)
            self.assertEqual(spot.status, AVAILABLE)
            for _ in range(4):
                sim.add_vehicle(REGULAR)
            self.run_until_idle(sim)
            self.assertConsistent(sim)
            self.assertEqual(sim.metrics[strategy].parked, 9)

    def test_full_lot_fails_gracefully(self):
        sim = Simulation()
        for _ in range(40):
            sim.add_vehicle(REGULAR)
            self.run_until_idle(sim)
        self.assertGreater(sim.metrics[AI].failed, 0)
        self.assertConsistent(sim)

    def test_reset(self):
        sim = Simulation()
        sim.add_vehicle(REGULAR)
        self.run_until_idle(sim)
        sim.add_random_obstacles()
        sim.reset()
        self.assertEqual(sim.metrics[AI].allocations, 0)
        self.assertEqual(sim.lot.count(OCCUPIED), 10)
        self.assertEqual(sim.lot.count(RESERVED), 0)
        self.assertConsistent(sim)

    def test_step_mode_waits_for_user(self):
        sim = Simulation()
        sim.step_mode = True
        sim.add_vehicle(REGULAR)
        for _ in range(120):
            sim.update(1 / 60)
        self.assertEqual(sim.search_shown, 0)
        sim.next_step()
        sim.next_step()
        self.assertEqual(sim.search_shown, 2)

    def test_blocking_route_reroutes_or_is_refused(self):
        sim = Simulation()
        sim.clear_blocks()
        sim.release_spot(sim.lot.spot_by_id["P2"])        # free some spots far away
        self.run_until_idle(sim)
        for s in sim.lot.spots[:12]:
            if s.status == AVAILABLE:
                sim.lot.occupy(s, "X")
        sim.add_vehicle(REGULAR)
        while sim.phase != MOVING:
            sim.update(1 / 60)
        v = sim.active
        ahead = [c for c in v.path[v.seg + 2:] if sim.lot.is_blockable(c)]
        self.assertTrue(ahead)
        cell = ahead[len(ahead) // 2]
        if sim.toggle_block(cell):
            self.assertNotIn(cell, v.remaining_cells())
        self.run_until_idle(sim)
        self.assertEqual(v.state, PARKED)


class TestBenchmark(unittest.TestCase):
    def test_deterministic_and_complete(self):
        a = run_benchmark(seeds=(1, 2), n_events=30)
        b = run_benchmark(seeds=(1, 2), n_events=30)
        for strategy in (AI, BASELINE):
            ma, mb = a["results"][strategy], b["results"][strategy]
            self.assertEqual((ma.parked, ma.failed, ma.total_distance, ma.nodes_explored),
                             (mb.parked, mb.failed, mb.total_distance, mb.nodes_explored))
            self.assertEqual(ma.allocations, a["arrivals"])


if __name__ == "__main__":
    unittest.main()
