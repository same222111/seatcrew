"""Find and build a workflow by name or path.

A workflow is either
  * a folder with workflow.yaml (no code), or
  * a folder / file workflow.py that defines  build(config_path, state_dir) -> seatcrew.Workflow.
Names are looked up in ./<name>/, ./workflows/<name>/ and the bundled examples (trading, content_review, support_triage)."""
import importlib.util
from pathlib import Path

def examples_dir():
    try:
        import seatcrew_examples; return Path(next(iter(seatcrew_examples.__path__)))
    except ImportError: return Path(__file__).resolve().parent.parent / "examples"

def find(name):
    p = Path(name)
    cands = [p] if p.suffix in (".py", ".yaml", ".yml") else [d / f for d in (p, Path("workflows") / name, examples_dir() / name) for f in ("workflow.yaml", "workflow.yml", "workflow.py")]
    for c in cands:
        if c.is_file(): return c
    raise FileNotFoundError(f"workflow '{name}' not found (looked for {', '.join(map(str, cands))})")

def list_examples():
    d = examples_dir(); return sorted(x.name for x in d.iterdir() if x.is_dir() and any((x / f).exists() for f in ("workflow.yaml", "workflow.py")))

def build(name, config_path=None, state_dir=None):
    f = find(name); stem = f.parent.name if f.name.startswith("workflow") else f.stem
    config_path = config_path or f"config.{stem}.yaml"; state_dir = state_dir or f"state/{stem}"
    if f.suffix in (".yaml", ".yml"):
        from .yamlflow import build as yb; return yb(f, config_path, state_dir)
    spec = importlib.util.spec_from_file_location(f"seatcrew_wf_{stem}", f); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.build(config_path, state_dir)
