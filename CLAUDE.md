# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run / develop

```bash
uv sync                           # install streamlit, pandas, plotly
uv run streamlit run app.py       # opens http://localhost:8501
```

Deps are declared in `pyproject.toml` (managed by `uv`). `requirements.txt` is kept as a pip-friendly mirror — keep them in sync if you change one.

There are no tests, no linter config, and no build step. `main.py` is leftover scaffolding and is not part of the app — `app.py` is the entry point.

## Architecture

Single-file app (`app.py`, ~1450 lines) organized in four sections:

1. **Financial math helpers** (`monthly_payment`, `amortize_month`, `depreciate_monthly`, `date_to_month_index`) — pure functions used by both simulators.
2. **`simulate_stay(p)`** — 120-month loop returning a DataFrame with `Stay_*` columns.
3. **`simulate_go(p)`** — 120-month loop returning `Go_*` columns; handles five life events (truck purchase, Aliner sale, house sale, RV purchase, domicile change) at the start of the matching month before that month's cash flows.
4. **`main()`** — Streamlit sidebar collects every parameter into a single `p` dict, runs both simulators, then renders KPI cards, 5 Plotly tabs (Net Worth, Liquid Wealth, Monthly Cash Flow, Assets & Debt, Retirement), an event log, a month-by-month table, and sensitivity sliders.

Both simulators share the same `p: dict` schema. Adding a parameter means: (a) adding the sidebar widget in `main()`, (b) inserting it into `p`, (c) reading `p["..."]` inside whichever simulator(s) consume it, and (d) extending the save/load JSON whitelist if it should be persisted.

## Conventions and gotchas specific to this repo

- **Monthly rates everywhere.** All annual rates (interest, depreciation, appreciation, inflation, returns) are converted to monthly inside the loop as `annual / 12`. Don't pre-divide in the sidebar.
- **Inflation compounds monthly.** Operating costs use `base * (1 + inflation/12)**m`, not `(1 + inflation)**years`. Loan payments and depreciation are NOT inflation-adjusted.
- **Event ordering matters.** In `simulate_go`, events fire in this order within a month: domicile change, truck purchase (with CX-5 trade-in and possible negative-equity rollover into truck loan), Aliner sale, house sale, RV purchase. After events run, that month's income/tax/outflow logic uses the post-event asset state. Reordering can double-count groceries (house bucket vs RV bucket) or miss a cost transition.
- **Liquid wealth is one pool.** Cash and taxable investments are tracked as a single `liquid` variable; the split at `emergency_cash_floor` is reporting-only. The investment-return logic (taxable rate above floor, `cash_apy` below) runs against this pool each month.
- **IRS limits reset Jan 1**, not at month 12 of the simulation. The loop tracks `current_year` and zeros `ytd_employee` / `ytd_combined` at year boundaries.
- **Traditional vs Roth 401(k)** changes whether employee contributions reduce taxable income (`is_traditional=True`) or are deducted post-tax from take-home. Don't conflate.
- See `SPECIFICATIONS.md` for the full functional spec, including expected default-scenario outputs used as sanity checks. `simulate_*` outputs should match the README's "Default scenario results" table when run with defaults.
