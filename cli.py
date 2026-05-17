#!/usr/bin/env python3
"""
Stay vs. Go — RV decision CLI.

Each subcommand answers one specific financial question.
All parameters have base-case defaults; pass flags to explore scenarios.

Examples
--------
  python cli.py summary
  python cli.py depreciation
  python cli.py cashflow --year 2
  python cli.py networth
  python cli.py breakeven
  python cli.py events

Override any assumption on any command:
  python cli.py summary --rv-price 95000 --gross-income 180000
  python cli.py depreciation --rv-dep-early 0.10
"""

from datetime import date, timedelta

import click
from rich.console import Console
from rich.table import Table
from rich import box
from rich.panel import Panel

from app import (
    simulate_stay,
    simulate_go,
    compute_starting_networth,
    depreciate_monthly,
    monthly_payment,
)

console = Console()


# ---------------------------------------------------------------------------
# Parameter builder — mirrors Streamlit defaults
# ---------------------------------------------------------------------------

def build_params(
    rv_price, truck_price, home_value, gross_income,
    rv_apr, truck_apr, cx5_value,
    rv_dep_early, rv_dep_late, truck_dep_early, truck_dep_late,
):
    today = date.today()
    return {
        "today": today,
        "starting_cash": 30_000.0,
        "starting_retirement": 60_000.0,
        "gross_annual_income": gross_income,
        "income_growth_rate": 0.03,
        "nc_state_rate": 0.0399,
        "fl_state_rate": 0.0,
        "federal_effective_rate": 0.18,
        "fica_rate": 0.0765,
        "home_value": home_value,
        "mortgage_balance": 342_000.0,
        "mortgage_rate": 0.05,
        "mortgage_months_remaining": 174,
        "property_tax_monthly": 300.0,
        "homeowners_insurance_monthly": 120.0,
        "home_appreciation_rate": 0.02,
        "home_maintenance_pct": 0.01,
        "home_utilities_monthly": 350.0,
        "groceries_monthly": 800.0,
        "cx5_fuel_monthly": 140.0,
        "cx5_balance": 20_000.0,
        "cx5_monthly_payment": 500.0,
        "cx5_months_remaining": 36,
        "cx5_value": cx5_value,
        "cx5_depreciation_rate": 0.12,
        "cx5_insurance_monthly": 90.0,
        "cx5_rate": 0.06,
        "aliner_value": 8_000.0,
        "aliner_depreciation_rate": 0.05,
        "aliner_sale_date": today + timedelta(days=44),
        "house_sale_date": today + timedelta(days=90),
        "house_sale_price": None,
        "house_sale_price_override": False,
        "house_selling_costs_pct": 0.07,
        "cx5_tradein_value": cx5_value,
        "truck_purchase_date": today + timedelta(days=30),
        "truck_purchase_price": truck_price,
        "truck_down_payment": 0.0,
        "truck_loan_apr": truck_apr,
        "truck_loan_months": 36,
        "truck_depreciation_rate_early": truck_dep_early,
        "truck_depreciation_rate_late": truck_dep_late,
        "truck_insurance_monthly": 130.0,
        "truck_fuel_monthly": 400.0,
        "truck_annual_maintenance": 2_400.0,
        "rv_purchase_date": today + timedelta(days=44),
        "rv_purchase_price": rv_price,
        "rv_down_payment": 0.0,
        "rv_use_all_available_cash": True,
        "rv_loan_apr": rv_apr,
        "rv_loan_months": 180,
        "rv_depreciation_rate_early": rv_dep_early,
        "rv_depreciation_rate_late": rv_dep_late,
        "rv_insurance_monthly": 200.0,
        "rv_setup_costs": 6_000.0,
        "campground_fees_monthly": 1_100.0,
        "propane_monthly": 80.0,
        "internet_monthly": 190.0,
        "rv_maintenance_monthly": 400.0,
        "domicile_mail_monthly": 25.0,
        "emergency_reserve_monthly": 250.0,
        "emergency_reserve_target": 15_000.0,
        "domicile_change_date": today + timedelta(days=104),
        "employee_contribution_pct": 0.10,
        "employer_match_pct": 0.04,
        "retirement_return": 0.08,
        "is_traditional": True,
        "irs_employee_limit": 23_500.0,
        "irs_combined_limit": 70_000.0,
        "cash_apy": 0.04,
        "taxable_return": 0.07,
        "emergency_cash_floor": 25_000.0,
        "inflation_rate": 0.03,
    }


