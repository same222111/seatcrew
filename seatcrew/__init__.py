"""SeatCrew - a framework for multi-AI "seat" workflows.

Every job gets a seat. Every item walks an ordered check chain of seats; each seat answers CHECK OK or CHECK BLOCKED
with a reason, and the first block stops the item ("an idea is not a trigger"). Each seat can be driven by plain
rules or by any LLM you assign to it, and AI can only make a decision more cautious.

Trading (examples/trading, the TradeCrew app) is the flagship showcase; content review and support triage show the
same engine on other domains. Start with ARCHITECTURE.md and AGENTS.md."""
__version__ = "0.7.1"
from .core import Seat, HumanSeat, Chief, Workflow, Runner  # noqa: E402,F401
