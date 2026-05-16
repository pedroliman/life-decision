# Cash Flow & Net Worth Simulator: "Stay vs. Go" RV Decision
## Functional Specifications

---

## 1. Overview

An interactive financial simulator comparing two life paths over 10 years on a month-by-month basis:

- **Stay** — remain in the current house, continue paying mortgage, keep the CX-5 and Aliner
- **Go** — sell the house, trade in the CX-5, sell the Aliner, buy a Ram 3500 truck and a Brinkley Z 3610 fifth-wheel RV, and live full-time on the road

The simulator helps visualize exactly when and by how much the two paths diverge on cash flow, asset values, debt, and net worth.

---

## 2. Architecture

- **Single Python file** (`app.py`) using **Streamlit** for the UI
- **Pandas** for month-by-month time-series computation
- **Plotly** for interactive charts
- **No external API calls** — all inputs come from sidebar widgets
- Save/load scenarios as JSON

---

## 3. Input Parameters

All parameters are editable via the Streamlit sidebar. Defaults represent the user's actual situation.

### 3.1 Starting Position (both scenarios)

| Parameter | Default |
|---|---|
| Starting cash balance | $30,000 |
| Starting retirement balance | $60,000 |

### 3.2 Personal & Tax

| Parameter | Default |
|---|---|
| Gross annual income | $160,000 |
| Income annual growth rate | 3% |
| NC state income tax rate | 3.99% |
| FL state income tax rate | 0% |
| Domicile change date | 60 days after RV purchase |
| Federal effective tax rate | 18% |
| FICA rate | 7.65% |

### 3.3 Current House (Stay Scenario)

| Parameter | Default |
|---|---|
| Current home value | $400,000 |
| Mortgage balance | $342,000 |
| Mortgage interest rate | 5.0% |
| Months remaining | 174 (14.5 years) |
| Computed monthly P&I | ~$2,767/mo (proper amortization) |
| Property tax | $300/mo |
| Homeowner's insurance | $120/mo |
| Annual home appreciation | 2.0% |
| Annual maintenance (% of value) | 1.0% |
| Monthly utilities | $350 |
| Monthly groceries | $800 |
| Monthly auto fuel (CX-5) | $140 |

### 3.4 Current Car (CX-5)

| Parameter | Default |
|---|---|
| Loan balance | $20,000 |
| Monthly payment | $500 |
| Months remaining | 36 |
| Current value | $22,000 |
| Annual depreciation rate | 12% |
| Monthly insurance | $90 |
| Loan interest rate | 6.0% |

### 3.5 Aliner (Current Small Trailer)

| Parameter | Default |
|---|---|
| Current value | $8,000 |
| Loan | None |
| Annual depreciation rate | 5% |
| Sale date (Go only) | Same as RV purchase date |

**Stay scenario**: Aliner is kept as an asset, depreciated monthly, never sold.  
**Go scenario**: Aliner is sold on the sale date; proceeds added to cash; asset removed.

### 3.6 Sell Decision Inputs (Go Scenario)

| Parameter | Default |
|---|---|
| House sale date | 90 days from today |
| House sale price | Appreciated value at sale date (overrideable) |
| Selling costs | 7% of sale price |
| CX-5 trade-in date | Same as truck purchase date |
| CX-5 trade-in value | $20,000 |

If the CX-5 loan balance exceeds the trade-in value, negative equity rolls into the truck loan.

### 3.7 Truck (Ram 3500 — Go Only)

| Parameter | Default |
|---|---|
| Purchase date | 30 days from today |
| Purchase price | $72,000 |
| Down payment | $0 |
| Loan APR | 0% |
| Loan term | 36 months |
| Depreciation (years 1–5) | 5%/yr |
| Depreciation (years 6–10) | 7%/yr |
| Monthly insurance | $130 |
| Monthly fuel (while RVing) | $400 |
| Annual maintenance | $2,400 |

### 3.8 RV (Brinkley Z 3610 — Go Only)

| Parameter | Default |
|---|---|
| Purchase date | Truck purchase date + 14 days |
| Purchase price | $115,000 |
| Down payment | All available cash above emergency floor (or fixed amount) |
| Loan APR | 7.5% |
| Loan term | 180 months (15 years) |
| Depreciation (years 1–5) | 8%/yr |
| Depreciation (years 6–10) | 5%/yr |
| Monthly insurance | $200 (full-timer policy) |
| One-time setup costs | $6,000 (hitch, Starlink, supplies) |

