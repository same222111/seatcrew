"""Flagship example: TradeCrew (paper trading) as a SeatCrew workflow.

    seatcrew ui trading        # generic SeatCrew dashboard rendering the trading workflow
    tradecrew start            # the full TradeCrew terminal (portfolios, Strategy Lab, wizard...)
Both drive the same Crew class (tradecrew/seats.py), which subclasses seatcrew.Workflow."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))   # when run from a source checkout
from tradecrew.config import Config
from tradecrew.seats import Crew

def build(config_path, state_dir):
    return Crew(Config(config_path), state_dir)
