# Macro Quant Lab · notes for Claude

Personal, public research repo of a rates/multi-asset portfolio manager who codes as a citizen developer. Optimise for clear, well-tested Python he can read and explain in an interview.

## Hard rules
- Public data only. Never add, infer or ask about anything internal to his employer: clients, positions, systems, colleagues, or the employer's name.
- Every new text file must pass `python -m mql.compliance`. Never weaken the compliance gate or its config to make a commit pass.
- No API keys in code. Optional keys come from environment variables (`GEMINI_API_KEY`).
- Anything an LLM writes about markets must pass `narrative.check_grounding` (no number that is not in the data table).
- The model portfolio is paper only. Decisions are rows in `data/portfolio/decisions.csv`, never back-dated.
- Never publish a tuned backtest as a track record.

## Layout
- `config/` watchlist (`series.yaml`), decoder lexicon, portfolio policy, compliance rules
- `mql/` package; each module has a docstring explaining its job
- `scripts/run_daily.py` the daily pipeline; `--publish` writes `docs/` and the README brief
- `data/` committed CSV history and JSON outputs (generated; don't hand-edit `history/`)
- `docs/` MkDocs site; generated pages: `index.md`, `monitor.md`, `brief/`, `decoder/`, `portfolio/factsheet-*`
- `tests/` unittest, no network; synthetic data helpers in `tests/helpers.py`

## Commands
- Tests: `python -m unittest discover -s tests -t .`
- Offline rebuild: `python scripts/run_daily.py --offline --publish`
- Compliance: `python -m mql.compliance`
- Site preview: `mkdocs serve`

## Conventions
- Units: `pct` levels in %, changes in bp; `spread` in bp; `price` changes in %; `level` in points.
- Parsing is separate from downloading so it can be tested offline.
- One failing data source must never stop the daily run; record it in the quality report instead.
- Charts: one y-axis, at most three series, fixed colour order, legend plus end labels, source line.
