# Contributing to JARVIS

Thanks for helping build JARVIS. Bug reports, fixes, new tools, docs and design work are all welcome.

## Getting set up

JARVIS runs on macOS (Apple Silicon recommended) with Python 3.11+ and Node.js 18+.

```bash
git clone https://github.com/bertrandmbanwi/Jarvis.git
cd Jarvis
./setup.sh                      # Python venv, dependencies, Ollama models
cp .env.example .env            # add OPENAI_API_KEY (or run fully local with Ollama)
./start.sh full                 # server + UI + voice + overlay
```

You don't need a paid API key to work on most of the codebase: the test suite mocks every model call, and JARVIS falls back to Ollama locally.

## Before you open a pull request

Run the same checks CI runs:

```bash
source .venv/bin/activate
python -m ruff check .
python -m mypy jarvis
python -m pytest tests -q
python scripts/check_tool_contracts.py
python scripts/run_evals.py --offline
python -m bandit -q -r jarvis

cd jarvis/ui/jarvis-ui && npm ci && npm run lint && npm run build
```

Guidelines:

- **Keep changes focused.** One fix or feature per PR, with a test that fails before your change and passes after it.
- **Match the surrounding code.** Same naming, comment density and structure as the file you're editing.
- **New tools** need a schema in `jarvis/agent/tools_schema.py`, an entry in `TOOL_REGISTRY`, and a permission classification in `jarvis/core/permissions.py`. `scripts/check_tool_contracts.py` enforces this.
- **Anything that acts on the user's behalf** (sends, deletes, runs commands, spends money) must be marked `requires_confirmation` so it goes through the approval prompt.
- **Commit messages** use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `perf:`, `ci:`.

## Where to start

Issues labelled [`good first issue`](https://github.com/bertrandmbanwi/Jarvis/labels/good%20first%20issue) are scoped for newcomers. [`docs/ROADMAP.md`](docs/ROADMAP.md) lists the bigger pieces of work in progress. If you want to take something large, open an issue or discussion first so we can agree on the approach.

## Reporting security issues

Please don't open public issues for vulnerabilities. See [SECURITY.md](SECURITY.md).

## Code of conduct

Participation in this project is covered by the [Code of Conduct](CODE_OF_CONDUCT.md).
