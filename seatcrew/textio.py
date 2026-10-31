"""Windows code pages (cp1252/cp437/cp936...) cannot encode every character SeatCrew prints (Chinese titles, ·, →).
Call utf8_stdio() first thing in every entry point: stdout/stderr become UTF-8 and never raise on an odd character."""
import sys

def utf8_stdio():
    for s in (sys.stdout, sys.stderr):
        try:
            if s is not None and hasattr(s, "reconfigure") and (getattr(s, "encoding", "") or "").lower().replace("-", "") != "utf8":
                s.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError): pass
