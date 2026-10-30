"""Build a workflow from YAML only - no Python needed. See examples/support_triage/workflow.yaml.

Each seat has a list of rules (run in order; the first failing rule blocks) and optionally `ai:` labels.
Rule types:
  require:        [field, ...]                          block if any field is empty
  max_len:        {field, max}                          block if longer
  min_len:        {field, min}                          block if shorter
  block_if_match: {field, pattern, reason}              block if regex matches (case-insensitive)
  require_match:  {field, pattern, reason}              block unless regex matches
  classify:       {field, into, keywords: {label: [words]}, default}   sets data[into]
  template:       {into, text}  or  {into, by, templates: {value: text}}  sets data[into] (str.format with item data)
  set:            {field: value, ...}                   sets fields
Seat options: name, job, human: true (approval gate), kind, ai: {labels, block, prompt}."""
import re
from pathlib import Path
import yaml
from .config import Config, base_defaults
from .core import Seat, HumanSeat, Chief, Workflow

class _Fmt(dict):
    def __missing__(self, k): return "{" + k + "}"

class RuleSeat(Seat):
    def __init__(self, wf, spec):
        ai = spec.get("ai") or {}
        super().__init__(wf, spec["name"], spec.get("job", ""), ai.get("labels", ()), ai.get("block", ()))
        self.spec = spec; self.kind = spec.get("kind", "check")

    def rules(self, item):
        d = item.setdefault("data", {}); notes = []
        for r in self.spec.get("rules") or []:
            (op, a), = r.items()
            if op == "require":
                miss = [f for f in a if not str(d.get(f, "")).strip()]
                if miss: return False, f"missing: {', '.join(miss)}"
            elif op == "max_len" and len(str(d.get(a["field"], ""))) > a["max"]: return False, f"{a['field']} longer than {a['max']} chars"
            elif op == "min_len" and len(str(d.get(a["field"], ""))) < a["min"]: return False, f"{a['field']} shorter than {a['min']} chars"
            elif op == "block_if_match" and re.search(a["pattern"], str(d.get(a["field"], "")), re.I): return False, a.get("reason", f"{a['field']} matches {a['pattern']}")
            elif op == "require_match" and not re.search(a["pattern"], str(d.get(a["field"], "")), re.I): return False, a.get("reason", f"{a['field']} must match {a['pattern']}")
            elif op == "classify":
                txt = str(d.get(a["field"], "")).lower()
                d[a["into"]] = next((lab for lab, ws in a["keywords"].items() if any(w.lower() in txt for w in ws)), a.get("default", "other"))
                notes.append(f"{a['into']}={d[a['into']]}")
            elif op == "template":
                text = a["templates"].get(str(d.get(a["by"])), a["templates"].get("default", "")) if "by" in a else a["text"]
                d[a["into"]] = text.format_map(_Fmt(d)); notes.append(f"{a['into']} written ({len(d[a['into']])} chars)")
            elif op == "set": d.update(a); notes.append("set " + ", ".join(a))
        return True, "; ".join(notes) or self.spec.get("ok", "rules passed")

    def ai_prompt(self, item):
        p = (self.spec.get("ai") or {}).get("prompt")
        return (p.format_map(_Fmt(item.get("data", {}))) if p else super().ai_prompt(item))

class YamlHuman(HumanSeat):
    def __init__(self, wf, spec): super().__init__(wf, spec["name"], spec.get("job", "human approval"))

class YamlWorkflow(Workflow):
    def __init__(self, spec, cfg, state_dir, base_dir=None):
        self.spec = spec; self.name = spec["name"]; self.title = spec.get("title", spec["name"])
        self.submit_fields = spec.get("submit", []); self.locale_dirs = (Path(base_dir) / "locales",) if base_dir else ()
        super().__init__(cfg, state_dir)
        seats = [Chief(self)] + [YamlHuman(self, s) if s.get("human") else RuleSeat(self, s) for s in spec["seats"] if s["name"] != "chief"]
        self.setup(seats, spec.get("chain"))
        if not self.items and spec.get("sample_items") and cfg.data.get("settings", {}).get("load_samples", True):
            for s in spec["sample_items"]: self.inbox.append(self.new_item(self.item_title(s), s, s.get(spec.get("subject_field", ""), "-")))

    def item_title(self, data):
        f = self.spec.get("title_field") or (self.submit_fields[0]["name"] if self.submit_fields else None)
        return str(data.get(f, "item"))[:80] if f else "item"

    def submit(self, title=None, data=None, subject="-"):
        data = dict(data or {}); return super().submit(title or self.item_title(data), data, data.get(self.spec.get("subject_field", ""), subject))

def load_spec(path): return yaml.safe_load(Path(path).read_text(encoding="utf-8"))

def build(path, config_path, state_dir):
    spec = load_spec(path); seats = ["chief"] + [s["name"] for s in spec["seats"] if s["name"] != "chief"]
    prompts = {s["name"]: (s.get("ai") or {}).get("system", f"You are the {s['name'].upper()} seat: {s.get('job', '')}.") for s in spec["seats"]}
    prompts.setdefault("chief", f"You are CHIEF, the commander of the '{spec['name']}' workflow. Answer proceed or hold.")
    d = base_defaults(seats, prompts, spec.get("settings")); d["run_interval_sec"] = spec.get("interval", 300); d["auto_run"] = spec.get("auto_run", True)
    return YamlWorkflow(spec, Config(config_path, d), state_dir, Path(path).parent)
