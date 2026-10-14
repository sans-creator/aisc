"""
metrics.py - Counters used to compare allocation strategies.

Every number is computed from real allocation results; nothing is hard-coded.

Definitions
  Successful allocations  vehicles that received a spot
  Failed allocations      vehicles with no reachable eligible spot (turned away)
  Total route length      sum of the A* route lengths entrance -> assigned spot (cells)
  Avg path length         total route length / successful allocations
  Avg nodes / A* search   nodes expanded per A* call (search effort of ONE search)
  A* searches / vehicle   how many A* calls one allocation decision needed
  Avg A* time             time of ONE A* search (pathfinding time)
  Avg allocation time     time of the WHOLE decision per vehicle (all A* calls + selection)
"""


class Metrics:
    def __init__(self):
        self.allocations = 0
        self.parked = 0
        self.failed = 0
        self.total_distance = 0
        self.astar_calls = 0
        self.nodes_explored = 0
        self.pathfinding_ms = 0.0
        self.allocation_ms = 0.0

    def record(self, alloc, sign=1):
        """Add (sign=1) or remove (sign=-1, used when an allocation is re-planned)."""
        self.allocations += sign
        if alloc.success:
            self.parked += sign
            self.total_distance += sign * alloc.route_length
        else:
            self.failed += sign
        self.astar_calls += sign * alloc.astar_calls
        self.nodes_explored += sign * alloc.nodes_explored
        self.pathfinding_ms += sign * alloc.pathfinding_ms
        self.allocation_ms += sign * alloc.allocation_ms

    @property
    def avg_path(self):
        return self.total_distance / self.parked if self.parked else 0.0

    @property
    def avg_nodes_per_search(self):
        return self.nodes_explored / self.astar_calls if self.astar_calls else 0.0

    @property
    def searches_per_vehicle(self):
        return self.astar_calls / self.allocations if self.allocations else 0.0

    @property
    def avg_astar_ms(self):
        return self.pathfinding_ms / self.astar_calls if self.astar_calls else 0.0

    @property
    def avg_allocation_ms(self):
        return self.allocation_ms / self.allocations if self.allocations else 0.0


def _avg(fmt, getter):
    return lambda m: (fmt.format(getter(m)) if m.allocations else "-")


ROWS = (
    ("Successful allocations", lambda m: str(m.parked)),
    ("Failed allocations", lambda m: str(m.failed)),
    ("Total route length (cells)", lambda m: str(m.total_distance)),
    ("Avg path length (cells)", _avg("{:.2f}", lambda m: m.avg_path)),
    ("Avg nodes / A* search", _avg("{:.1f}", lambda m: m.avg_nodes_per_search)),
    ("A* searches / vehicle", _avg("{:.1f}", lambda m: m.searches_per_vehicle)),
    ("Avg A* time (ms)", _avg("{:.3f}", lambda m: m.avg_astar_ms)),
    ("Avg allocation time (ms)", _avg("{:.3f}", lambda m: m.avg_allocation_ms)),
)


def comparison_rows(ai, baseline):
    """[(label, ai_value_text, baseline_value_text), ...]"""
    return [(label, fn(ai), fn(baseline)) for label, fn in ROWS]