# ---------------------------------------------------------------------------
# Shared options decorator
# ---------------------------------------------------------------------------

_SHARED_OPTIONS = [
    click.option("--rv-price",       default=88_000.0, type=float, show_default=True,
                 metavar="$",    help="RV purchase price"),
    click.option("--truck-price",    default=62_000.0, type=float, show_default=True,
                 metavar="$",    help="Truck (RAM 2500) purchase price"),
    click.option("--home-value",     default=400_000.0, type=float, show_default=True,
                 metavar="$",    help="Current home value"),
    click.option("--gross-income",   default=160_000.0, type=float, show_default=True,
                 metavar="$",    help="Gross annual income"),
    click.option("--rv-apr",         default=0.075, type=float, show_default=True,
                 metavar="RATE", help="RV loan APR (e.g. 0.075 = 7.5%)"),
    click.option("--truck-apr",      default=0.0,   type=float, show_default=True,
                 metavar="RATE", help="Truck loan APR"),
    click.option("--cx5-value",      default=20_000.0, type=float, show_default=True,
                 metavar="$",    help="CX-5 current market value"),
    click.option("--rv-dep-early",   default=0.08, type=float, show_default=True,
                 metavar="RATE", help="RV annual depreciation rate, yrs 1-5"),
    click.option("--rv-dep-late",    default=0.05, type=float, show_default=True,
                 metavar="RATE", help="RV annual depreciation rate, yrs 6-10"),
    click.option("--truck-dep-early", default=0.05, type=float, show_default=True,
                 metavar="RATE", help="Truck annual depreciation rate, yrs 1-5"),
    click.option("--truck-dep-late",  default=0.07, type=float, show_default=True,
                 metavar="RATE", help="Truck annual depreciation rate, yrs 6-10"),
]


def shared_options(func):
    for opt in reversed(_SHARED_OPTIONS):
        func = opt(func)
    return func


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def d(n: float) -> str:
    return f"${n:,.0f}"


def signed(n: float) -> str:
    if n >= 0:
        return f"[green]+${n:,.0f}[/green]"
    return f"[red]-${abs(n):,.0f}[/red]"


def pct(n: float) -> str:
    return f"{n*100:.1f}%"


def _header(title: str, params: dict) -> Panel:
    p = params
    return Panel.fit(
        f"[bold]{title}[/bold]\n"
        f"RV [cyan]{d(p['rv_purchase_price'])}[/cyan]  "
        f"Truck [cyan]{d(p['truck_purchase_price'])}[/cyan]  "
        f"Income [cyan]{d(p['gross_annual_income'])}/yr[/cyan]  "
        f"Home [cyan]{d(p['home_value'])}[/cyan]",
        border_style="blue",
    )


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """Stay vs. Go RV Decision — answer specific financial questions.

    \b
    Commands:
      summary      10-year net worth comparison
      depreciation Depreciation cost: truck + RV vs keeping the CX-5
      cashflow     Monthly surplus for a given year (income minus all outflows)
      costs        Line-item cost breakdown before and after house sale
      networth     Year-by-year net worth table
      breakeven    When (if ever) does Go catch up to Stay?
      events       Life events and their timing in the Go scenario

    All commands share the same parameter flags. Use --help on any command.
    """


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------

