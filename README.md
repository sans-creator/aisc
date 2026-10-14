# Smart Parking Space Allocation using AI Search

AISC course project. Vehicles arrive at a parking lot, the system allocates a suitable free
spot, and an AI search algorithm finds the route to it.

**Live demo:** https://sans-creator.github.io/aisc/

| Folder | What it is |
|---|---|
| [`smart_parking_web/`](smart_parking_web/) | Web simulator (HTML/CSS/JS): A\*, Best-First Search, Hill Climbing and DFS, with live g(n) / h(n) values. Open `index.html` to run it. |
| [`smart_parking/`](smart_parking/) | Python + Pygame simulator with an A\* allocator, a baseline comparison, tests (`python -m unittest test_parking`) and `PROJECT_REPORT.md`. |