### 3.9 RV Operating Costs (monthly, Go only, begins at RV purchase)

| Item | Default |
|---|---|
| Campground fees | $1,100 |
| Propane & non-campground utilities | $80 |
| Internet (Starlink + cellular) | $190 |
| RV maintenance reserve | $400 |
| Groceries | $800 |
| Domicile mail service | $25 |
| Emergency repair reserve buildup | $250/mo until $15,000 reached, then $0 |

### 3.10 Retirement Account (both scenarios)

| Parameter | Default |
|---|---|
| Starting balance | $60,000 (from Starting Position) |
| Employee contribution | 10% of gross |
| Employer match | 4% of gross |
| Annual investment return | 8% |
| Account type | Traditional 401(k) or Roth 401(k) |
| IRS employee limit (2025/2026) | $23,500 |
| IRS combined limit | $70,000 |

**Traditional 401(k)**: Employee contributions reduce federal and state taxable income.  
**Roth 401(k)**: Contributions are post-tax; no reduction to taxable income.  
IRS annual limits reset each January 1.

### 3.11 Investment Assumptions

| Parameter | Default |
|---|---|
| Cash savings APY | 4% |
| Taxable investment return (excess above floor) | 7% |
| Emergency cash floor | $25,000 |
| Annual inflation rate | 3% |

---

## 4. Calculation Logic

### 4.1 Starting Net Worth

Both scenarios begin with identical net worth:

```
Starting NW = Cash + Retirement + House Equity + CX-5 Equity + Aliner Value
            = $30K  + $60K       + ($400K−$342K) + ($22K−$20K) + $8K
            = $158,000
```

### 4.2 Amortization Formula

All four loans (mortgage, CX-5, truck, RV) use the standard fixed-payment formula:

```
Payment = P × r(1+r)^n / ((1+r)^n − 1)
```

where `P` = principal, `r` = APR/12 (monthly rate), `n` = remaining months.

Each month:
- Interest = Balance × r
- Principal = Payment − Interest (capped at remaining balance)
- New Balance = Balance − Principal

### 4.3 Inflation

Operating costs are inflated **monthly** at `annual_rate / 12`, compounded:

```
adjusted_cost = base_cost × (1 + inflation_rate / 12)^month
```

Loan payments are fixed; depreciation is not inflation-adjusted.

### 4.4 Depreciation

Geometric monthly decline:

```
new_value = value × (1 − annual_depreciation_rate / 12)
```

### 4.5 Investment Returns

Each month, after all cash flows:

- If `liquid > emergency_floor`:
  - Excess above floor earns `taxable_return / 12`
  - Floor portion earns `cash_apy / 12`
- Else: entire liquid balance earns `cash_apy / 12`

Retirement balance compounds at `(1 + annual_return / 12)` per month, then employee and employer contributions are added.

### 4.6 Stay Scenario — Monthly Steps

1. Compute gross monthly income (steps up annually by `income_growth_rate`)
2. Compute retirement contributions (IRS-capped); for Traditional, deduct from taxable income
3. Compute taxes: federal, state (NC throughout), FICA
4. Compute net take-home
5. Outflows: mortgage P&I, property tax, HOI, utilities, groceries, CX-5 fuel, CX-5 insurance, home maintenance, CX-5 loan payment
6. Update liquid: `liquid += net_income − total_outflows`
7. Apply investment return to liquid
8. Compound retirement balance; add contributions
9. Appreciate house value; depreciate CX-5 and Aliner; amortize mortgage and CX-5 loan
10. Compute net worth: `liquid + retirement + assets − liabilities`

### 4.7 Go Scenario — Life Events

Events fire at the **start** of the month matching their input date. Processing order within a month:

1. **Domicile change** → switch state tax rate from NC to FL
2. **Truck purchase** → deduct down payment from cash; compute truck loan; dispose CX-5 (trade value reduces truck financed amount; if underwater, negative equity rolls in)
3. **Aliner sale** → add depreciated value to cash; remove from assets
4. **House sale** → add (sale price × (1 − selling costs%) − mortgage balance) to cash; remove house and mortgage
5. **RV purchase** → deduct down payment and setup costs from cash; compute RV loan; begin RV operating costs; groceries shift from house bucket to RV bucket