@cli.command()
@shared_options
def summary(**kw):
    """10-year net worth: Stay vs. Go — the big picture."""
    p = build_params(**kw)
    stay_df = simulate_stay(p)
    go_df, _ = simulate_go(p)

    snw = compute_starting_networth(p)
    s5,  s10 = stay_df["Stay_NetWorth"].iloc[59],  stay_df["Stay_NetWorth"].iloc[-1]
    g5,  g10 = go_df["Go_NetWorth"].iloc[59],      go_df["Go_NetWorth"].iloc[-1]
    sr10 = stay_df["Stay_Retirement"].iloc[-1]

    diffs = go_df["Go_NetWorth"].values - stay_df["Stay_NetWorth"].values
    crossover = next(
        (i + 1 for i in range(1, len(diffs)) if diffs[i-1] < 0 and diffs[i] >= 0),
        None,
    )

    mortgage_pmt = monthly_payment(
        p["mortgage_balance"], p["mortgage_rate"], p["mortgage_months_remaining"])
    rv_pmt = monthly_payment(
        p["rv_purchase_price"], p["rv_loan_apr"], p["rv_loan_months"])

    console.print(_header("Stay vs. Go — 10-Year Summary", p))

    # Net worth comparison
    t = Table(box=box.SIMPLE_HEAD, header_style="bold")
    t.add_column("",              style="dim",   min_width=26)
    t.add_column("Stay",          justify="right", min_width=13)
    t.add_column("Go",            justify="right", min_width=13)
    t.add_column("Go − Stay",     justify="right", min_width=14)

    t.add_row("Starting net worth", d(snw), d(snw), "—")
    t.add_row("Net worth @ Year 5",  d(s5),  d(g5),  signed(g5 - s5))
    t.add_row("Net worth @ Year 10", d(s10), d(g10), signed(g10 - s10))
    t.add_row("10-yr gain",
              signed(s10 - snw), signed(g10 - snw), "—")
    t.add_row("Retirement @ Year 10", d(sr10), d(sr10), "—")
    console.print(t)

    # Key metrics
    t2 = Table(box=box.SIMPLE_HEAD, show_header=False)
    t2.add_column("Metric", style="dim", min_width=34)
    t2.add_column("Value",  justify="right", min_width=18)

    cost = s10 - g10
    t2.add_row("Cost of going (Stay NW − Go NW @ yr 10)",
               f"[{'red' if cost > 0 else 'green'}]{d(cost)}[/]")
    if crossover:
        t2.add_row("Go overtakes Stay at month",
                   f"[green]Month {crossover} "
                   f"(~{crossover//12}y {crossover%12}m)[/green]")
    else:
        leader = "Stay" if s10 > g10 else "Go"
        t2.add_row("Crossover", f"[yellow]None — {leader} leads at yr 10[/yellow]")
    t2.add_row("Mortgage payment",   f"{d(mortgage_pmt)}/mo")
    t2.add_row("RV loan payment",    f"{d(rv_pmt)}/mo" if rv_pmt else "[dim]cash[/dim]")
    t2.add_row("RV + truck purchase", d(p["rv_purchase_price"] + p["truck_purchase_price"]))
    console.print(t2)


# ---------------------------------------------------------------------------
# depreciation
# ---------------------------------------------------------------------------

