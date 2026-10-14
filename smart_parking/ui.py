"""
ui.py - Everything the user sees and clicks (Pygame drawing + input).

The UI makes no parking decisions: it calls Simulation methods and draws the
current state. Everything is drawn on a fixed 1280x720 "logical" canvas;
main.py scales it to fit smaller laptop screens.
"""

import math

import pygame

import benchmark
from allocator import AI, BASELINE, STRATEGY_NAMES, STRATEGY_SHORT
from metrics import comparison_rows
from parking_lot import (WALL, ROAD, OBSTACLE, SPOT, ENTRANCE, EXIT,
                         AVAILABLE, RESERVED, OCCUPIED, REGULAR, EV, ACCESSIBLE, SPOT_TYPE_NAMES)
from simulation import IDLE, SEARCHING, SEARCH_DONE, MOVING
from vehicle import ALLOCATING, DRIVING, PARKED, LEAVING, STATE_NAMES, GONE

LOGICAL_W, LOGICAL_H = 1280, 720
CELL = 48
LOT_X, LOT_Y = 16, 58
PANEL_X, PANEL_W = 900, 364

C = {
    "bg": (22, 25, 32), "panel": (33, 37, 46), "panel_edge": (55, 61, 74),
    "text": (232, 235, 240), "muted": (150, 158, 172), "dark": (18, 20, 26),
    "grass": (38, 66, 49), "grass2": (34, 60, 44),
    "road": (98, 102, 110), "road_line": (86, 90, 98), "lane_mark": (150, 150, 120),
    "spot_base": (62, 66, 74),
    "available": (46, 170, 92), "reserved": (150, 82, 205), "occupied": (205, 62, 52),
    "obstacle": (238, 132, 40),
    "explored": (245, 200, 30), "frontier": (255, 236, 140), "path": (52, 142, 255),
    "car": (246, 246, 246), "ev": (0, 205, 225), "accessible": (80, 130, 255),
    "start": (60, 225, 125),
    "button": (50, 56, 70), "button_hover": (68, 77, 96), "button_on": (36, 108, 190),
    "info": (200, 210, 225), "ok": (95, 215, 135), "warn": (245, 180, 70), "error": (240, 95, 85),
    "ai": (88, 166, 255), "baseline": (240, 160, 80),
}
ROOF = {REGULAR: (125, 130, 142), EV: C["ev"], ACCESSIBLE: C["accessible"]}
STATUS_COLOR = {AVAILABLE: C["available"], RESERVED: C["reserved"], OCCUPIED: C["occupied"]}


def _font(size, bold=False):
    return pygame.font.SysFont("segoeui,arial,helvetica", size, bold=bold)


class Button:
    def __init__(self, rect, text, action, is_on=None):
        self.rect = pygame.Rect(rect)
        self.text = text          # str or function returning str
        self.action = action
        self.is_on = is_on        # optional function -> bool (highlight)

    def label(self):
        return self.text() if callable(self.text) else self.text


