"""
benchmark.py - Fair, repeatable comparison of the AI and baseline strategies.

Both strategies get EXACTLY the same layout, the same blocked roads, the same
pre-parked cars and the same sequence of arrivals and departures (generated
from fixed random seeds). Only the destination-selection rule differs.
Vehicles are placed instantly (no animation), so the benchmark runs in about
a second. Departures here are instantaneous (the car is simply removed).

Run from a terminal:   python benchmark.py
"""

import random

from allocator import AI, BASELINE, allocate
from metrics import Metrics, comparison_rows
from parking_lot import ParkingLot, DEFAULT_BLOCKED, REGULAR, EV, ACCESSIBLE

VEHICLE_MIX = ((REGULAR, 0.70), (EV, 0.18), (ACCESSIBLE, 0.12))
DEFAULT_SEEDS = (1, 2, 3, 4, 5)
DEFAULT_EVENTS = 60


def random_vehicle_type(rng):
    types = [t for t, _ in VEHICLE_MIX]
    weights = [w for _, w in VEHICLE_MIX]
    return rng.choices(types, weights=weights)[0]


def generate_scenario(seed, n_events=DEFAULT_EVENTS, arrival_prob=0.65):
    """List of ("arrive", vehicle_id, type) and ("depart", vehicle_id, None) events."""
    rng = random.Random(seed)
    events, present, n = [], [], 0
    for _ in range(n_events):
        if present and rng.random() >= arrival_prob:
            vehicle_id = present.pop(rng.randrange(len(present)))
            events.append(("depart", vehicle_id, None))
        else:
            n += 1
            vehicle_id = f"V{n}"
            present.append(vehicle_id)
            events.append(("arrive", vehicle_id, random_vehicle_type(rng)))
    return events


def run_scenario(strategy, events, blocked=DEFAULT_BLOCKED, metrics=None):
    lot = ParkingLot(blocked=blocked)
    lot.place_initial_cars()
    metrics = metrics if metrics is not None else Metrics()
    parked = {}
    for kind, vehicle_id, vehicle_type in events:
        if kind == "arrive":
            alloc = allocate(lot, vehicle_type, lot.entrance, strategy,
                             vehicle_id=vehicle_id, record_steps=False)
            metrics.record(alloc)
            if alloc.success:
                lot.occupy(alloc.spot, vehicle_id)
                parked[vehicle_id] = alloc.spot
        else:
            spot = parked.pop(vehicle_id, None)   # no-op if this vehicle was turned away
            if spot is not None:
                lot.release(spot)
    return metrics


def run_benchmark(blocked=DEFAULT_BLOCKED, seeds=DEFAULT_SEEDS, n_events=DEFAULT_EVENTS):
    results = {AI: Metrics(), BASELINE: Metrics()}
    arrivals = 0
    for seed in seeds:
        events = generate_scenario(seed, n_events)
        arrivals += sum(1 for e in events if e[0] == "arrive")
        for strategy in (AI, BASELINE):
            run_scenario(strategy, events, blocked, results[strategy])
    return {"results": results, "seeds": tuple(seeds), "events": n_events,
            "arrivals": arrivals, "blocked": len(blocked)}


def print_report(title, bench):
    res = bench["results"]
    print(f"\n{title}")
    print(f"seeds {bench['seeds']}, {bench['events']} events each, "
          f"{bench['arrivals']} arrivals in total, {bench['blocked']} blocked road cell(s)")
    print(f"{'Metric':30}{'AI':>12}{'Baseline':>12}")
    print("-" * 54)
    for label, a, b in comparison_rows(res[AI], res[BASELINE]):
        print(f"{label:30}{a:>12}{b:>12}")


if __name__ == "__main__":
    print_report("Default layout (with the maintenance block)", run_benchmark())
    print_report("Same layout, no blocked roads", run_benchmark(blocked=()))