@cli.command()
@shared_options
def depreciation(**kw):
    """Depreciation cost of ownership: RAM 2500 + RV vs keeping the CX-5."""
    p = build_params(**kw)

    tv  = p["truck_purchase_price"]
    rv  = p["rv_purchase_price"]
    cx5 = p["cx5_value"]
    total_truck = total_rv = total_cx5 = 0.0
    rows = []

    for yr in range(1, 11):
        t_r  = p["truck_depreciation_rate_early"] if yr <= 5 else p["truck_depreciation_rate_late"]
        r_r  = p["rv_depreciation_rate_early"]    if yr <= 5 else p["rv_depreciation_rate_late"]

        tv_s, rv_s, cx5_s = tv, rv, cx5
        for _ in range(12):
            tv  = depreciate_monthly(tv,  t_r)
            rv  = depreciate_monthly(rv,  r_r)
            cx5 = depreciate_monthly(cx5, 0.12)

        td, rd, c5d = tv_s - tv, rv_s - rv, cx5_s - cx5
        prem = td - c5d
        incr = prem + rd
        total_truck += td;  total_rv += rd;  total_cx5 += c5d
        rows.append((yr, td, c5d, prem, rd, incr, incr / 12))

    truck_prem_10 = total_truck - total_cx5
    total_incr_10 = truck_prem_10 + total_rv

    console.print(_header("Depreciation — Cost of Ownership", p))

    t = Table(box=box.SIMPLE_HEAD, header_style="bold")
    t.add_column("Yr",           justify="right", min_width=3)
    t.add_column("Truck Dep",    justify="right", min_width=10)
    t.add_column("CX-5 Dep",     justify="right", min_width=10)
    t.add_column("Truck Prem",   justify="right", min_width=11)
    t.add_column("RV Dep",       justify="right", min_width=10)
    t.add_column("Total Incr",   justify="right", min_width=11)
    t.add_column("$/mo",         justify="right", min_width=8)

    for yr, td, c5d, prem, rd, incr, mo in rows:
        t.add_row(
            str(yr),
            d(td), d(c5d),
            f"[yellow]{d(prem)}[/yellow]",
            d(rd),
            f"[bold]{d(incr)}[/bold]",
            f"[bold]{d(mo)}[/bold]",
        )
    t.add_section()
    t.add_row(
        "TOTAL",
        d(total_truck), d(total_cx5),
        f"[yellow]{d(truck_prem_10)}[/yellow]",
        d(total_rv),
        f"[bold cyan]{d(total_incr_10)}[/bold cyan]",
        f"[bold cyan]{d(total_incr_10/120)}[/bold cyan]",
    )
    console.print(t)

    console.print(
        f"\nTruck upgrade adds [yellow]{d(truck_prem_10/120)}/mo[/yellow] over keeping the CX-5.  "
        f"RV adds [yellow]{d(total_rv/120)}/mo[/yellow].  "
        f"Total incremental: [bold cyan]{d(total_incr_10/120)}/mo[/bold cyan] avg over 10 yrs.\n"
        f"[dim]Rates — Truck {pct(p['truck_depreciation_rate_early'])}→"
        f"{pct(p['truck_depreciation_rate_late'])}/yr  "
        f"RV {pct(p['rv_depreciation_rate_early'])}→"
        f"{pct(p['rv_depreciation_rate_late'])}/yr  CX-5 12%/yr[/dim]"
    )


# ---------------------------------------------------------------------------
# cashflow
# ---------------------------------------------------------------------------

@cli.command()
@shared_options
@click.option("--year", default=1, type=int, show_default=True,
              help="Simulation year to display (1–10)")
