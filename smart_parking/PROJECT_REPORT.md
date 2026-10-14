# Smart Parking Space Allocation and Pathfinding Using A* Search
*AISC project: report material and viva preparation*

## Abstract
Drivers waste time and fuel looking for parking. Many simple systems send a driver to the
nearest free space as the crow flies, ignoring pillars, one-way lanes and closed roads.
This project models a parking lot as a grid and uses **A\* search** to find the shortest
drivable route from the entrance to each candidate space. Each arriving vehicle is given the
eligible free space with the **lowest real route cost**. The space is reserved so it cannot
be assigned twice. An interactive Pygame simulator shows the search step by step: the
explored nodes, the open set and the final path. The car then drives along that path.
The system supports EV-charging and accessible spaces, run-time road blocks with automatic
re-routing, departures, and random traffic. A benchmark compares the AI allocator with a
nearest-by-straight-line baseline on identical scenarios.

## Objectives
1. Represent a parking lot (40 spaces, lanes, pillars, entrance/exit) as a searchable grid.
2. Implement A* from scratch with an admissible, consistent heuristic.
3. Allocate spaces using real route costs, respecting vehicle eligibility, and never
   double-assign a space.
4. Visualise the A* search process and the vehicle's movement, including step-by-step mode.
5. Handle dynamic conditions (blocked roads, departures, full lot) without crashing.
6. Measure performance against a baseline using identical, reproducible scenarios.

## Methodology
**Environment.** An 18×9 grid. Road, entrance and exit cells are drivable. Walls, pillars
and blocked roads are not. A parking spot can be entered only when it is the search goal.
Each move (up, down, left, right) costs 1.

