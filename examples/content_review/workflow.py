"""Example 2: content review pipeline (Python-defined workflow).

    topic -> DRAFT -> FACTCHECK -> POLICY -> APPROVE (human) -> PUBLISH -> REVIEW

* Works with no API key: every seat has rules (template drafter, claim/source checks, banned-phrase policy).
* Assign an AI to any seat in Settings: DRAFT then writes the draft; FACTCHECK/POLICY/REVIEW can only add blocks.
* APPROVE is a human gate: the item waits on the dashboard until someone clicks Approve / Reject.
* PUBLISH writes Markdown to state/content_review/published/<id>.md; REVIEW re-reads it and un-publishes on failure.
Run:  seatcrew ui content_review    |    seatcrew run content_review --yes"""
import re
from pathlib import Path
from seatcrew import Seat, HumanSeat, Chief, Workflow, llm
from seatcrew.config import Config, base_defaults

SEATS = ["chief", "draft", "factcheck", "policy", "approve", "publish", "review"]
PROMPTS = {
    "chief": "You are CHIEF of a small editorial team. Given today's topics, answer proceed or hold.",
    "draft": "You are DRAFT, a concise writer. Write a ~150-word blog post in Markdown on the topic using ONLY the notes and sources given. No invented facts or numbers.",
    "factcheck": "You are FACTCHECK. Does the draft make claims not supported by the notes/sources? Answer supported or unsupported.",
    "policy": "You are POLICY, a compliance reviewer. Does the draft contain medical/financial promises, hate, personal data or legal risk? Answer ok or violation.",
    "approve": "Human approval gate.",
    "publish": "You are PUBLISH.",
    "review": "You are REVIEW. Compare the published text with the approved draft. Answer ok or flag.",
}
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
def words(text):
    """Word count that also works for Chinese/Japanese/Korean (each CJK character counts as one word)."""
    return len(_CJK.findall(text or "")) + len(_CJK.sub(" ", text or "").split())

SETTINGS = {"banned_phrases": ["guaranteed", "risk-free", "miracle", "100% safe", "cure"], "min_words": 30, "max_words": 600,
            "approve_auto_approve": False, "load_samples": True}
SAMPLES = [
    dict(topic="Why we test in staging", notes="Staging mirrors production config. Most of our incidents last year were config mistakes caught late.", sources="internal postmortems 2025"),
    dict(topic="Our new pricing", notes="The Pro plan is now $12/month. This plan is guaranteed to double your revenue.", sources="pricing page"),
    dict(topic="Benchmark results", notes="Our app is now 3x faster than every competitor.", sources=""),
    dict(topic="Team offsite recap", notes="We met in Lisbon, planned the Q3 roadmap and shipped two prototypes.", sources="offsite notes"),
]

class Draft(Seat):
    name = "draft"; job = "writes the draft"; kind = "producer"
    def rules(self, it):
        d = it["data"]
        if not d.get("topic", "").strip(): return False, "no topic"
        out = llm.write(self.name, f"Topic: {d['topic']}\nNotes: {d.get('notes', '')}\nSources: {d.get('sources', '')}", self.cfg)
        if out:
            d["draft"], who = out; self.wf.log(self.name, "AI", f"[{who}] drafted {words(d['draft'])} words", it["subject"]); return True, f"AI draft by {who}"
        d["draft"] = f"# {d['topic']}\n\n{d.get('notes', '').strip()}\n\n" + (f"_Sources: {d['sources']}_\n" if d.get("sources") else "") + \
                     "\nThis post was drafted from the team's notes and is reviewed by a human before publishing. Questions and corrections are welcome."
        return True, f"template draft ({words(d['draft'])} words)"

class FactCheck(Seat):
    name = "factcheck"; job = "checks claims"; labels = ("supported", "unsupported"); block_labels = ("unsupported",)
    def rules(self, it):
        d = it["data"]; nums = re.findall(r"\d[\d,.]*%?|\$\d+", d.get("draft", ""))
        if nums and not d.get("sources", "").strip(): return False, f"{len(nums)} number(s) ({', '.join(nums[:3])}) but no source given"
        return True, f"{len(nums)} numeric claim(s), sources: {d.get('sources') or 'none needed'}"

class Policy(Seat):
    name = "policy"; job = "compliance"; labels = ("ok", "violation"); block_labels = ("violation",)
    def rules(self, it):
        s = self.cfg["settings"]; text = it["data"].get("draft", ""); w = words(text)
        hit = [p for p in s["banned_phrases"] if p.lower() in text.lower()]
        if hit: return False, f"banned phrase: {', '.join(hit)}"
        if w < s["min_words"]: return False, f"too short ({w} < {s['min_words']} words)"
        if w > s["max_words"]: return False, f"too long ({w} > {s['max_words']} words)"
        if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+|\b\d{3}[- ]?\d{3}[- ]?\d{4}\b", text): return False, "contains an email address or phone number"
        return True, f"no banned phrases, {w} words"

class Approve(HumanSeat):
    name = "approve"; job = "human sign-off"

class Publish(Seat):
    name = "publish"; job = "publishes"; kind = "producer"
    def rules(self, it):
        f = self.wf.state_dir / "published" / f"{it['id']}.md"; f.parent.mkdir(exist_ok=True)
        f.write_text(it["data"]["draft"], encoding="utf-8"); it["data"]["published_path"] = str(f); return True, f"published to {f.name}"

class Review(Seat):
    name = "review"; job = "post-publish check"; labels = ("ok", "flag"); block_labels = ("flag",)
    def check(self, it):
        ok, why = super().check(it)
        if not ok:   # failed review un-publishes (the equivalent of reverting a fill)
            Path(it["data"].get("published_path", "/nonexistent")).unlink(missing_ok=True); why += " -> unpublished"
        return ok, why
    def rules(self, it):
        f = Path(it["data"].get("published_path", ""))
        if not f.is_file(): return False, "published file missing"
        if f.read_text(encoding="utf-8") != it["data"]["draft"]: return False, "published text differs from the approved draft"
        return True, "published text matches the approved draft"

class ContentReview(Workflow):
    name = "content_review"; title = "Content review"
    locale_dirs = (Path(__file__).parent / "locales",)
    submit_fields = [dict(name="topic", label="Topic"), dict(name="notes", label="Notes / facts", type="textarea"), dict(name="sources", label="Sources")]
    def __init__(self, cfg, state_dir):
        super().__init__(cfg, state_dir)
        self.setup([Chief(self), Draft(self), FactCheck(self), Policy(self), Approve(self), Publish(self), Review(self)])
        if not self.items and cfg["settings"]["load_samples"]:
            for s in SAMPLES: self.inbox.append(self.new_item(s["topic"], s, "post"))
    def submit(self, title=None, data=None, subject="post"):
        data = dict(data or {}); return super().submit(title or data.get("topic", "post"), data, subject)

def build(config_path, state_dir):
    return ContentReview(Config(config_path, base_defaults(SEATS, PROMPTS, SETTINGS)), state_dir)