def cashflow(year, **kw):
    """Monthly surplus (net income minus all outflows) — Stay vs. Go, for one year."""
    if not 1 <= year <= 10:
        raise click.BadParameter("must be between 1 and 10", param_hint="--year")

    p = build_params(**kw)
    stay_df = simulate_stay(p)
    go_df, _ = simulate_go(p)

    start_m = (year - 1) * 12
    end_m   = start_m + 12

    console.print(_header(f"Monthly Cash Flow Surplus — Year {year}", p))
    console.print("[dim]Surplus = net take-home income − all outflows (loans, housing, living costs)[/dim]\n")

    t = Table(box=box.SIMPLE_HEAD, header_style="bold")
    t.add_column("Mo",           justify="right", min_width=4)
    t.add_column("Date",         min_width=10)
    t.add_column("Stay Out",     justify="right", min_width=10)
    t.add_column("Stay Surplus", justify="right", min_width=13)
    t.add_column("Go Out",       justify="right", min_width=10)
    t.add_column("Go Surplus",   justify="right", min_width=11)
    t.add_column("Diff (Go−Stay)", justify="right", min_width=14)

    stay_total = go_total = 0.0
    for i in range(start_m, end_m):
        sr = stay_df.iloc[i]
        gr = go_df.iloc[i]
        s_surp = sr["Stay_NetIncome"] - sr["Stay_TotalOutflow"]
        g_surp = gr["Go_NetIncome"]   - gr["Go_TotalOutflow"]
        stay_total += s_surp
        go_total   += g_surp
        diff = g_surp - s_surp

        t.add_row(
            str(int(sr["Month"])),
            str(sr["Date"]),
            d(sr["Stay_TotalOutflow"]),
            signed(s_surp),
            d(gr["Go_TotalOutflow"]),
            signed(g_surp),
            signed(diff),
        )

    t.add_section()
    t.add_row("Total", "", "", signed(stay_total), "", signed(go_total),
              signed(go_total - stay_total))
    t.add_row("Avg/mo", "", "", signed(stay_total / 12), "", signed(go_total / 12),
              signed((go_total - stay_total) / 12))
    console.print(t)
    console.print("[dim]Use `costs` command to see what's inside each outflow number.[/dim]")


# ---------------------------------------------------------------------------
# costs — per-category breakdown for the Go scenario
# ---------------------------------------------------------------------------

@cli.command()
@shared_options
@click.option("--month", default=None, type=int,
              help="Specific month to inspect (default: shows before and after house sale)")
