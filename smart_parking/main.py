"""
main.py - Start the Smart Parking Space Allocation & A* Pathfinding Simulator.

Run:  python main.py
"""

import sys

import pygame

from simulation import Simulation
from ui import UI, LOGICAL_W, LOGICAL_H


def main():
    pygame.init()
    pygame.display.set_caption("Smart Parking Space Allocation - A* Pathfinding Simulator")

    # Fit the 1280x720 design onto smaller laptop screens by scaling it down.
    info = pygame.display.Info()
    scale = min(1.0, info.current_w * 0.96 / LOGICAL_W, info.current_h * 0.88 / LOGICAL_H)
    window = pygame.display.set_mode((int(LOGICAL_W * scale), int(LOGICAL_H * scale)))
    canvas = window if scale == 1.0 else pygame.Surface((LOGICAL_W, LOGICAL_H))

    def to_logical(pos):
        return (int(pos[0] / scale), int(pos[1] / scale))

    sim = Simulation()
    ui = UI(sim)
    clock = pygame.time.Clock()

    running = True
    while running:
        dt = min(clock.tick(60) / 1000.0, 0.1)   # seconds since last frame (capped)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break
            pos = to_logical(event.pos) if hasattr(event, "pos") else None
            if ui.handle_event(event, pos) == "quit":
                running = False

        sim.update(dt)
        ui.update(dt, to_logical(pygame.mouse.get_pos()))
        ui.draw(canvas)
        if canvas is not window:
            pygame.transform.smoothscale(canvas, window.get_size(), window)
        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
