# Smart Parking Space Allocation & Pathfinding using A* Search

An interactive Pygame simulator for the AISC course. Vehicles arrive at a parking lot. The
system chooses a suitable free spot and reserves it. The simulator then shows **A\* search**
exploring the grid and the car driving along the shortest route to its spot.

## 1. How to run (Windows + VS Code)

1. Install **Python 3.10 or newer** from python.org. During setup, tick **"Add python.exe to PATH"**.
2. Open the `smart_parking` folder in VS Code (**File → Open Folder**).
3. Open a terminal (**Terminal → New Terminal**) and run:

```powershell
python -m pip install -r requirements.txt
python main.py
```

Other commands:

```powershell
python -m unittest -v test_parking   # 19 correctness tests
python benchmark.py                  # AI vs baseline comparison printed in the terminal
```

## 2. Project structure

| File | Responsibility |
|---|---|
| `astar.py` | A* search written from scratch: `f(n) = g(n) + h(n)`, Manhattan heuristic, `heapq` open set, path reconstruction, and stats (path, cost, nodes explored, time). |
| `parking_lot.py` | The grid layout, the 40 parking spots (regular / EV / accessible), roads, pillars, blocked roads, and reserve / occupy / release. |
| `allocator.py` | Chooses the destination. It filters eligible spots, then applies the **AI** strategy (lowest A* route cost) or the **baseline** (nearest by Manhattan distance). It also writes the explanation shown on screen. |
| `vehicle.py` | Vehicle state and smooth movement along a path. |
| `simulation.py` | The state machine: queue, reservations, search replay, driving, departures, road blocks and re-routing, and metrics. Contains no drawing code. |
| `metrics.py` | Comparison metrics and their exact definitions. |
| `benchmark.py` | Fair comparison: both strategies get identical scenarios built from fixed random seeds. |
| `ui.py` | Pygame drawing, buttons, keyboard and mouse input, legend, side panel, overlays. |
| `main.py` | Opens the window and runs the game loop. |
| `test_parking.py` | Unit tests. |

**Destination selection** (`allocator.py`) is separate from **route finding** (`astar.py`).
The allocator uses A* as a tool to measure real route costs.

## 3. What happens when a car arrives

1. The car waits in the queue at the entrance (`IN`).
2. **Constraint filtering:** only *available* spots of an *eligible* type are candidates.
   - Regular car → regular spots only.
   - EV → EV charging spots first, then a regular spot if none is free and reachable.
   - Accessible vehicle → accessible spots first, then a regular spot.
3. **Spot choice:**
   - **AI mode:** run A* from the entrance to *every* candidate. Discard unreachable spots.
     Pick the lowest route cost; ties go to the lower spot number. The A* cost of each
     candidate is printed on its spot (`--` means unreachable).
   - **Baseline mode:** pick the spot with the smallest straight-line (Manhattan) distance,
     printed as `m5`, then run A* only to that spot. If it is unreachable, try the next one.
4. The chosen spot is **reserved** (purple), so no other vehicle can get it.
5. The A* search is **replayed on the grid**. Yellow cells are explored (closed set),
   yellow-outlined cells are the open set, and the white box is the node being expanded.
6. The final **blue path** appears and the car drives along it. The spot turns **red** (occupied).
7. When a car is released, its spot becomes **green** again. The car drives to `OUT` along a
   new A* route.

If no eligible spot is reachable, the car is turned away. A message explains why, and the
program keeps running.

## 4. Controls

| Key / Button | Action |
|---|---|
| `1` / `2` / `3` | Add regular car / EV / accessible vehicle |
| `Enter` | Allocate next waiting vehicle (when Auto-Allocate is OFF) |
| `A` | Auto-allocate ON/OFF |
| `R` | Random arrivals and departures ON/OFF |
| `M` | Switch strategy: AI ↔ Baseline |
| `S` | Step mode ON/OFF. In step mode, A* expands one node per key press |
| `Space` / `N` | Next A* step (or start driving after the search finishes) |
| `P` | Pause / resume |
| `F`, `+`, `-` | Speed 0.5x / 1x / 2x / 4x |
| `V` | Show / hide explored nodes |
| `D` | Release the selected parked car (or a random one) |
| `O` / `C` | Add 3 random road blocks / clear all blocks |
| `B` | Run the benchmark (AI vs baseline on identical scenarios) |
| `H` | Help screen |
| `X` | Reset |
| `Esc` / `Q` | Close overlay / quit |
| **Left-click road** | Block / unblock it. Cars already driving are re-routed by A* |
| **Left-click spot** | Select the car parked there (details appear in the side panel) |
| **Right-click parked car** | Release it |
| **Hover a cell** | Shows `g`, `h`, `f` for cells A* has explored |

In step mode, every explored cell also shows its `f` value.

## 5. Suggested 5-minute demo

1. **Start:** explain the colours using the legend. Point out the orange striped block on the
   top lane and the orange pillars.
2. Press `S` (step mode), then `1`. Press `Space` a few times. Show the panel line
   `Expanding (r,c): g + h = f`, the yellow closed set and the outlined open set. Hover a cell
   to show its g/h/f. Keep pressing until the path appears, then press `Space` once more to drive.
3. Press `S` to turn step mode off. Add 5–6 cars with `1` so the left side fills up.
4. Press `2` (EV). The numbers on the EV spots show the real A* cost of each candidate.
   The panel explains why the chosen spot won.
5. Click a few road cells to block them. Add a car and show it taking a detour. Click a road
   ahead of a moving car and show it being re-routed.
6. Press `M` (baseline), then add cars. The labels now show straight-line `m` distances. The
   "Why" panel shows the extra moves caused by obstacles.
7. Press `B` for the fair benchmark. Discuss the trade-off: shorter routes in exchange for more
   A* searches.
8. Right-click a parked car to release it, then `R` for random traffic.

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| `'python' is not recognized` | Reinstall Python with "Add to PATH" ticked, or use `py main.py` and `py -m pip install pygame`. |
| `ModuleNotFoundError: No module named 'pygame'` | Run `python -m pip install pygame` in the same terminal. If VS Code uses another interpreter, pick the right one with **Ctrl+Shift+P → Python: Select Interpreter**. |
| `pip` fails to build pygame | Your Python is very new or 32-bit. Install the latest 64-bit Python 3.12, or try `python -m pip install pygame --pre`. |
| Window is too big or blurry | The program scales itself to fit the screen. A small amount of blur on high-DPI screens is normal. |
| Clicks do nothing | Close the Help or Benchmark overlay first (`Esc`). |
| Nothing moves after adding a car | Check whether it is paused (`P`), whether step mode is on (press `Space`), or whether Auto-Allocate is off (press `Enter`). |
| "Cannot block that road" | The block would trap a moving car or cut the entrance off from the exit. This is intentional. |
| Car is "turned away" | No eligible free spot is reachable. Release a car (`D`) or clear blocks (`C`). |
