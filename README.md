# Stay vs. Go — RV Decision Simulator

A 10-year, month-by-month financial simulator that compares staying in your current house against selling everything and living full-time in an RV. Built with Python, Streamlit, Pandas, and Plotly.

## What it does

Enter your actual numbers in the sidebar and the app simulates both life paths simultaneously, showing exactly when cash flow, assets, debt, and net worth diverge. The default scenario models:

- **Stay**: keep the house ($400K value, $342K mortgage at 5%), CX-5, and Aliner
- **Go**: sell the house, trade in the CX-5, sell the Aliner, buy a Ram 3500 ($72K) and a Brinkley Z 3610 fifth-wheel ($115K), domicile in Florida (0% state income tax)

## Quick start

```bash
pip install streamlit pandas plotly
streamlit run app.py
```

The app opens in your browser at `http://localhost:8501`.

## Default scenario results

With all defaults loaded:

| Metric | Value |
|---|---|
| Starting net worth (both) | $158,000 |
| Stay net worth at year 10 | ~$1.89M |
| Go net worth at year 10 | ~$1.62M |
| Cost of going (10-yr) | ~$272K |
| Retirement balance at year 10 | ~$517K |
| RV loan payment | ~$904/mo |
| Mortgage P&I | ~$2,767/mo |

## Charts (5 tabs)

| Tab | What you see |
|---|---|
| Net Worth | Stay vs Go lines with red/green fill, event annotations, gap on right axis |
| Liquid Wealth | Cash + investments for each path with emergency floor marker |
| Monthly Cash Flow | Income minus outflows per month — the clearest view of the house-sale discontinuity |
| Assets & Debt | Side-by-side stacked areas: asset types above zero, loan balances below |
| Retirement | Compound growth curve with $100K/$250K/$500K/$1M milestones |

## Key financial logic

- **Proper amortization** for all four loans (mortgage, CX-5, truck, RV): `P × r(1+r)^n / ((1+r)^n − 1)`
- **Inflation** applied monthly (compounded at `annual_rate/12`) to all operating costs
- **IRS contribution limits** enforced annually; Traditional/Roth 401(k) toggle
- **Geometric depreciation** for all vehicles (`value × (1 − rate/12)` per month)
- **Event sequencing**: life events (truck purchase, Aliner sale, house sale, RV purchase, domicile change) fire in chronological order at the start of the month they occur, before that month's cash flows run
- **Groceries** correctly shift from the house bucket to the RV bucket the moment you own the RV (no double-counting)
- **CX-5 negative equity** rolls into the truck loan if the trade-in value is less than the remaining balance

## Inputs (all editable in the sidebar)

- Starting cash and retirement balance
- Income, tax rates (federal, NC, FL), FICA
- Mortgage parameters (balance, rate, remaining term)
- House appreciation, maintenance %, utilities
- CX-5 loan, value, depreciation, insurance
- Aliner value, depreciation, sale date
- Truck and RV purchase prices, loan terms, APRs, depreciation schedules
- All RV operating costs (campground, propane, internet, maintenance, etc.)
- Domicile change date
- Retirement contribution rates, employer match, return assumption
- Emergency cash floor, taxable investment return, savings APY, inflation

## Sensitivity analysis

Four sidebar sliders re-run the full simulation instantly:
- House appreciation rate (0–6%)
- RV depreciation rate years 1–5 (5–12%)
- RV operating costs multiplier (±30%)
- Retirement return (4–12%)

## Scenario management

Use the **Save Scenario** button to download your parameters as JSON. Use **Load Scenario** to restore them in a future session.

## Files

```
app.py              # Single-file Streamlit application (all simulation + UI)
requirements.txt    # Python dependencies
SPECIFICATIONS.md   # Full functional specification with formulas and logic
README.md           # This file
```

## Requirements

```
streamlit>=1.35.0
pandas>=2.0.0
plotly>=5.18.0
```

Python 3.9+ recommended.
