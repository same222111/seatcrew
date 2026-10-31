"""PyInstaller entry point for the SeatCrew desktop app."""
import multiprocessing, sys
from seatcrew.desktop import main
if __name__ == "__main__":
    multiprocessing.freeze_support()
    import os
    for name in ("stdout", "stderr"):          # windowed build: no console, keep stray writes from crashing
        if getattr(sys, name) is None: setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    sys.exit(main())
