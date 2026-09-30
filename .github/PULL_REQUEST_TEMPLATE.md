## What does this change?

<!-- One or two sentences. Link the issue it fixes, e.g. "Fixes #123". -->

## How was it tested?

- [ ] `python -m pytest tests -q`
- [ ] `python -m ruff check .` and `python -m mypy jarvis`
- [ ] `npm run lint && npm run build` (if the UI changed)
- [ ] Tried it in the running app (describe below)

## Checklist

- [ ] New tools have a schema, a `TOOL_REGISTRY` entry and a permission classification
- [ ] Actions that send, delete, run commands or spend money require confirmation
- [ ] Docs updated if behavior or setup changed
