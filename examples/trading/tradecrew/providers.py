"""TradeCrew uses the framework's LLM layer unchanged (this module IS seatcrew.llm, so monkeypatching works)."""
import sys
from seatcrew import llm as _llm
sys.modules[__name__] = _llm
