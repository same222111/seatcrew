# Make it yours: SeatCrew as a template

SeatCrew is meant to be **forked and reshaped by your own AI**. The engine (seats, check chain, human gate, Runner, dashboard, multi-LLM, i18n) stays the same, and you describe your own jobs. Trading ([examples/trading](examples/trading/README.md)) is just the most complete example.

## How
1. Clone the repo and open it in Cursor, Claude Code, Codex CLI, Copilot or Windsurf, or upload a zip to ChatGPT or Claude.
2. Paste the **starter prompt**, then one task prompt below (edit the parts in `<>`).
3. Run `pytest -q` and `seatcrew ui <your workflow>`.

## Copy-paste prompts
**Starter (always paste this first):**
```text
You are working on SeatCrew, a framework for multi-AI "seat" workflows. Read AGENTS.md and ARCHITECTURE.md first and
follow the hard rules: every action goes through the check chain, AI may only make things more cautious, rules-only
must work without keys, no keys in files, all UI strings in locales, keep pytest green and offline.
Make small, well-commented changes, add tests, run `pytest -q`, and summarize what you changed.
```

**Build my own workflow (no code):**
```text
Create a YAML workflow with `seatcrew new <name>` for: <describe the process, e.g. "approve team expense requests:
check amount and receipt, block anything over $500 without a manager, flag weekend purchases, human approval, then a
final review">. One seat per job, rules first, optional `ai:` labels where judgement helps, a human seat before any
irreversible step, 3 realistic sample_items (at least one that should be blocked). Show me `seatcrew run <path> --yes`.
```

**Build it in Python (with real side effects):**
```text
Create a Python workflow (`seatcrew new <name> --python`) that <e.g. pulls new GitHub issues from a repo, LABEL seat
classifies them, DUPLICATE seat blocks likely duplicates, a human APPROVE seat, then a POST seat that adds the label via
the API (token from env), and a REVIEW seat that re-reads the issue and removes the label if it didn't stick>.
Override collect() for the input. Mock all HTTP in tests.
```

**Add a seat to an existing workflow:**
```text
In <workflow>, add a seat "<NAME>" between <A> and <B> that blocks when <rule>. Give it AI labels <ok|flag> with
<flag> blocking. Add seat_<name> to every locale file of that workflow and a test that proves it blocks and that nothing
after it runs.
```

**Use my favorite AI / model:**
```text
Make <OpenRouter / Groq / Mistral / ...> a first-class provider in seatcrew/llm.py PROVIDERS (OpenAI-compatible if
possible), default model <model>, key env <ENV_NAME>, add it to .env.example, and add a mocked test.
```

**Change the dashboard look:**
```text
Restyle seatcrew/web/index.html to <a light theme / compact mobile layout>. Keep it a single file with no build step,
keep every data-i18n attribute and T('...') call, and don't change the API.
```

**Add a language:**
```text
Add <language> (<code>): copy seatcrew/locales/en.json (and each example's locales/en.json) to <code>.json, translate
every value keeping {placeholders}, register it in seatcrew/config.py LANGUAGES, and run pytest.
```

**Customize the trading example:**
```text
Read examples/trading/AGENTS.md. <Add a strategy / a seat that blocks buys near earnings / a new data source>.
Paper trading only. Add tests in examples/trading/tests.
```

**Explain before changing:**
```text
Read AGENTS.md, ARCHITECTURE.md and seatcrew/core.py and explain with a diagram how one item flows from submit() to
"done", where a human approval happens, and where I would plug in <my idea>. Don't change code yet.
```