class UI:
    def __init__(self, sim):
        self.sim = sim
        self.f_title = _font(22, True)
        self.f_head = _font(13, True)
        self.f_body = _font(15)
        self.f_bold = _font(15, True)
        self.f_small = _font(13)
        self.f_tiny = _font(11, True)
        self.f_btn = _font(14, True)
        self.f_btn_small = _font(12, True)

        self.show_search = True
        self.overlay = None           # None / "help" / "bench_pending" / "bench"
        self.bench = None
        self._bench_frames = 0
        self.time = 0.0
        self.mouse = (0, 0)
        self._closed_info = {}        # cell -> SearchStep (for tooltips)
        self._text_cache = {}
        self._car_cache = {}
        lot = sim.lot
        self.lot_rect = pygame.Rect(LOT_X, LOT_Y, lot.cols * CELL, lot.rows * CELL)
        self.overlay_surf = pygame.Surface(self.lot_rect.size, pygame.SRCALPHA)
        self.hazard = self._make_hazard_tile()
        self.buttons = self._make_buttons()

    # ================================================================ input
    def _make_buttons(self):
        s = self.sim
        on_off = lambda flag: "ON" if flag else "OFF"
        specs = [
            # Row 1 - vehicles
            ("Add Car [1]", lambda: s.add_vehicle(REGULAR), None),
            ("Add EV [2]", lambda: s.add_vehicle(EV), None),
            ("Add Accessible [3]", lambda: s.add_vehicle(ACCESSIBLE), None),
            ("Allocate Next [Enter]", s.allocate_next, None),
            (lambda: f"Auto-Allocate: {on_off(s.auto_allocate)} [A]", s.toggle_auto,
             lambda: s.auto_allocate),
            (lambda: f"Random Arrivals: {on_off(s.random_arrivals)} [R]", s.toggle_random_arrivals,
             lambda: s.random_arrivals),
            # Row 2 - A* demonstration
            (lambda: f"Mode: {STRATEGY_SHORT[s.strategy]} [M]", s.toggle_strategy,
             lambda: s.strategy == AI),
            (lambda: f"Step Mode: {on_off(s.step_mode)} [S]", s.toggle_step_mode, lambda: s.step_mode),
            ("Next A* Step [Space]", s.next_step, None),
            (lambda: "Resume [P]" if s.paused else "Pause [P]", s.toggle_pause, lambda: s.paused),
            (lambda: f"Speed: {s.speed:g}x [F]", s.cycle_speed, None),
            (lambda: f"Show Explored: {on_off(self.show_search)} [V]", self.toggle_search_view,
             lambda: self.show_search),
            # Row 3 - environment & tools
            ("Release Spot [D]", s.release_selected_or_random, None),
            ("Random Obstacles [O]", s.add_random_obstacles, None),
            ("Clear Blocks [C]", s.clear_blocks, None),
            ("Benchmark [B]", self.start_benchmark, None),
            ("Help [H]", self.toggle_help, None),
            ("Reset [X]", s.reset, None),
        ]
        buttons = []
        w, h, gap = 137, 36, 8
        for i, (text, action, is_on) in enumerate(specs):
            row, col = divmod(i, 6)
            rect = (LOT_X + col * (w + gap), 536 + row * (h + 6), w, h)
            buttons.append(Button(rect, text, action, is_on))
        return buttons

    def toggle_search_view(self):
        self.show_search = not self.show_search

    def toggle_help(self):
        self.overlay = None if self.overlay == "help" else "help"

    def start_benchmark(self):
        self.overlay = "bench_pending"
        self._bench_frames = 2        # draw a "running..." frame first

    def handle_event(self, event, pos):
        """Returns "quit" when the application should close."""
        s = self.sim
        if event.type == pygame.KEYDOWN:
            k = event.key
            if k == pygame.K_ESCAPE:
                if self.overlay:
                    self.overlay = None
                    return None
                return "quit"
            if k == pygame.K_q:
                return "quit"
            if self.overlay and k not in (pygame.K_h, pygame.K_b):
                self.overlay = None
                return None
            actions = {
                pygame.K_1: lambda: s.add_vehicle(REGULAR), pygame.K_KP1: lambda: s.add_vehicle(REGULAR),
                pygame.K_2: lambda: s.add_vehicle(EV), pygame.K_KP2: lambda: s.add_vehicle(EV),
                pygame.K_3: lambda: s.add_vehicle(ACCESSIBLE), pygame.K_KP3: lambda: s.add_vehicle(ACCESSIBLE),
                pygame.K_RETURN: s.allocate_next, pygame.K_KP_ENTER: s.allocate_next,
                pygame.K_a: s.toggle_auto, pygame.K_r: s.toggle_random_arrivals,
                pygame.K_m: s.toggle_strategy, pygame.K_s: s.toggle_step_mode,
                pygame.K_SPACE: s.next_step, pygame.K_n: s.next_step,
                pygame.K_p: s.toggle_pause, pygame.K_f: s.cycle_speed,
                pygame.K_EQUALS: lambda: s.change_speed(1), pygame.K_PLUS: lambda: s.change_speed(1),
                pygame.K_KP_PLUS: lambda: s.change_speed(1), pygame.K_MINUS: lambda: s.change_speed(-1),
                pygame.K_KP_MINUS: lambda: s.change_speed(-1),
                pygame.K_v: self.toggle_search_view, pygame.K_d: s.release_selected_or_random,
                pygame.K_o: s.add_random_obstacles, pygame.K_c: s.clear_blocks,
                pygame.K_b: self.start_benchmark, pygame.K_h: self.toggle_help, pygame.K_x: s.reset,
            }
            if k in actions:
                actions[k]()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
            self._on_click(pos, event.button)
        return None

    def _on_click(self, pos, button):
        s = self.sim
        if self.overlay:
            if self.overlay != "bench_pending":
                self.overlay = None
            return
        if button == 1:
            for b in self.buttons:
                if b.rect.collidepoint(pos):
                    b.action()
                    return
        cell = self._cell_at(pos)
        if cell is None:
            return
        lot = s.lot
        kind = lot.grid[cell]
        if kind == SPOT:
            spot = lot.spot_at[cell]
            if button == 3:
                s.release_spot(spot)
            else:
                s.spot_clicked(spot)
        elif button == 1:
            if lot.is_blockable(cell):
                s.toggle_block(cell)
            elif kind == OBSTACLE:
                s.say(f"{cell} is a static pillar - it cannot be removed.", "warn")
            elif kind == ENTRANCE:
                s.say("Entrance: every arriving vehicle starts its A* search here.")
            elif kind == EXIT:
                s.say("Exit: leaving cars drive here along an A* route.")

    def update(self, dt, mouse):
        self.time += dt
        self.mouse = mouse
        if self.overlay == "bench_pending":
            self._bench_frames -= 1
            if self._bench_frames <= 0:
                self.bench = benchmark.run_benchmark(blocked=tuple(sorted(self.sim.lot.blocked)))
                self.overlay = "bench"
                self.sim.say("Benchmark finished: both strategies ran on identical scenarios.", "ok")

    # ============================================================ helpers
    def _cell_rect(self, cell):
        return pygame.Rect(LOT_X + cell[1] * CELL, LOT_Y + cell[0] * CELL, CELL, CELL)

    def _local_rect(self, cell):
        return pygame.Rect(cell[1] * CELL, cell[0] * CELL, CELL, CELL)

    def _center(self, cell):
        return (LOT_X + cell[1] * CELL + CELL // 2, LOT_Y + cell[0] * CELL + CELL // 2)

    def _cell_at(self, pos):
        if not self.lot_rect.collidepoint(pos):
            return None
        return ((pos[1] - LOT_Y) // CELL, (pos[0] - LOT_X) // CELL)

    def text(self, surf, txt, font, color, pos, anchor="topleft"):
        key = (txt, id(font), color)
        img = self._text_cache.get(key)
        if img is None:
            if len(self._text_cache) > 4000:
                self._text_cache.clear()
            img = font.render(txt, True, color)
            self._text_cache[key] = img
        rect = img.get_rect(**{anchor: pos})
        surf.blit(img, rect)
        return rect

    def wrap(self, txt, font, width):
        lines, cur = [], ""
        for word in txt.split():
            test = word if not cur else cur + " " + word
            if font.size(test)[0] <= width:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def pill(self, surf, txt, font, fg, bg, pos, anchor="center", pad=(6, 2)):
        img_w, img_h = font.size(txt)
        rect = pygame.Rect(0, 0, img_w + pad[0] * 2, img_h + pad[1] * 2)
        setattr(rect, anchor, pos)
        pygame.draw.rect(surf, bg, rect, border_radius=rect.h // 2)
        self.text(surf, txt, font, fg, rect.center, "center")
        return rect

    def _make_hazard_tile(self):
        tile = pygame.Surface((CELL, CELL))
        tile.fill(C["obstacle"])
        for x in range(-CELL, CELL * 2, 12):
            pygame.draw.line(tile, (40, 30, 20), (x, CELL), (x + CELL, 0), 4)
        pygame.draw.rect(tile, (120, 60, 15), tile.get_rect(), 2)
        return tile

    def _car_sprite(self, vtype, heading):
        key = (vtype, int(round(heading)) % 360)
        sprite = self._car_cache.get(key)
        if sprite is None:
            base_key = (vtype, "base")
            base = self._car_cache.get(base_key)
            if base is None:
                w, h = 32, 18
                base = pygame.Surface((w, h), pygame.SRCALPHA)
                pygame.draw.rect(base, C["car"], (0, 0, w, h), border_radius=6)
                pygame.draw.rect(base, ROOF[vtype], (8, 3, 14, h - 6), border_radius=3)
                pygame.draw.rect(base, (40, 48, 62), (22, 3, 5, h - 6), border_radius=2)   # windscreen
                pygame.draw.rect(base, (40, 48, 62), (4, 4, 3, h - 8), border_radius=1)    # rear window
                pygame.draw.rect(base, (255, 232, 120), (w - 3, 2, 3, 4))                  # headlights
                pygame.draw.rect(base, (255, 232, 120), (w - 3, h - 6, 3, 4))
                pygame.draw.rect(base, (220, 60, 60), (0, 2, 2, 4))                        # tail lights
                pygame.draw.rect(base, (220, 60, 60), (0, h - 6, 2, 4))
                pygame.draw.rect(base, (25, 25, 30), (0, 0, w, h), 1, border_radius=6)
                self._car_cache[base_key] = base
            sprite = pygame.transform.rotate(base, key[1])
            self._car_cache[key] = sprite
        return sprite

    # ============================================================== draw
    def draw(self, surf):
        surf.fill(C["bg"])
        self._draw_header(surf)
        self._draw_lot(surf)
        self._draw_legend(surf)
        self._draw_buttons(surf)
        self._draw_message(surf)
        self._draw_panel(surf)
        if self.overlay is None:
            self._draw_tooltip(surf)
        elif self.overlay == "help":
            self._draw_help(surf)
        elif self.overlay == "bench_pending":
            box = self._overlay_box(surf, 520, 140, "Running benchmark...")
            self.text(surf, "AI and baseline are allocating the same vehicles on identical lots.",
                      self.f_body, C["text"], (box.centerx, box.y + 70), "center")
        elif self.overlay == "bench":
            self._draw_benchmark(surf)

    # ------------------------------------------------------------ header
    def _phase_info(self):
        s = self.sim
        if s.paused:
            return "PAUSED", C["muted"]
        if s.phase == SEARCHING:
            if s.step_mode:
                return "A* STEP MODE - press SPACE", C["warn"]
            return "A* SEARCHING...", C["explored"]
        if s.phase == SEARCH_DONE:
            return "A* COMPLETE - path found", C["ok"]
        if s.phase == MOVING:
            return "DRIVING ALONG A* PATH", C["path"]
        if s.leaving:
            return "VEHICLE LEAVING", C["path"]
        if s.display_alloc is not None:
            return "A* COMPLETE - idle", C["ok"]
        return "IDLE - add a vehicle", C["muted"]

    def _draw_header(self, surf):
        self.text(surf, "Smart Parking Space Allocation  |  A* Pathfinding Simulator",
                  self.f_title, C["text"], (16, 14))
        label, color = self._phase_info()
        r = self.pill(surf, label, self.f_bold, C["dark"], color, (LOGICAL_W - 16, 29), "midright", (12, 4))
        strat = self.sim.strategy
        self.pill(surf, f"Strategy: {STRATEGY_SHORT[strat]}", self.f_bold, C["dark"], C[strat],
                  (r.left - 10, 29), "midright", (12, 4))

    # --------------------------------------------------------------- lot
    def _draw_lot(self, surf):
        s = self.sim
        lot = s.lot
        frame = self.lot_rect.inflate(12, 12)
        pygame.draw.rect(surf, C["panel"], frame, border_radius=10)
        for cell, kind in lot.grid.items():
            self._draw_cell(surf, cell, kind)
        self._draw_search(surf)
        self._draw_vehicles(surf)
        self._draw_spot_labels(surf)
        hover = self._cell_at(self.mouse)
        if hover is not None and self.overlay is None and lot.grid[hover] != WALL:
            pygame.draw.rect(surf, (255, 255, 255), self._cell_rect(hover), 1)

    def _draw_cell(self, surf, cell, kind):
        lot = self.sim.lot
        rect = self._cell_rect(cell)
        if kind == WALL:
            pygame.draw.rect(surf, C["grass"] if (cell[0] + cell[1]) % 2 else C["grass2"], rect)
            return
        if kind == SPOT:
            spot = lot.spot_at[cell]
            pygame.draw.rect(surf, C["spot_base"], rect)
            inner = rect.inflate(-6, -6)
            pygame.draw.rect(surf, STATUS_COLOR[spot.status], inner, border_radius=6)
            if spot.type == EV:
                pygame.draw.rect(surf, C["ev"], inner, 3, border_radius=6)
            elif spot.type == ACCESSIBLE:
                pygame.draw.rect(surf, C["accessible"], inner, 3, border_radius=6)
            else:
                pygame.draw.rect(surf, (235, 235, 235), inner, 1, border_radius=6)
            return
        # Road-like cells
        pygame.draw.rect(surf, C["road"], rect)
        pygame.draw.rect(surf, C["road_line"], rect, 1)
        if kind == OBSTACLE:
            pillar = rect.inflate(-16, -16)
            pygame.draw.rect(surf, C["obstacle"], pillar, border_radius=5)
            pygame.draw.rect(surf, (120, 60, 15), pillar, 2, border_radius=5)
            pygame.draw.line(surf, (120, 60, 15), pillar.topleft, pillar.bottomright, 2)
            pygame.draw.line(surf, (120, 60, 15), pillar.topright, pillar.bottomleft, 2)
        elif cell in lot.blocked:
            surf.blit(self.hazard, rect)
        elif kind in (ENTRANCE, EXIT):
            color = C["start"] if kind == ENTRANCE else C["error"]
            pygame.draw.rect(surf, color, rect.inflate(-4, -4), 2, border_radius=6)
            cx, cy = rect.center
            pygame.draw.polygon(surf, color, [(cx + 6, cy + 6), (cx + 6, cy + 18), (cx + 14, cy + 12)])
            self.text(surf, "IN" if kind == ENTRANCE else "OUT", self.f_tiny, color, (cx, cy - 6), "center")

    def _draw_search(self, surf):
        s = self.sim
        alloc = s.display_alloc
        self._closed_info = {}
        if alloc is None or alloc.search is None:
            return
        lot = s.lot
        steps = alloc.search.steps
        k = s.visible_steps()
        complete = k >= len(steps)

        closed, frontier = {}, {}
        for st in steps[:k]:
            closed[st.node] = st
            for node, g, h in st.added:
                frontier[node] = (g, h)
        for node in closed:
            frontier.pop(node, None)
        self._closed_info = closed

        if self.show_search:
            ov = self.overlay_surf
            ov.fill((0, 0, 0, 0))
            for node in closed:
                if lot.grid[node] != SPOT:
                    pygame.draw.rect(ov, (*C["explored"], 115), self._local_rect(node).inflate(-4, -4),
                                     border_radius=5)
            for node in frontier:
                if lot.grid[node] != SPOT:
                    pygame.draw.rect(ov, (*C["frontier"], 235), self._local_rect(node).inflate(-6, -6),
                                     2, border_radius=5)
            surf.blit(ov, self.lot_rect.topleft)
            if s.step_mode:   # show f = g + h on every node in step mode
                for node, st in closed.items():
                    if lot.grid[node] != SPOT:
                        self.text(surf, f"f{st.f}", self.f_tiny, C["dark"],
                                  self._cell_rect(node).move(0, -2).midbottom, "midbottom")
                for node, (g, h) in frontier.items():
                    if lot.grid[node] != SPOT:
                        self.text(surf, f"f{g + h}", self.f_tiny, C["frontier"],
                                  self._cell_rect(node).move(0, -2).midbottom, "midbottom")

        if complete:
            points = [self._center(c) for c in alloc.search.path]
            if len(points) > 1:
                pygame.draw.lines(surf, C["path"], False, points, 6)
            for p in points:
                pygame.draw.circle(surf, (210, 230, 255), p, 3)
        elif k > 0:
            pygame.draw.rect(surf, (255, 255, 255), self._cell_rect(steps[k - 1].node).inflate(-2, -2),
                             3, border_radius=5)

        pygame.draw.circle(surf, C["start"], self._center(alloc.start), 20, 3)
        if s.active is not None and s.active.allocation is alloc:
            pulse = 3 + 3 * (1 + math.sin(self.time * 6)) / 2
            pygame.draw.rect(surf, (255, 255, 255), self._cell_rect(alloc.spot.cell).inflate(pulse, pulse),
                             3, border_radius=8)

    def _draw_vehicles(self, surf):
        s = self.sim
        for v in s.vehicles.values():
            if v.state in (PARKED, ALLOCATING, DRIVING, LEAVING):
                center = (LOT_X + (v.x + 0.5) * CELL, LOT_Y + (v.y + 0.5) * CELL)
                sprite = self._car_sprite(v.type, v.heading)
                surf.blit(sprite, sprite.get_rect(center=center))
                if v.state != PARKED:
                    self.pill(surf, v.id, self.f_tiny, C["dark"], C["car"], (center[0], center[1] - 20))
                if v.id == s.selected_id:
                    pygame.draw.circle(surf, C["ai"], (int(center[0]), int(center[1])), 22, 2)
        # Waiting queue, drawn on the grass below the entrance
        lot = s.lot
        for i, v in enumerate(s.queue):
            cell = (lot.entrance[0] + 1 + i, lot.entrance[1])
            if cell[0] >= lot.rows:
                break
            center = self._center(cell)
            sprite = self._car_sprite(v.type, 90)
            surf.blit(sprite, sprite.get_rect(center=center))
            self.pill(surf, v.id, self.f_tiny, C["dark"], C["warn"], (center[0], center[1] + 14))
        if s.queue:
            self.text(surf, "QUEUE", self.f_tiny, C["warn"],
                      self._cell_rect((lot.entrance[0] + 1, 0)).move(0, -1).midtop, "midtop")

    def _draw_spot_labels(self, surf):
        s = self.sim
        alloc = s.display_alloc
        show_scores = alloc is not None and s.active is not None and s.active.allocation is alloc
        for spot in s.lot.spots:
            inner = self._cell_rect(spot.cell).inflate(-6, -6)
            self.pill(surf, spot.id, self.f_tiny, C["text"], C["dark"], (inner.x + 1, inner.y + 1),
                      "topleft", (3, 0))
            if spot.type == EV:
                self.pill(surf, "EV", self.f_tiny, C["dark"], C["ev"], (inner.x + 1, inner.bottom - 1),
                          "bottomleft", (3, 0))
            elif spot.type == ACCESSIBLE:
                self.pill(surf, "A", self.f_tiny, C["text"], C["accessible"], (inner.x + 1, inner.bottom - 1),
                          "bottomleft", (4, 0))
            if show_scores and spot.id in alloc.scores:
                value = alloc.scores[spot.id]
                if alloc.score_kind == "route":
                    txt = "--" if value is None else str(value)
                else:
                    txt = f"m{value}"
                chosen = spot is alloc.spot
                self.pill(surf, txt, self.f_tiny, C["dark"], C["explored"] if chosen else C["frontier"],
                          (inner.right - 1, inner.bottom - 1), "bottomright", (3, 0))

    def _draw_legend(self, surf):
        items = [
            ("Road", C["road"], "fill"), ("Available", C["available"], "fill"),
            ("Reserved", C["reserved"], "fill"), ("Occupied", C["occupied"], "fill"),
            ("Explored by A*", C["explored"], "fill"), ("Open set (frontier)", C["frontier"], "outline"),
            ("Final A* path", C["path"], "line"), ("Pillar / blocked road", C["obstacle"], "fill"),
            ("Vehicle", C["car"], "fill"), ("EV charging spot", C["ev"], "outline"),
            ("Accessible spot", C["accessible"], "outline"), ("Start (entrance)", C["start"], "ring"),
        ]
        col_w = 144
        for i, (label, color, style) in enumerate(items):
            row, col = divmod(i, 6)
            x = LOT_X + col * col_w
            y = 503 + row * 16
            box = pygame.Rect(x, y + 2, 12, 12)
            if style == "fill":
                pygame.draw.rect(surf, color, box, border_radius=3)
            elif style == "outline":
                pygame.draw.rect(surf, color, box, 2, border_radius=3)
            elif style == "line":
                pygame.draw.line(surf, color, (x, y + 8), (x + 12, y + 8), 4)
            else:
                pygame.draw.circle(surf, color, box.center, 6, 2)
            self.text(surf, label, self.f_small, C["muted"], (x + 17, y))

    def _draw_buttons(self, surf):
        for b in self.buttons:
            hover = b.rect.collidepoint(self.mouse) and self.overlay is None
            on = b.is_on() if b.is_on else False
            color = C["button_on"] if on else C["button"]
            if hover:
                color = tuple(min(255, c + 22) for c in color)
            pygame.draw.rect(surf, color, b.rect, border_radius=8)
            pygame.draw.rect(surf, C["panel_edge"], b.rect, 1, border_radius=8)
            label = b.label()
            font = self.f_btn if self.f_btn.size(label)[0] <= b.rect.w - 10 else self.f_btn_small
            self.text(surf, label, font, C["text"], b.rect.center, "center")

    def _draw_message(self, surf):
        s = self.sim
        rect = pygame.Rect(LOT_X, 664, self.lot_rect.w, 30)
        pygame.draw.rect(surf, C["panel"], rect, border_radius=8)
        color = C.get(s.message_level, C["info"])
        pygame.draw.rect(surf, color, (rect.x, rect.y, 5, rect.h), border_top_left_radius=8,
                         border_bottom_left_radius=8)
        msg = s.message
        while self.f_body.size(msg)[0] > rect.w - 24 and len(msg) > 4:
            msg = msg[:-4] + "..."
        self.text(surf, msg, self.f_body, color, (rect.x + 14, rect.centery), "midleft")
        self.text(surf, "Mouse: left-click road = block/unblock  |  left-click spot = select car  |  "
                        "right-click parked car = release  |  H = help",
                  self.f_small, C["muted"], (LOT_X, 698))

    # ------------------------------------------------------------- panel
    def _card(self, surf, y, h, title, title_color=None):
        rect = pygame.Rect(PANEL_X, y, PANEL_W, h)
        pygame.draw.rect(surf, C["panel"], rect, border_radius=10)
        pygame.draw.rect(surf, C["panel_edge"], rect, 1, border_radius=10)
        self.text(surf, title, self.f_head, title_color or C["muted"], (rect.x + 12, rect.y + 8))
        return rect

    def _row(self, surf, x, y, label, value, color=None, label_w=96):
        self.text(surf, label, self.f_small, C["muted"], (x, y + 1))
        self.text(surf, value, self.f_body, color or C["text"], (x + label_w, y - 1))

    def _draw_panel(self, surf):
        s = self.sim
        lot = s.lot

        # --- Status
        r = self._card(surf, 58, 112, "SIMULATION STATUS")
        x, y = r.x + 12, r.y + 30
        self._row(surf, x, y, "Strategy", STRATEGY_NAMES[s.strategy], C[s.strategy])
        queue = ", ".join(f"{v.id} {v.label}" for v in s.queue) or "empty"
        if self.f_body.size(queue)[0] > PANEL_W - 120:
            queue = f"{len(s.queue)} vehicles waiting"
        self._row(surf, x, y + 19, "Queue", queue)
        occ, res = lot.count(OCCUPIED), lot.count(RESERVED)
        total = len(lot.spots)
        self._row(surf, x, y + 38, "Occupancy", f"{occ} occupied, {res} reserved, "
                                                f"{total - occ - res} free / {total}")
        bar = pygame.Rect(x, y + 60, PANEL_W - 24, 8)
        pygame.draw.rect(surf, C["dark"], bar, border_radius=4)
        if occ:
            pygame.draw.rect(surf, C["occupied"], (bar.x, bar.y, bar.w * occ // total, bar.h), border_radius=4)
        if res:
            pygame.draw.rect(surf, C["reserved"], (bar.x + bar.w * occ // total, bar.y,
                                                   max(4, bar.w * res // total), bar.h))
        self.text(surf, f"Blocked roads: {len(lot.blocked)}   |   Speed {s.speed:g}x   |   "
                        f"Auto {'ON' if s.auto_allocate else 'OFF'}   |   Step {'ON' if s.step_mode else 'OFF'}",
                  self.f_small, C["muted"], (x, y + 70))

        # --- Vehicle details
        v = s.focus_vehicle()
        title = "VEHICLE DETAILS" if v is None else f"VEHICLE {v.id}  -  {v.label}"
        r = self._card(surf, 178, 168, title, C["text"] if v else None)
        x, y = r.x + 12, r.y + 30
        if v is None:
            self.text(surf, "No vehicle yet. Press 1, 2 or 3 to add one.", self.f_body, C["muted"], (x, y))
        else:
            a = v.allocation
            self._row(surf, x, y, "State", STATE_NAMES[v.state])
            if a is None:
                self._row(surf, x, y + 19, "Spot", f"{v.spot.id if v.spot else '-'} (pre-parked)")
            elif a.success:
                spot = a.spot
                self._row(surf, x, y + 19, "Assigned spot", f"{spot.id}  ({SPOT_TYPE_NAMES[spot.type]})",
                          C["ok"], 100)
                self._row(surf, x, y + 38, "Path length", f"{a.route_length} moves  |  "
                                                           f"{a.search.nodes_explored} nodes explored")
                self._row(surf, x, y + 57, "A* searches", f"{a.astar_calls} run, {a.nodes_explored} nodes in total")
                self._row(surf, x, y + 76, "Decision time", f"{a.allocation_ms:.2f} ms  (A*: {a.pathfinding_ms:.2f} ms)")
                self._row(surf, x, y + 95, "Strategy", STRATEGY_NAMES[a.strategy], C[a.strategy])
            else:
                self._row(surf, x, y + 19, "Result", "No reachable eligible spot", C["error"])
                self._row(surf, x, y + 38, "A* searches", f"{a.astar_calls} run, {a.nodes_explored} nodes")
            if v is s.active and s.phase == SEARCHING:
                steps = a.search.steps
                k = s.visible_steps()
                if k:
                    st = steps[k - 1]
                    line = f"Expanding {st.node}:  g={st.g} + h={st.h} = f={st.f}"
                else:
                    line = "Open set = {start}. Press SPACE to expand." if s.step_mode else "Starting search..."
                pygame.draw.rect(surf, C["dark"], (x - 4, y + 114, PANEL_W - 16, 22), border_radius=5)
                self.text(surf, f"Step {k}/{len(steps)}   {line}", self.f_small, C["explored"], (x, y + 117))

        # --- Why this spot
        r = self._card(surf, 354, 112, "WHY THIS SPOT?")
        if v is None:
            reason = "Each decision is explained here."
        elif v.allocation is None:
            reason = "This car was already parked when the simulation started."
        else:
            reason = v.allocation.reason
        lines = self.wrap(reason, self.f_small, PANEL_W - 24)
        for i, line in enumerate(lines[:5]):
            self.text(surf, line, self.f_small, C["text"], (r.x + 12, r.y + 28 + i * 16))

        # --- Live comparison
        r = self._card(surf, 474, 230, "LIVE COMPARISON  (this session)")
        x = r.x + 12
        col_ai, col_base = r.right - 112, r.right - 14
        y = r.y + 28
        highlight = col_ai if s.strategy == AI else col_base
        pygame.draw.rect(surf, (45, 52, 66), (highlight - 70, y - 2, 74, 184), border_radius=5)
        self.text(surf, "Metric", self.f_head, C["muted"], (x, y))
        self.text(surf, "AI", self.f_head, C["ai"], (col_ai, y), "topright")
        self.text(surf, "Baseline", self.f_head, C["baseline"], (col_base, y), "topright")
        rows = comparison_rows(s.metrics[AI], s.metrics[BASELINE])
        for i, (label, a_val, b_val) in enumerate(rows):
            yy = y + 20 + i * 20
            self.text(surf, label, self.f_small, C["text"], (x, yy))
            self.text(surf, a_val, self.f_bold, C["text"], (col_ai, yy - 1), "topright")
            self.text(surf, b_val, self.f_bold, C["text"], (col_base, yy - 1), "topright")
        self.text(surf, "M = switch strategy   |   B = fair benchmark (identical scenarios)",
                  self.f_tiny, C["muted"], (x, r.bottom - 18))

    # ------------------------------------------------------------- tooltip
    def _draw_tooltip(self, surf):
        cell = self._cell_at(self.mouse)
        if cell is None:
            return
        lot = self.sim.lot
        kind = lot.grid[cell]
        if kind == SPOT:
            spot = lot.spot_at[cell]
            txt = f"{spot.id} | {SPOT_TYPE_NAMES[spot.type]} | {spot.status}"
            if spot.vehicle_id:
                txt += f" by {spot.vehicle_id}"
        elif cell in lot.blocked:
            txt = f"Blocked road {cell} - click to unblock"
        elif kind == ROAD:
            txt = f"Road {cell} - click to block"
        elif kind == OBSTACLE:
            txt = f"Pillar {cell} (static obstacle)"
        elif kind == ENTRANCE:
            txt = "Entrance - every A* search starts here"
        elif kind == EXIT:
            txt = "Exit"
        else:
            return
        st = self._closed_info.get(cell)
        if st is not None:
            txt += f"  |  A*: g={st.g}  h={st.h}  f={st.f}"
        w, h = self.f_small.size(txt)
        rect = pygame.Rect(self.mouse[0] + 14, self.mouse[1] + 16, w + 14, h + 8)
        if rect.right > LOGICAL_W - 4:
            rect.right = self.mouse[0] - 6
        pygame.draw.rect(surf, C["dark"], rect, border_radius=6)
        pygame.draw.rect(surf, C["panel_edge"], rect, 1, border_radius=6)
        self.text(surf, txt, self.f_small, C["text"], (rect.x + 7, rect.y + 4))

    # ------------------------------------------------------------ overlays
    def _overlay_box(self, surf, w, h, title):
        shade = pygame.Surface((LOGICAL_W, LOGICAL_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 175))
        surf.blit(shade, (0, 0))
        rect = pygame.Rect(0, 0, w, h)
        rect.center = (LOGICAL_W // 2, LOGICAL_H // 2)
        pygame.draw.rect(surf, C["panel"], rect, border_radius=12)
        pygame.draw.rect(surf, C["ai"], rect, 2, border_radius=12)
        self.text(surf, title, self.f_title, C["text"], (rect.x + 20, rect.y + 14))
        return rect

    def _draw_help(self, surf):
        rect = self._overlay_box(surf, 860, 560, "Controls")
        rows = [
            ("1 / 2 / 3", "Add a regular car / EV / accessible vehicle at the entrance"),
            ("Enter", "Allocate the next waiting vehicle (needed when Auto-Allocate is OFF)"),
            ("A", "Auto-allocate ON / OFF"),
            ("R", "Random arrivals and departures ON / OFF"),
            ("M", "Strategy: AI (lowest A* route cost)  <->  Baseline (nearest by Manhattan)"),
            ("S", "Step mode: A* expands ONE node per SPACE press"),
            ("Space / N", "Next A* step (or start driving once the search is complete)"),
            ("P", "Pause / resume all animation"),
            ("F,  + / -", "Change speed (0.5x, 1x, 2x, 4x)"),
            ("V", "Show / hide explored nodes and open set"),
            ("D", "Release the selected parked car (or a random one)"),
            ("O  /  C", "Add 3 random road blocks  /  clear all road blocks"),
            ("B", "Run the fair benchmark: AI vs baseline on identical scenarios"),
            ("X", "Reset the simulation"),
            ("Esc / Q", "Close this window / quit"),
            ("Left-click road", "Block / unblock it (moving cars are re-routed by A*)"),
            ("Left-click spot", "Select the car parked there (details in side panel)"),
            ("Right-click car", "Release it: the spot frees up and the car drives to the exit"),
            ("Hover a cell", "Shows g, h and f for nodes A* has explored"),
        ]
        y = rect.y + 58
        for key, desc in rows:
            self.text(surf, key, self.f_bold, C["ai"], (rect.x + 24, y))
            self.text(surf, desc, self.f_body, C["text"], (rect.x + 190, y))
            y += 24
        self.text(surf, "Click anywhere or press Esc to close", self.f_small, C["muted"],
                  (rect.centerx, rect.bottom - 14), "center")

    def _draw_benchmark(self, surf):
        bench = self.bench
        res = bench["results"]
        rect = self._overlay_box(surf, 960, 560, "Benchmark: AI vs Baseline on identical scenarios")
        sub = (f"Same layout ({bench['blocked']} blocked road cells), same pre-parked cars, same arrivals "
               f"and departures.  Seeds {bench['seeds'][0]}-{bench['seeds'][-1]}, {bench['events']} "
               f"events each, {bench['arrivals']} arrivals in total.")
        for i, line in enumerate(self.wrap(sub, self.f_small, rect.w - 40)):
            self.text(surf, line, self.f_small, C["muted"], (rect.x + 20, rect.y + 50 + i * 16))

        # Table
        x, y = rect.x + 24, rect.y + 96
        col_ai, col_base = x + 330, x + 430
        self.text(surf, "Metric", self.f_head, C["muted"], (x, y))
        self.text(surf, "AI", self.f_head, C["ai"], (col_ai, y), "topright")
        self.text(surf, "Baseline", self.f_head, C["baseline"], (col_base, y), "topright")
        for i, (label, a_val, b_val) in enumerate(comparison_rows(res[AI], res[BASELINE])):
            yy = y + 24 + i * 26
            self.text(surf, label, self.f_body, C["text"], (x, yy))
            self.text(surf, a_val, self.f_bold, C["text"], (col_ai, yy), "topright")
            self.text(surf, b_val, self.f_bold, C["text"], (col_base, yy), "topright")

        # Bar charts
        charts = [
            ("Avg path length (cells)", lambda m: m.avg_path, "{:.2f}"),
            ("Failed allocations", lambda m: m.failed, "{}"),
            ("Avg nodes / A* search", lambda m: m.avg_nodes_per_search, "{:.1f}"),
            ("A* searches / vehicle", lambda m: m.searches_per_vehicle, "{:.1f}"),
        ]
        for i, (title, getter, fmt) in enumerate(charts):
            cx = rect.x + 500 + (i % 2) * 225
            cy = rect.y + 96 + (i // 2) * 170
            self.text(surf, title, self.f_head, C["muted"], (cx, cy))
            values = [getter(res[AI]), getter(res[BASELINE])]
            top = max(max(values), 1e-9)
            base_y = cy + 140
            for j, (val, key) in enumerate(zip(values, (AI, BASELINE))):
                h = int(105 * val / top)
                bar = pygame.Rect(cx + 20 + j * 90, base_y - h, 60, h)
                pygame.draw.rect(surf, C[key], bar, border_top_left_radius=4, border_top_right_radius=4)
                self.text(surf, fmt.format(val), self.f_bold, C["text"], (bar.centerx, bar.top - 3), "midbottom")
                self.text(surf, STRATEGY_SHORT[key], self.f_small, C["muted"], (bar.centerx, base_y + 3), "midtop")
            pygame.draw.line(surf, C["panel_edge"], (cx + 10, base_y), (cx + 200, base_y), 1)

        note = ("AI runs A* to every free eligible spot and takes the lowest real route cost; the baseline "
                "takes the nearest spot by straight-line distance and uses A* only to drive there. For one "
                "vehicle in the same lot state the AI route is never longer, but it costs more A* searches. "
                "Over a whole scenario the lots diverge, so the totals above are what was actually measured.")
        for i, line in enumerate(self.wrap(note, self.f_small, 450)):
            self.text(surf, line, self.f_small, C["muted"], (x, rect.y + 330 + i * 17))
        self.text(surf, "Press B to run again, click anywhere or Esc to close", self.f_small, C["muted"],
                  (rect.centerx, rect.bottom - 14), "center")
