# SmartPark: AI search for parking allocation (web version)

**How to open:** double-click `index.html`, or run `python -m http.server 8000` in this folder
and open http://localhost:8000. It uses plain HTML, CSS and JavaScript. Every algorithm is
written from scratch.

## Files

| File | What it does |
|---|---|
| `js/lot.js` | Grid, neighbours, and the **heuristic function** `h(n)` |
| `js/search.js` | **A\*, Best-First Search, Hill Climbing, DFS** |
| `js/allocator.js` | Picks the spot: the free eligible spot with the shortest real route (found by A\*) |
| `js/renderer.js` | Draws the map, explored cells, h-values and the route |
| `js/app.js` | Buttons, playback, the live h(n) calculation box, the comparison table |

## How g(n) and h(n) are calculated

- **g(n)** = number of moves from the entrance (IN) to cell n along the path found so far.
  Each move up, down, left or right adds 1.
- **h(n)** = Manhattan distance to the goal spot:
  `h(n) = |n.row − goal.row| + |n.col − goal.col|`. It ignores walls, so it is a lower bound
  (admissible).
- **f(n)** = g(n) + h(n), used only by A\*.

## The four algorithms

| Algorithm | Chooses next | Uses h(n)? | Result |
|---|---|---|---|
| A\* | smallest g + h | yes | always the shortest route |
| Best-First | smallest h | yes | fast, sometimes longer |
| Hill Climbing | neighbour with smallest h, never goes back | yes | can get stuck (local minimum) |
| DFS | newest node (stack) | no | finds a route, usually long |

## Demo

1. Select **A\***, then click spot **P39** on the map. Step with `→` and watch the
   "Heuristic function" box calculate h and f for each node.
2. Click the rows of the table ("All algorithms, same spot") to replay the same spot with
   each algorithm.
3. Select **Hill Climb** and click **P26**. It gets stuck at (4,1), which is a local minimum.
4. Select **DFS**. The map shows the visit order (1, 2, 3…) instead of h values.
5. Use **Start from beginning** to replay any search.