**Search problem formulation (for A\*)**
- *State:* the car's cell (row, col).
- *Initial state:* the entrance (or the car's current cell when re-routing / leaving).
- *Actions:* move to a 4-neighbour that is drivable, or is the goal spot.
- *Goal test:* the cell equals the target spot.
- *Path cost:* number of moves.
- *Heuristic:* h(n) = |r − r_goal| + |c − c_goal| (Manhattan distance).

**A\*.** The open set is a binary heap ordered by f = g + h. Ties are broken by smaller h,
then by insertion order. A node is expanded at most once (closed set). Parent links rebuild
the path. Each search returns the path, cost, number of nodes expanded and time taken.

**Allocation.**
1. Constraint filtering: keep spots that are available and of an eligible type, with an
   ordered fallback for EV and accessible vehicles.
2. Run A* to every candidate.
3. Discard unreachable candidates.
4. Choose the minimum route cost; ties go to the lower spot index.
5. Reserve the spot.

**Baseline.** Choose the nearest spot by Manhattan distance, then run A* only for the route.

**Evaluation.** Five seeded scenarios of 60 arrival/departure events each. Both strategies
start from the same initial lot and receive the same events.

### Flowchart
```
          +----------------------+
          |  Vehicle arrives     |
          +----------+-----------+
                     v
     +-------------------------------+
     | Filter: available + eligible  |<------------------+
     | spots (constraint filtering)  |                   |
     +---------------+---------------+                   |
                     v                                   |
     +-------------------------------+     no candidates |
     | For each candidate spot:      |     reachable     |
     |   run A* (f = g + h)          |---> try next tier +
     +---------------+---------------+     (EV/accessible -> regular)
                     v                         |
     +-------------------------------+         | no tiers left
     | Discard unreachable spots,    |         v
     | pick lowest route cost        |   +-------------------+
     +---------------+---------------+   | "No reachable     |
                     v                   |  spot" - turn away|
     +-------------------------------+   +-------------------+
     | RESERVE spot (purple)         |
     +---------------+---------------+
                     v
     +-------------------------------+
     | Replay A* search, draw path   |
     +---------------+---------------+
                     v
     +-------------------------------+   road blocked on route?
     | Car drives along path         |---> A* re-plans from next cell
     +---------------+---------------+
                     v
     +-------------------------------+
     | Spot OCCUPIED (red)           |
     +---------------+---------------+
                     v
     +-------------------------------+
     | Departure: release spot,      |
     | A* route to the exit          |
     +-------------------------------+
```

## Results (from `python benchmark.py`, seeds 1–5, 60 events each, 194 arrivals)

| Metric | AI | Baseline |
|---|---|---|
| Successful allocations | 194 | 194 |
| Failed allocations | 0 | 0 |
| Total route length (cells) | 1545 | 1746 |
| Avg path length (cells) | 7.96 | 9.00 |
| Avg nodes / A* search | 27.4 | 13.9 |
| A* searches / vehicle | 14.4 | 1.0 |
| Avg allocation time (ms) | ~1.7 | ~0.1 |

With the default road block, the AI routes were about 11.5% shorter in total. With no
blocks, the two strategies were almost equal (7.22 vs 7.26 cells on average), because
straight-line distance is then a good guide. The AI pays for its better choices with about
14× more A* searches per decision, but each decision still takes under 2 ms. Timing numbers vary
slightly from run to run. The benchmark recomputes everything; nothing is hard-coded.

## Viva questions and answers

**Why is this an AI problem?**
It is a state-space search problem: states, actions, a goal test and path cost. It is solved
with an informed (heuristic) search algorithm. The agent also decides between alternative
goals using the search results.

**A\* vs Greedy Best-First Search?**
Greedy uses f(n) = h(n) and only looks at how close a node *seems* to the goal. It can be
lured into dead ends next to the goal, and it does not guarantee the shortest path.
A* uses f(n) = g(n) + h(n): the real cost so far plus the estimate. With an admissible
heuristic it is optimal. Dijkstra is A* with h = 0. It is optimal too, but it explores more
nodes because it has no sense of direction.

**Role of g, h and f?**
g(n) is the exact cost from the start to n. h(n) is the estimated remaining cost. f(n) is the
estimated total cost of a route through n. A* always expands the lowest f.

**Why Manhattan distance?**
Cars move in 4 directions with a cost of 1 per move, so at least |dr| + |dc| moves are needed.
That means h never over-estimates (admissible). Obstacles only add moves. h also changes by at
most 1 per move (consistent), so each node is expanded once and the first path found to the
goal is optimal. Euclidean distance would also be admissible but is weaker (smaller), so A*
would explore more nodes. Diagonal-based heuristics would not match this movement model.

**Allocation vs route finding?**
Allocation decides *where* the car should go. Route finding decides *how* it gets there.
Here A* answers "how" and gives the real cost. The allocator uses those costs to answer
"where". They are in separate modules (`allocator.py`, `astar.py`).

**How do obstacles affect the search?**
Blocked cells are removed from the neighbour function, so A* must go around them. g grows
while h stays the same, so A* explores more nodes. If every route is cut, the open set empties
and A* reports "unreachable". The allocator then skips that spot.

**Why is the AI's route never longer than the baseline's for the same vehicle?**
Both strategies consider the same candidate set. The AI computes the exact optimal route
cost of every candidate and takes the minimum. The baseline picks one of those candidates.
Over a whole scenario the lot states diverge, so totals are measured, not assumed.

**Complexity in this implementation?**
One A* search: O(V log V) time with a binary heap. V ≤ 162 grid cells and each cell has at
most 4 edges. Space is O(V) for g, the parent links and the closed set. The AI decision runs
one A* per candidate: O(k · V log V) for k candidates (k ≤ 40). The baseline usually runs one
search. An optimisation: a single Dijkstra from the entrance gives the cost to *all* spots at
once, O(V log V) per decision.

**Is the allocation globally optimal?**
No. It is greedy per vehicle: each car gets the best spot *now*. A batch assignment
(Hungarian algorithm), or reserving close spots for expected arrivals, could do better
overall.

**Limitations and future work**
- No collisions or congestion between moving cars. Possible extensions: time-expanded A* or
  traffic-weighted edge costs (keep h admissible by using the minimum edge cost).
- Unit move costs. Real lots have turns, lane directions and speed bumps.
- Departures in the benchmark are instantaneous.
- Future work: one-way lanes, multi-level lots, walking distance to the shop entrance as a
  second objective, sensor/camera input, D* Lite for faster re-planning, fuzzy-logic
  preferences.