After events, the same monthly income/tax/outflow/return logic applies as Stay, with costs reflecting current asset ownership.

### 4.8 Go Scenario — Monthly Outflows

| Cost category | Active when |
|---|---|
| Mortgage P&I | House not yet sold |
| Property tax, HOI, utilities, maintenance | House not yet sold |
| Groceries (house) | House not yet sold **and** RV not yet owned |
| CX-5 loan payment, insurance, fuel | CX-5 active (before truck purchase) |
| Truck loan payment | Truck owned, balance > 0 |
| Truck insurance, maintenance | Truck owned |
| Truck fuel | Truck owned **and** RV owned |
| RV loan payment | RV owned, balance > 0 |
| All RV operating costs (incl. groceries) | RV owned |

### 4.9 Net Worth Formula

```
Net Worth = Liquid Wealth + Retirement Balance + Non-Cash Assets − Liabilities
```

- **Liquid wealth** = cash + taxable investments (single pool; split at emergency floor for reporting)
- **Non-cash assets** = house, CX-5, truck, RV, Aliner (as applicable per scenario and date)
- **Liabilities** = outstanding loan balances (mortgage, CX-5, truck, RV)

---

## 5. Output

### 5.1 Summary KPI Cards

- Starting net worth (month 0, identical for both scenarios)
- Stay net worth at year 10
- Go net worth at year 10 (with delta vs Stay)
- Retirement balance at year 10
- Crossover month (if Go ever overtakes Stay) or who leads at year 10
- Cost of going (Stay − Go at year 10)
- Computed mortgage P&I and RV loan payment

### 5.2 Interactive Plotly Charts (5 tabs)

**Tab 1 — Net Worth**
- Two lines: Stay (blue) and Go (orange) over 120 months
- Red/green shaded fill between lines (red = Stay ahead, green = Go ahead)
- Gap (Go − Stay) on a right Y-axis
- Numbered event annotations (E1, E2, …) on the Go line

**Tab 2 — Liquid Wealth**
- Cash + taxable investments for both scenarios
- Horizontal emergency floor marker
- Event annotations

**Tab 3 — Monthly Cash Flow**
- Net income minus total outflows per month for each scenario
- Shows discontinuities clearly: Go goes sharply negative months 2–3 (dual house + RV costs), then jumps positive in month 4 (house costs stop)

**Tab 4 — Assets & Debt**
- Side-by-side subplots: Stay (left) and Go (right)
- Stacked areas above zero = asset components by type (house, CX-5, truck, RV, Aliner)
- Stacked areas below zero = loan balances by type
- House bar visibly collapses at house sale month in Go panel

**Tab 5 — Retirement**
- Single compound growth curve
- Milestone markers at $100K, $250K, $500K, $1M

### 5.3 Month-by-Month Comparison Table

One row per month for 120 months:

| Column | Description |
|---|---|
| Month | 1–120 |
| Date | Calendar month |
| Stay: Cash | Liquid cash (below emergency floor portion) |
| Stay: Assets | Non-cash, non-retirement assets |
| Stay: Retirement | Retirement balance |
| Stay: Debt | Total outstanding loans |
| Stay: Net Worth | Total net worth |
| Go: Cash | (same as above, Go scenario) |
| Go: Assets | |
| Go: Retirement | |
| Go: Debt | |
| Go: Net Worth | |
| Difference (Go−Stay) | Green if positive, red if negative |

- Filterable by simulation year
- Exportable to CSV

### 5.4 Life Event Log

Lists every Go scenario event with month, date, description, and net worth at the moment it fires.

### 5.5 Sensitivity Analysis

Four sidebar sliders that re-run the simulation live:
- House appreciation rate: 0–6%
- RV depreciation rate (years 1–5): 5–12%
- RV operating costs multiplier: 0.70×–1.30×
- Retirement annual return: 4–12%

### 5.6 Methodology Expander

Plain-English explanation of all formulas, assumptions, and simplifications at the bottom of the app.

---

## 6. Validation Checks

Before showing results, the app warns if:

- Month-1 net worth differs between Stay and Go by more than $5,000 (events should not fire in month 1 with default dates)
- Stay year-10 net worth falls below $600,000
- Year-10 retirement balance falls below $300,000

---

## 7. Scenario Save / Load

- **Save**: Download current key parameters as a JSON file
- **Load**: Upload a previously saved JSON; sidebar values update on next rerun
