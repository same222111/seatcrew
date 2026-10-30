"""PyInstaller entry point for the SeatCrew desktop app."""
import multiprocessing, sys
from seatcrew.desktop import main
if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