def costs(month, **kw):
    """Monthly cost breakdown for the Go scenario — what's actually in each outflow.

    By default shows two months side-by-side: the last month before the house
    sells and the first full month after. Pass --month N to inspect any month.
    """
    p = build_params(**kw)
    _, ev_list = simulate_go(p)
    go_df, _ = simulate_go(p)

    # Find house-sale month from events
    house_sale_m = next(
        (ev["Month"] for ev in ev_list if "House sold" in ev["Event"]), None)

    if month is not None:
        months_to_show = [month]
        labels = [f"Month {month}"]
    elif house_sale_m:
        before = max(1, house_sale_m - 1)
        after  = min(120, house_sale_m + 1)
        months_to_show = [before, after]
        labels = [f"Month {before} (before house sale)", f"Month {after} (after house sale)"]
    else:
        months_to_show = [1, 6]
        labels = ["Month 1", "Month 6"]

    console.print(_header("Go Scenario — Monthly Cost Breakdown", p))
    if house_sale_m:
        console.print(f"  House sells at Month {house_sale_m}. "
                      f"Mortgage + housing costs drop to $0 after that.\n")

    # All line items: (label, df_column, group)
    ALL_LINES = [
        ("Mortgage P&I",    "Go_MortgageOut",  "Housing"),
        ("Property tax",    "Go_PropTax",       "Housing"),
        ("Home insurance",  "Go_HOI",           "Housing"),
        ("Utilities",       "Go_HomeUtil",      "Housing"),
        ("Home maint.",     "Go_HomeMaint",     "Housing"),
        ("Truck loan",      "Go_TruckLoanOut",  "Truck"),
        ("Truck insurance", "Go_TruckIns",      "Truck"),
        ("Truck fuel",      "Go_TruckFuel",     "Truck"),
        ("Truck maint.",    "Go_TruckMaint",    "Truck"),
        ("RV loan",         "Go_RVLoanOut",     "RV"),
        ("RV insurance",    "Go_RVIns",         "RV"),
        ("Campground",      "Go_Campground",    "RV"),
        ("Propane",         "Go_Propane",       "RV"),
        ("Internet",        "Go_Internet",      "RV"),
        ("RV maint.",       "Go_RVMaint",       "RV"),
        ("Groceries",       "Go_Groceries",     "RV"),
        ("Domicile mail",   "Go_DomicileMail",  "RV"),
        ("Emerg. reserve",  "Go_EmergReserve",  "RV"),
    ]
    GROUPS = ["Housing", "Truck", "RV"]
    GROUP_COLS = {g: [col for _, col, grp in ALL_LINES if grp == g] for g in GROUPS}

    for col_m, label in zip(months_to_show, labels):
        row = go_df.iloc[col_m - 1]
        total_out = row["Go_TotalOutflow"]
        surplus = row["Go_NetIncome"] - total_out
        console.print(
            f"[bold]{label}[/bold]  —  "
            f"Income: [cyan]{d(row['Go_NetIncome'])}/mo[/cyan]  |  "
            f"Total outflow: [cyan]{d(total_out)}/mo[/cyan]  |  "
            f"Surplus: {signed(surplus)}/mo")

        # --- Grouped breakdown ---
        t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        t.add_column("Group",    min_width=10)
        t.add_column("Line item", min_width=17, style="dim")
        t.add_column("Amount",   justify="right", min_width=9)
        t.add_column("% total",  justify="right", min_width=8)

        for grp in GROUPS:
            grp_total = sum(row[c] for c in GROUP_COLS[grp])
            t.add_row(f"[bold]{grp}[/bold]", "",
                      f"[bold]{d(grp_total)}[/bold]",
                      f"[bold]{grp_total/total_out*100:.0f}%[/bold]")
            for lbl, col, g in ALL_LINES:
                if g != grp:
                    continue
                val = row[col]
                if val == 0:
                    t.add_row("", lbl, f"[dim]{d(val)}[/dim]", "[dim]—[/dim]")
                else:
                    bar = "█" * max(1, round(val / total_out * 20))
                    t.add_row("", lbl, d(val),
                              f"[dim]{val/total_out*100:.0f}%[/dim] {bar}")
            t.add_section()

        t.add_row("[bold]TOTAL[/bold]", "", f"[bold]{d(total_out)}[/bold]", "[bold]100%[/bold]")
        console.print(t)

        # --- Ranked list (non-zero only) ---
        ranked = sorted(
            [(lbl, row[col]) for lbl, col, _ in ALL_LINES if row[col] > 0],
            key=lambda x: x[1], reverse=True)
        console.print("  [bold]Ranked by size:[/bold]")
        for rank, (lbl, val) in enumerate(ranked, 1):
            bar = "█" * max(1, round(val / total_out * 30))
            console.print(f"  {rank:>2}. {lbl:<18} {d(val):>8}  "
                          f"({val/total_out*100:.0f}%)  [cyan]{bar}[/cyan]")
        console.print()


# ---------------------------------------------------------------------------
# networth
# ---------------------------------------------------------------------------

@cli.command()
@shared_options
def networth(**kw):
    """Year-by-year net worth: Stay vs. Go."""
    p = build_params(**kw)
    stay_df = simulate_stay(p)
    go_df, _ = simulate_go(p)

    snw = compute_starting_networth(p)
    console.print(_header("Net Worth — Year-by-Year", p))
    console.print(f"  Starting net worth: [bold]{d(snw)}[/bold]\n")

    t = Table(box=box.SIMPLE_HEAD, header_style="bold")
    t.add_column("Year",       justify="right", min_width=5)
    t.add_column("Stay NW",    justify="right", min_width=13)
    t.add_column("Stay Gain",  justify="right", min_width=13)
    t.add_column("Go NW",      justify="right", min_width=13)
    t.add_column("Go Gain",    justify="right", min_width=13)
    t.add_column("Go − Stay",  justify="right", min_width=13)

    for yr in range(1, 11):
        idx   = yr * 12 - 1
        s_nw  = stay_df["Stay_NetWorth"].iloc[idx]
        g_nw  = go_df["Go_NetWorth"].iloc[idx]
        diff  = g_nw - s_nw
        color = "green" if diff >= 0 else "red"
        t.add_row(
            str(yr),
            d(s_nw), signed(s_nw - snw),
            d(g_nw), signed(g_nw - snw),
            f"[{color}]{'+' if diff >= 0 else ''}{d(diff).replace('$','')}[/{color}]",
        )
    console.print(t)


