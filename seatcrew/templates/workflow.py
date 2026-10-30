"""{name}: a SeatCrew workflow defined in Python. Run:  seatcrew ui {path}

Each seat owns ONE job. rules(item) -> (ok, reason); give a seat `labels`/`block_labels` and assign it an AI in
Settings to let the AI add blocks (it can never un-block). See AGENTS.md for the rules your AI must follow."""
from seatcrew import Seat, HumanSeat, Chief, Workflow
from seatcrew.config import Config, base_defaults

SEATS = ["chief", "intake", "judge", "approve", "review"]
PROMPTS = {{"judge": "You are JUDGE. Answer approve or reject for this request."}}
SETTINGS = {{"max_chars": 2000, "approve_auto_approve": False}}

class Intake(Seat):
    name = "intake"; job = "checks the request is complete"
    def rules(self, it):
        text = it["data"].get("request", "")
        if not text.strip(): return False, "empty request"
        if len(text) > self.cfg["settings"]["max_chars"]: return False, "request too long"
        return True, f"{{len(text)}} chars"

class Judge(Seat):
    name = "judge"; job = "an idea is not a trigger"; labels = ("approve", "reject"); block_labels = ("reject",)

class Approve(HumanSeat):
    name = "approve"; job = "human sign-off"

class Review(Seat):
    name = "review"; job = "final replay"

class {cls}(Workflow):
    name = "{name}"; title = "{title}"
    submit_fields = [dict(name="request", label="Request", type="textarea")]
    def __init__(self, cfg, state_dir):
        super().__init__(cfg, state_dir)
        self.setup([Chief(self), Intake(self), Judge(self), Approve(self), Review(self)])
    # def collect(self): ...   # pull items from an API / folder / feed instead of the dashboard form

def build(config_path, state_dir):
    return {cls}(Config(config_path, base_defaults(SEATS, PROMPTS, SETTINGS)), state_dir)
