"""
astar.py - A* search, written from scratch (no pathfinding libraries).

The parking lot is a grid. A car moves one cell up, down, left or right and
every move costs 1. A* finds the cheapest route from a start cell to a goal
cell by always expanding the node with the smallest

    f(n) = g(n) + h(n)

    g(n) = real cost of the best route found so far from the start to n
    h(n) = Manhattan distance |dr| + |dc| from n to the goal (an estimate)
    f(n) = estimated cost of the complete route  start -> n -> goal

Why Manhattan distance?
    * Admissible: with 4-direction moves of cost 1 a car needs AT LEAST
      |dr| + |dc| moves; obstacles can only make the route longer, so h never
      over-estimates.
    * Consistent: one move changes h by at most 1, which is exactly the move
      cost. So the first time A* expands a node, its g value is already optimal,
      and a closed node never has to be re-opened.
  => A* returns a shortest route.
"""

import heapq
import math
import time
from dataclasses import dataclass, field

MOVE_COST = 1


def manhattan(a, b):
    """Heuristic h(n): Manhattan distance between two (row, col) cells."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


@dataclass
class SearchStep:
    """One expansion of A*, stored so the UI can replay the search step by step."""
    node: tuple      # cell taken out of the open set
    g: int
    h: int
    f: int
    added: list      # (cell, g, h) for neighbours added to / improved in the open set


@dataclass
class SearchResult:
    start: tuple
    goal: tuple
    path: list = field(default_factory=list)   # [start, ..., goal], or [] if unreachable
    cost: float = math.inf                      # number of moves (inf if unreachable)
    nodes_explored: int = 0                     # nodes expanded (moved to the closed set)
    time_ms: float = 0.0                        # wall-clock time of this search
    steps: list = field(default_factory=list)   # SearchStep list in expansion order

    @property
    def found(self):
        return bool(self.path)


def reconstruct_path(came_from, node):
    """Follow parent links back from the goal to the start, then reverse."""
    path = [node]
    while node in came_from:
        node = came_from[node]
        path.append(node)
    path.reverse()
    return path


def astar(start, goal, neighbours, heuristic=manhattan, record_steps=True):
    """
    start, goal  : (row, col) cells
    neighbours   : function(cell, goal) -> cells a car may move to from `cell`
    heuristic    : function(cell, goal) -> estimated remaining cost
    record_steps : keep every expansion (needed only for the visual replay)

    Returns a SearchResult. If the goal cannot be reached, result.path is []
    and result.cost is infinity - the caller decides what to do.
    """
    t0 = time.perf_counter()
    result = SearchResult(start, goal)

    # OPEN set: priority queue of (f, h, tie_breaker, cell).
    # Equal f values are broken by smaller h (closer to the goal) and then by
    # insertion order, so the search is fully deterministic.
    h0 = heuristic(start, goal)
    counter = 0
    open_heap = [(h0, h0, counter, start)]
    g_score = {start: 0}     # best known cost from start to each cell
    came_from = {}           # parent of each discovered cell (for the final path)
    closed = set()           # cells that have already been expanded

    while open_heap:
        f, h, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue  # outdated queue entry: this cell was already expanded more cheaply

        closed.add(current)
        g = g_score[current]
        added = []

        # Goal test happens when the goal is EXPANDED (not when it is first seen);
        # this is what makes A* optimal.
        if current == goal:
            result.path = reconstruct_path(came_from, current)
            result.cost = g
            if record_steps:
                result.steps.append(SearchStep(current, g, h, f, added))
            break

        for nb in neighbours(current, goal):
            if nb in closed:
                continue
            tentative_g = g + MOVE_COST
            if tentative_g < g_score.get(nb, math.inf):
                # Found a cheaper way to reach nb: remember it and (re)queue it.
                g_score[nb] = tentative_g
                came_from[nb] = current
                h_nb = heuristic(nb, goal)
                counter += 1
                heapq.heappush(open_heap, (tentative_g + h_nb, h_nb, counter, nb))
                added.append((nb, tentative_g, h_nb))

        if record_steps:
            result.steps.append(SearchStep(current, g, h, f, added))

    result.nodes_explored = len(closed)
    result.time_ms = (time.perf_counter() - t0) * 1000.0
    return result