# ---------------------------------------------------------------------------
# breakeven
# ---------------------------------------------------------------------------

@cli.command()
@shared_options
def breakeven(**kw):
    """When (if ever) does Go's net worth overtake Stay's?"""
    p = build_params(**kw)
    stay_df = simulate_stay(p)
    go_df, events = simulate_go(p)

    diffs  = go_df["Go_NetWorth"].values - stay_df["Stay_NetWorth"].values
    dates  = go_df["Date"].values
    # Only flag when Go rises above Stay (negative → positive), not when it falls behind
    crossover = next(
        (i + 1 for i in range(1, len(diffs)) if diffs[i-1] < 0 and diffs[i] >= 0),
        None,
    )

    console.print(_header("Breakeven Analysis", p))

    if crossover:
        console.print(
            f"\n[green bold]Go overtakes Stay at Month {crossover}[/green bold] "
            f"(~{crossover//12}y {crossover%12}m from today, "
            f"around {str(dates[crossover-1])[:7]})\n"
        )
    else:
        s10 = stay_df["Stay_NetWorth"].iloc[-1]
        g10 = go_df["Go_NetWorth"].iloc[-1]
        leader = "Stay" if s10 > g10 else "Go"
        console.print(
            f"\n[yellow]No crossover in 10 years. "
            f"{leader} leads at year 10 by {d(abs(s10 - g10))}.[/yellow]\n"
        )

    # Show every year-end gap
    t = Table(box=box.SIMPLE_HEAD, header_style="bold")
    t.add_column("Year",      justify="right", min_width=5)
    t.add_column("Stay NW",   justify="right", min_width=13)
    t.add_column("Go NW",     justify="right", min_width=13)
    t.add_column("Go − Stay", justify="right", min_width=14)
    t.add_column("Leader",    min_width=6)

    for yr in range(1, 11):
        idx  = yr * 12 - 1
        s_nw = stay_df["Stay_NetWorth"].iloc[idx]
        g_nw = go_df["Go_NetWorth"].iloc[idx]
        diff = g_nw - s_nw
        mark = "★" if crossover and abs(crossover // 12 - yr) <= 1 else ""
        t.add_row(
            f"{yr} {mark}",
            d(s_nw), d(g_nw),
            signed(diff),
            "[green]Go[/green]" if diff >= 0 else "[red]Stay[/red]",
        )
    console.print(t)

    if events:
        console.print("\n[dim]Key Go events:[/dim]")
        for ev in events:
            console.print(f"  [dim]Month {ev['Month']:>3}  {ev['Event']}[/dim]")


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------

@cli.command()
@shared_options
def events(**kw):
    """Life events in the Go scenario: what happens and when."""
    p = build_params(**kw)
    _, ev_list = simulate_go(p)

    console.print(_header("Go Scenario — Life Events", p))

    if not ev_list:
        console.print("[yellow]No events fired (all dates fall beyond simulation window).[/yellow]")
        return

    t = Table(box=box.SIMPLE_HEAD, header_style="bold")
    t.add_column("Month",      justify="right", min_width=6)
    t.add_column("Date",       min_width=11)
    t.add_column("Event",      min_width=50)
    t.add_column("NW at Event", justify="right", min_width=14)

    for ev in ev_list:
        t.add_row(
            str(ev["Month"]),
            str(ev["Date"]),
            ev["Event"],
            d(ev["NetWorthAtEvent"]),
        )
    console.print(t)


if __name__ == "__main__":
    cli()
