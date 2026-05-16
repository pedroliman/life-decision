"""
Cash Flow & Net Worth Simulator: "Stay vs. Go" RV Decision
============================================================
Single-file Streamlit app. All financial calculations in simulate_stay()
and simulate_go(). Month-by-month simulation over 10 years (120 months).
"""

import json
import math
from datetime import date, timedelta
from io import StringIO

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Financial math helpers
# ---------------------------------------------------------------------------

def monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    """Standard fixed-payment amortization: P×r(1+r)^n / ((1+r)^n − 1)."""
    if principal <= 0 or months <= 0:
        return 0.0
    if annual_rate == 0:
        return principal / months
    r = annual_rate / 12
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def amortize_month(balance: float, annual_rate: float, fixed_payment: float):
    """
    Return (interest, principal, new_balance) for one month of amortization.
    Interest = balance × monthly_rate; principal = payment − interest (capped at balance).
    """
    if balance <= 0:
        return 0.0, 0.0, 0.0
    r = annual_rate / 12
    interest = balance * r
    principal = min(max(fixed_payment - interest, 0.0), balance)
    return interest, principal, balance - principal


def date_to_month_index(event_date: date, start_date: date) -> int:
    """0-based month index when an event occurs relative to start_date."""
    delta = (event_date.year - start_date.year) * 12 + (event_date.month - start_date.month)
    return max(0, delta)


def depreciate_monthly(value: float, annual_rate: float) -> float:
    """Geometric monthly depreciation: value × (1 − annual_rate/12)."""
    return value * (1 - annual_rate / 12)


# ---------------------------------------------------------------------------
# Core simulation: Stay Scenario
# ---------------------------------------------------------------------------

def simulate_stay(p: dict) -> pd.DataFrame:
    """
    Simulate 'Stay in house' scenario month-by-month for 120 months.

    Monthly flow:
      1. Gross income (grows annually at income_growth_rate)
      2. Retirement contribution (employee + employer, IRS-capped)
      3. Tax withholding (federal + NC state + FICA)
      4. Net take-home
      5. Fixed outflows: mortgage P&I, property tax, HOI, utilities, groceries,
         CX-5 fuel, CX-5 insurance, home maintenance, CX-5 loan payment
      6. Retirement balance compounds monthly
      7. Cash above emergency floor earns taxable_return; below earns cash_apy
      8. Assets appreciate/depreciate; liabilities amortize
    """
    rows = []
    today = p["today"]

    # Liquid wealth: track as a single pool, split into floor cash + taxable investments
    liquid = p["starting_cash"]
    retirement = p["starting_retirement"]

    # House
    house_value = p["home_value"]
    mortgage_balance = p["mortgage_balance"]
    mortgage_rate = p["mortgage_rate"]
    mortgage_months_left = p["mortgage_months_remaining"]
    mortgage_pmt = monthly_payment(mortgage_balance, mortgage_rate, mortgage_months_left)

    # CX-5
    cx5_value = p["cx5_value"]
    cx5_balance = p["cx5_balance"]
    cx5_months_left = p["cx5_months_remaining"]
    cx5_pmt = p["cx5_monthly_payment"]
    cx5_rate = p["cx5_rate"]

    # Aliner — kept forever in Stay scenario, depreciated monthly
    aliner_value = p["aliner_value"]

    annual_gross_base = p["gross_annual_income"]
    employee_pct = p["employee_contribution_pct"]
    employer_pct = p["employer_match_pct"]
    irs_employee_limit = p["irs_employee_limit"]
    irs_combined_limit = p["irs_combined_limit"]
    is_traditional = p["is_traditional"]

    ytd_employee = 0.0
    ytd_combined = 0.0
    current_year = today.year

    for m in range(120):
        yr = today.year + (today.month - 1 + m) // 12
        mo = (today.month - 1 + m) % 12 + 1
        month_date = date(yr, mo, 1)

        if month_date.year != current_year:
            current_year = month_date.year
            ytd_employee = 0.0
            ytd_combined = 0.0

        # --- Income ---
        years_elapsed = m // 12
        gross_monthly = annual_gross_base * (1 + p["income_growth_rate"]) ** years_elapsed / 12

        # --- Retirement contributions (IRS-capped) ---
        desired_employee = gross_monthly * employee_pct
        desired_employer = gross_monthly * employer_pct
        actual_employee = min(desired_employee, max(0, irs_employee_limit - ytd_employee))
        room_combined = max(0, irs_combined_limit - ytd_combined - actual_employee)
        actual_employer = min(desired_employer, room_combined)
        ytd_employee += actual_employee
        ytd_combined += actual_employee + actual_employer

        # --- Taxes ---
        # Traditional 401k: contributions reduce federal/state taxable income
        taxable_income = gross_monthly - (actual_employee if is_traditional else 0)
        federal_tax = taxable_income * p["federal_effective_rate"]
        state_tax = taxable_income * p["nc_state_rate"]
        fica = gross_monthly * p["fica_rate"]
        # Roth: employee contribution is a post-tax deduction from take-home
        post_tax_retirement_deduction = actual_employee if not is_traditional else 0.0
        net_income = gross_monthly - federal_tax - state_tax - fica - post_tax_retirement_deduction

        # --- Outflows (inflation-adjusted) ---
        inf = (1 + p["inflation_rate"] / 12) ** m

        # Mortgage
        if mortgage_months_left > 0 and mortgage_balance > 0:
            _, _, mortgage_balance = amortize_month(mortgage_balance, mortgage_rate, mortgage_pmt)
            mortgage_months_left -= 1
            mortgage_outflow = mortgage_pmt
        else:
            mortgage_outflow = 0.0

        # CX-5 loan payment
        if cx5_balance > 0 and cx5_months_left > 0:
            _, _, cx5_balance = amortize_month(cx5_balance, cx5_rate, cx5_pmt)
            cx5_months_left -= 1
            cx5_loan_outflow = cx5_pmt
        else:
            cx5_loan_outflow = 0.0

        property_tax = p["property_tax_monthly"] * inf
        hoi = p["homeowners_insurance_monthly"] * inf
        utilities = p["home_utilities_monthly"] * inf
        groceries = p["groceries_monthly"] * inf
        fuel_cx5 = p["cx5_fuel_monthly"] * inf
        cx5_insurance = p["cx5_insurance_monthly"] * inf
        # Home maintenance: annual % of current house value, monthly
        home_maintenance = house_value * p["home_maintenance_pct"] / 12

        total_outflow = (mortgage_outflow + property_tax + hoi + utilities + groceries +
                         fuel_cx5 + cx5_insurance + home_maintenance + cx5_loan_outflow)

        # --- Update liquid wealth ---
        liquid = liquid + net_income - total_outflow

        # --- Retirement compounding ---
        retirement = retirement * (1 + p["retirement_return"] / 12) + actual_employee + actual_employer

        # --- Investment return on liquid wealth ---
        floor = p["emergency_cash_floor"]
        if liquid > floor:
            excess_gain = (liquid - floor) * (p["taxable_return"] / 12)
            floor_gain = floor * (p["cash_apy"] / 12)
            liquid += excess_gain + floor_gain
        elif liquid > 0:
            liquid *= (1 + p["cash_apy"] / 12)

        # Report cash vs taxable investments
        cash_reported = min(liquid, floor)
        taxable_investments_reported = max(0.0, liquid - floor)

        # --- Asset/liability updates ---
        house_value = house_value * (1 + p["home_appreciation_rate"] / 12)
        cx5_value = depreciate_monthly(cx5_value, p["cx5_depreciation_rate"])
        aliner_value = depreciate_monthly(aliner_value, p["aliner_depreciation_rate"])

        assets = house_value + cx5_value + aliner_value
        debt = mortgage_balance + cx5_balance
        net_worth = liquid + retirement + assets - debt

        rows.append({
            "Month": m + 1,
            "Date": month_date,
            "Stay_Cash": cash_reported,
            "Stay_TaxableInv": taxable_investments_reported,
            "Stay_Assets": assets,
            "Stay_Retirement": retirement,
            "Stay_Debt": debt,
            "Stay_NetWorth": net_worth,
            "Stay_HouseValue": house_value,
            "Stay_MortgageBalance": mortgage_balance,
            "Stay_CX5Value": cx5_value,
            "Stay_AlineValue": aliner_value,
            "Stay_CX5Balance": cx5_balance,
            "Stay_GrossMonthly": gross_monthly,
            "Stay_NetIncome": net_income,
            "Stay_TotalOutflow": total_outflow,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Core simulation: Go Scenario
# ---------------------------------------------------------------------------

def simulate_go(p: dict) -> pd.DataFrame:
    """
    Simulate 'Sell house, buy truck + RV, go full-time' scenario for 120 months.

    Life events fire at the month matching their input date:
      - Truck purchase + CX-5 trade-in
      - Aliner sale
      - House sale
      - RV purchase
      - Domicile change (NC → FL tax rate)

    Events are applied at the START of each month before cash-flow calculations,
    so the full month's P&L reflects the new state of assets/liabilities.
    """
    rows = []
    today = p["today"]
    events = []

    # Liquid wealth pool
    liquid = p["starting_cash"]
    retirement = p["starting_retirement"]

    # House
    house_value = p["home_value"]
    mortgage_balance = p["mortgage_balance"]
    mortgage_rate = p["mortgage_rate"]
    mortgage_months_left = p["mortgage_months_remaining"]
    mortgage_pmt = monthly_payment(mortgage_balance, mortgage_rate, mortgage_months_left)
    house_sold = False

    # CX-5
    cx5_value = p["cx5_value"]
    cx5_balance = p["cx5_balance"]
    cx5_months_left = p["cx5_months_remaining"]
    cx5_pmt = p["cx5_monthly_payment"]
    cx5_rate = p["cx5_rate"]
    cx5_active = True

    # Aliner
    aliner_value = p["aliner_value"]
    aliner_sold = False

    # Truck
    truck_owned = False
    truck_value = 0.0
    truck_balance = 0.0
    truck_pmt = 0.0
    truck_months_left = 0
    truck_rate = 0.0

    # RV
    rv_owned = False
    rv_value = 0.0
    rv_balance = 0.0
    rv_pmt = 0.0
    rv_months_left = 0
    rv_rate = 0.0
    rv_start_month = 0
    emergency_reserve_built = 0.0

    # Event month indices
    truck_month = date_to_month_index(p["truck_purchase_date"], today)
    aliner_sale_month = date_to_month_index(p["aliner_sale_date"], today)
    house_sale_month = date_to_month_index(p["house_sale_date"], today)
    rv_month = date_to_month_index(p["rv_purchase_date"], today)
    domicile_month = date_to_month_index(p["domicile_change_date"], today)

    current_state_rate = p["nc_state_rate"]
    domicile_changed = False

    annual_gross_base = p["gross_annual_income"]
    employee_pct = p["employee_contribution_pct"]
    employer_pct = p["employer_match_pct"]
    irs_employee_limit = p["irs_employee_limit"]
    irs_combined_limit = p["irs_combined_limit"]
    is_traditional = p["is_traditional"]

    ytd_employee = 0.0
    ytd_combined = 0.0
    current_year = today.year

    def current_nw():
        """Snapshot net worth for event log."""
        a = ((house_value if not house_sold else 0) +
             (aliner_value if not aliner_sold else 0) +
             (cx5_value if cx5_active else 0) +
             (truck_value if truck_owned else 0) +
             (rv_value if rv_owned else 0))
        d = ((mortgage_balance if not house_sold else 0) +
             (cx5_balance if cx5_active else 0) +
             (truck_balance if truck_owned else 0) +
             (rv_balance if rv_owned else 0))
        return liquid + retirement + a - d

    for m in range(120):
        yr = today.year + (today.month - 1 + m) // 12
        mo = (today.month - 1 + m) % 12 + 1
        month_date = date(yr, mo, 1)

        if month_date.year != current_year:
            current_year = month_date.year
            ytd_employee = 0.0
            ytd_combined = 0.0

        # ----------------------------------------------------------------
        # LIFE EVENTS (fire before monthly cash-flow)
        # ----------------------------------------------------------------

        # Domicile change: switch to FL tax rate
        if not domicile_changed and m == domicile_month:
            current_state_rate = p["fl_state_rate"]
            domicile_changed = True
            events.append({"Month": m + 1, "Date": month_date,
                           "Event": "Domicile change to FL (0% state income tax)",
                           "NetWorthAtEvent": current_nw()})

        # Truck purchase + CX-5 trade-in
        if not truck_owned and m == truck_month:
            truck_price = p["truck_purchase_price"]
            truck_down_pmt = p["truck_down_payment"]

            # CX-5 trade-in: if underwater, negative equity rolls into truck loan
            cx5_trade = p["cx5_tradein_value"]
            if cx5_balance > cx5_trade:
                # Negative equity: roll into truck financing
                effective_financed = truck_price - truck_down_pmt + (cx5_balance - cx5_trade)
            else:
                # Positive equity: reduces financed amount
                effective_financed = truck_price - truck_down_pmt - (cx5_trade - cx5_balance)

            effective_financed = max(effective_financed, 0.0)
            liquid -= truck_down_pmt

            truck_rate = p["truck_loan_apr"]
            truck_months_left = p["truck_loan_months"]
            truck_balance = effective_financed
            truck_pmt = monthly_payment(truck_balance, truck_rate, truck_months_left)
            truck_value = truck_price
            truck_owned = True

            # CX-5 disposed
            cx5_active = False
            cx5_balance = 0.0
            cx5_value = 0.0

            events.append({"Month": m + 1, "Date": month_date,
                           "Event": (f"Truck purchased (${truck_price:,.0f}); "
                                     f"CX-5 traded at ${cx5_trade:,.0f}"),
                           "NetWorthAtEvent": current_nw()})

        # Aliner sale: convert to cash at current depreciated value
        if not aliner_sold and m == aliner_sale_month:
            proceeds = aliner_value
            liquid += proceeds
            aliner_sold = True
            aliner_value = 0.0
            events.append({"Month": m + 1, "Date": month_date,
                           "Event": f"Aliner sold for ${proceeds:,.0f}",
                           "NetWorthAtEvent": current_nw()})

        # House sale
        if not house_sold and m == house_sale_month:
            # Appreciate to current point (already done in prior months' loops)
            if p.get("house_sale_price_override") and p.get("house_sale_price"):
                sale_price = p["house_sale_price"]
            else:
                sale_price = house_value  # use appreciated value
            selling_costs = sale_price * p["house_selling_costs_pct"]
            net_proceeds = sale_price - selling_costs - mortgage_balance
            liquid += net_proceeds
            house_sold = True
            house_value = 0.0
            mortgage_balance = 0.0
            events.append({"Month": m + 1, "Date": month_date,
                           "Event": (f"House sold at ${sale_price:,.0f}; "
                                     f"net proceeds ${net_proceeds:,.0f}"),
                           "NetWorthAtEvent": current_nw()})

        # RV purchase
        if not rv_owned and m == rv_month:
            rv_price = p["rv_purchase_price"]

            # Down payment logic: use all available cash above emergency floor if flag set
            if p.get("rv_use_all_available_cash"):
                floor = p["emergency_cash_floor"]
                rv_down = max(0.0, min(liquid - floor, rv_price))
            else:
                rv_down = p["rv_down_payment"]
                rv_down = min(rv_down, liquid)  # can't spend more than available

            liquid -= rv_down
            liquid -= p["rv_setup_costs"]

            rv_rate = p["rv_loan_apr"]
            rv_months_left = p["rv_loan_months"]
            rv_balance = max(rv_price - rv_down, 0.0)
            rv_pmt = monthly_payment(rv_balance, rv_rate, rv_months_left)
            rv_value = rv_price
            rv_owned = True
            rv_start_month = m

            events.append({"Month": m + 1, "Date": month_date,
                           "Event": (f"RV purchased (${rv_price:,.0f}); "
                                     f"down ${rv_down:,.0f}; "
                                     f"setup costs ${p['rv_setup_costs']:,.0f}"),
                           "NetWorthAtEvent": current_nw()})

        # ----------------------------------------------------------------
        # MONTHLY INCOME & TAXES
        # ----------------------------------------------------------------
        years_elapsed = m // 12
        gross_monthly = annual_gross_base * (1 + p["income_growth_rate"]) ** years_elapsed / 12

        desired_employee = gross_monthly * employee_pct
        desired_employer = gross_monthly * employer_pct
        actual_employee = min(desired_employee, max(0, irs_employee_limit - ytd_employee))
        room_combined = max(0, irs_combined_limit - ytd_combined - actual_employee)
        actual_employer = min(desired_employer, room_combined)
        ytd_employee += actual_employee
        ytd_combined += actual_employee + actual_employer

        taxable_income = gross_monthly - (actual_employee if is_traditional else 0)
        federal_tax = taxable_income * p["federal_effective_rate"]
        state_tax = taxable_income * current_state_rate
        fica = gross_monthly * p["fica_rate"]
        post_tax_retirement_deduction = actual_employee if not is_traditional else 0.0
        net_income = gross_monthly - federal_tax - state_tax - fica - post_tax_retirement_deduction

        # ----------------------------------------------------------------
        # MONTHLY OUTFLOWS (inflation-adjusted)
        # ----------------------------------------------------------------
        inf = (1 + p["inflation_rate"] / 12) ** m

        # Mortgage (if house not yet sold)
        if not house_sold and mortgage_balance > 0 and mortgage_months_left > 0:
            _, _, mortgage_balance = amortize_month(mortgage_balance, mortgage_rate, mortgage_pmt)
            mortgage_months_left -= 1
            mortgage_outflow = mortgage_pmt
        else:
            mortgage_outflow = 0.0

        # CX-5 loan
        if cx5_active and cx5_balance > 0 and cx5_months_left > 0:
            _, _, cx5_balance = amortize_month(cx5_balance, cx5_rate, cx5_pmt)
            cx5_months_left -= 1
            cx5_loan_outflow = cx5_pmt
        else:
            cx5_loan_outflow = 0.0

        # CX-5 operating costs
        cx5_insurance_out = p["cx5_insurance_monthly"] * inf if cx5_active else 0.0
        cx5_fuel_out = p["cx5_fuel_monthly"] * inf if cx5_active else 0.0

        # House operating costs
        if not house_sold:
            property_tax = p["property_tax_monthly"] * inf
            hoi = p["homeowners_insurance_monthly"] * inf
            home_utilities = p["home_utilities_monthly"] * inf
            home_maintenance = house_value * p["home_maintenance_pct"] / 12
            house_groceries = p["groceries_monthly"] * inf
        else:
            property_tax = hoi = home_utilities = home_maintenance = house_groceries = 0.0

        # Truck loan + operating
        if truck_owned and truck_balance > 0 and truck_months_left > 0:
            _, _, truck_balance = amortize_month(truck_balance, truck_rate, truck_pmt)
            truck_months_left -= 1
            truck_loan_outflow = truck_pmt
        else:
            truck_loan_outflow = 0.0
        truck_insurance_out = p["truck_insurance_monthly"] * inf if truck_owned else 0.0
        # Truck fuel only applies while RVing (driving the rig)
        truck_fuel_out = p["truck_fuel_monthly"] * inf if (truck_owned and rv_owned) else 0.0
        truck_maint_out = p["truck_annual_maintenance"] / 12 * inf if truck_owned else 0.0

        # RV loan + operating
        if rv_owned and rv_balance > 0 and rv_months_left > 0:
            _, _, rv_balance = amortize_month(rv_balance, rv_rate, rv_pmt)
            rv_months_left -= 1
            rv_loan_outflow = rv_pmt
        else:
            rv_loan_outflow = 0.0

        if rv_owned:
            rv_insurance_out = p["rv_insurance_monthly"] * inf
            campground_out = p["campground_fees_monthly"] * inf
            propane_out = p["propane_monthly"] * inf
            internet_out = p["internet_monthly"] * inf
            rv_maint_out = p["rv_maintenance_monthly"] * inf
            rv_groceries = p["groceries_monthly"] * inf
            domicile_mail_out = p["domicile_mail_monthly"] * inf
            # Emergency reserve buildup ($250/mo until $15K reached)
            if emergency_reserve_built < p["emergency_reserve_target"]:
                emerg_out = min(p["emergency_reserve_monthly"],
                                p["emergency_reserve_target"] - emergency_reserve_built)
                emergency_reserve_built += emerg_out
            else:
                emerg_out = 0.0
            rv_operating = (rv_insurance_out + campground_out + propane_out + internet_out +
                            rv_maint_out + rv_groceries + domicile_mail_out + emerg_out)
        else:
            rv_loan_outflow = 0.0
            rv_operating = 0.0
            # Still need groceries before RV
            if not house_sold:
                pass  # covered by house_groceries
            else:
                rv_operating += p["groceries_monthly"] * inf  # homeless but not RVing yet

        total_outflow = (
            mortgage_outflow + property_tax + hoi + home_utilities + home_maintenance +
            house_groceries +
            cx5_loan_outflow + cx5_insurance_out + cx5_fuel_out +
            truck_loan_outflow + truck_insurance_out + truck_fuel_out + truck_maint_out +
            rv_loan_outflow + rv_operating
        )

        # ----------------------------------------------------------------
        # UPDATE LIQUID WEALTH
        # ----------------------------------------------------------------
        liquid = liquid + net_income - total_outflow

        # Retirement compounding
        retirement = (retirement * (1 + p["retirement_return"] / 12) +
                      actual_employee + actual_employer)

        # Investment return on excess liquid wealth
        floor = p["emergency_cash_floor"]
        if liquid > floor:
            liquid += (liquid - floor) * (p["taxable_return"] / 12)
            liquid += floor * (p["cash_apy"] / 12)
        elif liquid > 0:
            liquid *= (1 + p["cash_apy"] / 12)

        # ----------------------------------------------------------------
        # ASSET DEPRECIATION
        # ----------------------------------------------------------------
        if not house_sold:
            house_value = house_value * (1 + p["home_appreciation_rate"] / 12)

        if truck_owned:
            yrs_truck = m / 12
            tdep = (p["truck_depreciation_rate_early"] if yrs_truck < 5
                    else p["truck_depreciation_rate_late"])
            truck_value = depreciate_monthly(truck_value, tdep)

        if rv_owned:
            yrs_rv = (m - rv_start_month) / 12
            rdep = (p["rv_depreciation_rate_early"] if yrs_rv < 5
                    else p["rv_depreciation_rate_late"])
            rv_value = depreciate_monthly(rv_value, rdep)

        if not aliner_sold:
            aliner_value = depreciate_monthly(aliner_value, p["aliner_depreciation_rate"])

        if cx5_active:
            cx5_value = depreciate_monthly(cx5_value, p["cx5_depreciation_rate"])

        # ----------------------------------------------------------------
        # NET WORTH SNAPSHOT
        # ----------------------------------------------------------------
        cash_reported = min(liquid, floor)
        taxable_investments_reported = max(0.0, liquid - floor)

        assets = ((house_value if not house_sold else 0) +
                  (aliner_value if not aliner_sold else 0) +
                  (cx5_value if cx5_active else 0) +
                  (truck_value if truck_owned else 0) +
                  (rv_value if rv_owned else 0))
        debt = ((mortgage_balance if not house_sold else 0) +
                (cx5_balance if cx5_active else 0) +
                (truck_balance if truck_owned else 0) +
                (rv_balance if rv_owned else 0))
        net_worth = liquid + retirement + assets - debt

        rows.append({
            "Month": m + 1,
            "Date": month_date,
            "Go_Cash": cash_reported,
            "Go_TaxableInv": taxable_investments_reported,
            "Go_Assets": assets,
            "Go_Retirement": retirement,
            "Go_Debt": debt,
            "Go_NetWorth": net_worth,
            "Go_HouseValue": house_value if not house_sold else 0,
            "Go_MortgageBalance": mortgage_balance if not house_sold else 0,
            "Go_TruckValue": truck_value if truck_owned else 0,
            "Go_TruckBalance": truck_balance if truck_owned else 0,
            "Go_RVValue": rv_value if rv_owned else 0,
            "Go_RVBalance": rv_balance if rv_owned else 0,
            "Go_GrossMonthly": gross_monthly,
            "Go_NetIncome": net_income,
            "Go_TotalOutflow": total_outflow,
        })

    return pd.DataFrame(rows), events


# ---------------------------------------------------------------------------
# Starting net worth (month 0 pre-simulation validation anchor)
# ---------------------------------------------------------------------------

def compute_starting_networth(p: dict) -> float:
    """
    Compute starting net worth before any simulation:
    Cash + Retirement + House equity + CX-5 equity + Aliner.
    Both scenarios begin here identically.
    """
    house_equity = p["home_value"] - p["mortgage_balance"]
    cx5_equity = p["cx5_value"] - p["cx5_balance"]
    return (p["starting_cash"] + p["starting_retirement"] +
            house_equity + cx5_equity + p["aliner_value"])


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Stay vs. Go RV Simulator", layout="wide")
    st.title("Cash Flow & Net Worth Simulator: Stay vs. Go RV Decision")

    today = date.today()

    # -----------------------------------------------------------------------
    # SIDEBAR — all input parameters
    # -----------------------------------------------------------------------
    with st.sidebar:
        st.header("Starting Position")
        starting_cash = st.number_input("Starting Cash ($)", value=30_000, step=1_000,
                                         help="Liquid cash at simulation start")
        starting_retirement = st.number_input("Starting Retirement Balance ($)",
                                               value=60_000, step=1_000)

        st.header("Personal & Tax")
        gross_income = st.number_input("Gross Annual Income ($)", value=160_000, step=5_000)
        income_growth = st.slider("Income Annual Growth (%)", 0.0, 10.0, 3.0, 0.1) / 100
        nc_state_rate = st.slider("NC State Tax Rate (%)", 0.0, 10.0, 3.99, 0.01) / 100
        fl_state_rate = st.slider("FL State Tax Rate (%)", 0.0, 5.0, 0.0, 0.01) / 100
        federal_rate = st.slider("Federal Effective Tax Rate (%)", 0.0, 40.0, 18.0, 0.5) / 100
        fica_rate = st.slider("FICA Rate (%)", 0.0, 15.0, 7.65, 0.01) / 100

        st.header("Current House (Stay Scenario)")
        home_value = st.number_input("Current Home Value ($)", value=400_000, step=5_000)
        mortgage_balance_in = st.number_input("Mortgage Balance ($)", value=342_000, step=1_000)
        mortgage_rate_in = st.slider("Mortgage Interest Rate (%)", 0.0, 10.0, 5.0, 0.05) / 100
        mortgage_months_remaining = st.number_input("Months Remaining on Mortgage",
                                                      value=174, step=1)
        prop_tax = st.number_input("Property Tax ($/mo)", value=300, step=25)
        hoi = st.number_input("Homeowners Insurance ($/mo)", value=120, step=10)
        home_appreciation = st.slider("Annual Home Appreciation (%)", 0.0, 10.0, 2.0, 0.1) / 100
        home_maintenance_pct_in = st.slider("Annual Maintenance (% of Value)",
                                             0.0, 3.0, 1.0, 0.1) / 100
        home_utilities = st.number_input("Monthly Utilities ($)", value=350, step=25)
        groceries = st.number_input("Monthly Groceries ($)", value=800, step=50)
        cx5_fuel = st.number_input("Monthly Auto Fuel — CX-5 ($)", value=140, step=10)

        st.header("Current Car (CX-5)")
        cx5_balance_in = st.number_input("CX-5 Loan Balance ($)", value=20_000, step=500)
        cx5_pmt_in = st.number_input("CX-5 Monthly Payment ($)", value=500, step=25)
        cx5_months_in = st.number_input("CX-5 Months Remaining", value=36, step=1)
        cx5_value_in = st.number_input("CX-5 Current Value ($)", value=22_000, step=500)
        cx5_dep_in = st.slider("CX-5 Annual Depreciation (%)", 0.0, 25.0, 12.0, 0.5) / 100
        cx5_insurance_in = st.number_input("CX-5 Monthly Insurance ($)", value=90, step=5)
        cx5_rate_in = st.slider("CX-5 Loan Interest Rate (%)", 0.0, 15.0, 6.0, 0.1) / 100

        st.header("Aliner (Current Trailer)")
        aliner_val_in = st.number_input("Aliner Current Value ($)", value=8_000, step=500)
        aliner_dep_in = st.slider("Aliner Annual Depreciation (%)", 0.0, 15.0, 5.0, 0.5) / 100
        aliner_sale_date = st.date_input("Aliner Sale Date (Go only)",
                                          value=today + timedelta(days=44))

        st.header("Sell Decision (Go Scenario)")
        house_sale_date = st.date_input("House Sale Date",
                                         value=today + timedelta(days=90))
        house_sale_override = st.checkbox("Override house sale price?", value=False)
        house_sale_price_val = st.number_input("House Sale Price Override ($)",
                                                value=400_000, step=5_000,
                                                disabled=not house_sale_override)
        house_selling_costs = st.slider("Selling Costs (%)", 0.0, 10.0, 7.0, 0.25) / 100
        cx5_tradein_value = st.number_input("CX-5 Trade-in Value ($)", value=20_000, step=500)

        st.header("Truck (Ram 3500 — Go Only)")
        truck_purchase_date = st.date_input("Truck Purchase Date",
                                             value=today + timedelta(days=30))
        truck_price = st.number_input("Truck Purchase Price ($)", value=72_000, step=1_000)
        truck_down = st.number_input("Truck Down Payment ($)", value=0, step=1_000)
        truck_apr = st.slider("Truck Loan APR (%)", 0.0, 12.0, 0.0, 0.1) / 100
        truck_term = st.number_input("Truck Loan Term (months)", value=36, step=12)
        truck_dep_early = st.slider("Truck Depreciation Yrs 1-5 (%/yr)",
                                     0.0, 20.0, 5.0, 0.5) / 100
        truck_dep_late = st.slider("Truck Depreciation Yrs 6-10 (%/yr)",
                                    0.0, 20.0, 7.0, 0.5) / 100
        truck_insurance = st.number_input("Truck Monthly Insurance ($)", value=130, step=10)
        truck_fuel = st.number_input("Truck Monthly Fuel (while RVing, $)", value=400, step=25)
        truck_maintenance = st.number_input("Truck Annual Maintenance ($)",
                                             value=2_400, step=100)

        st.header("RV (Brinkley Z 3610 — Go Only)")
        rv_purchase_date = st.date_input("RV Purchase Date",
                                          value=today + timedelta(days=44))
        rv_price = st.number_input("RV Purchase Price ($)", value=115_000, step=1_000)
        use_house_proceeds = st.checkbox(
            "Use available cash (house proceeds) as RV down payment?", value=True,
            help="If checked, all liquid cash above the emergency floor will be used as RV down payment")
        rv_down_manual = st.number_input("Fixed RV Down Payment ($)", value=0, step=1_000,
                                          disabled=use_house_proceeds)
        rv_apr = st.slider("RV Loan APR (%)", 0.0, 12.0, 7.5, 0.1) / 100
        rv_term = st.number_input("RV Loan Term (months)", value=180, step=12)
        rv_dep_early = st.slider("RV Depreciation Yrs 1-5 (%/yr)", 0.0, 20.0, 8.0, 0.5) / 100
        rv_dep_late = st.slider("RV Depreciation Yrs 6-10 (%/yr)", 0.0, 20.0, 5.0, 0.5) / 100
        rv_insurance = st.number_input("RV Monthly Insurance ($)", value=200, step=10)
        rv_setup_costs = st.number_input("One-time RV Setup Costs ($)", value=6_000, step=500)

        st.header("RV Operating Costs ($/mo, Go Only)")
        campground_fees = st.number_input("Campground Fees", value=1_100, step=50)
        propane = st.number_input("Propane & Utilities", value=80, step=10)
        internet = st.number_input("Internet (Starlink + cellular)", value=190, step=10)
        rv_maintenance = st.number_input("RV Maintenance Reserve", value=400, step=25)
        domicile_mail = st.number_input("Domicile Mail Service", value=25, step=5)
        emerg_monthly = st.number_input("Emergency Reserve Buildup ($/mo)", value=250, step=50)
        emerg_target = st.number_input("Emergency Reserve Target ($)", value=15_000, step=1_000)

        st.header("Domicile Change")
        domicile_change_date = st.date_input("Domicile Change Date",
                                              value=today + timedelta(days=104))

        st.header("Retirement Account")
        employee_pct_in = st.slider("Employee Contribution (% of gross)",
                                     0.0, 25.0, 10.0, 0.5) / 100
        employer_pct_in = st.slider("Employer Match (% of gross)",
                                     0.0, 10.0, 4.0, 0.5) / 100
        retirement_return_in = st.slider("Annual Retirement Return (%)",
                                          0.0, 15.0, 8.0, 0.5) / 100
        account_type = st.radio("Account Type",
                                 ["Traditional 401(k)", "Roth 401(k)"])
        irs_emp_limit = st.number_input("IRS Employee Contribution Limit ($)",
                                         value=23_500, step=500)
        irs_combined = st.number_input("IRS Combined Limit ($)", value=70_000, step=500)

        st.header("Investment Assumptions")
        cash_apy = st.slider("Cash Savings APY (%)", 0.0, 8.0, 4.0, 0.25) / 100
        taxable_return = st.slider("Taxable Investment Return (%)",
                                    0.0, 15.0, 7.0, 0.5) / 100
        emergency_floor = st.number_input("Emergency Cash Floor ($)", value=25_000, step=1_000)
        inflation_rate = st.slider("Annual Inflation Rate (%)", 0.0, 8.0, 3.0, 0.25) / 100

    # -----------------------------------------------------------------------
    # Scenario Save / Load
    # -----------------------------------------------------------------------
    st.sidebar.markdown("---")
    st.sidebar.subheader("Scenario Management")
    scenario_snapshot = {
        "starting_cash": starting_cash,
        "starting_retirement": starting_retirement,
        "gross_income": gross_income,
        "home_value": home_value,
        "mortgage_balance": mortgage_balance_in,
        "rv_price": rv_price,
        "truck_price": truck_price,
    }
    st.sidebar.download_button(
        "Save Scenario (JSON)",
        data=json.dumps(scenario_snapshot, indent=2),
        file_name="scenario.json", mime="application/json")
    uploaded = st.sidebar.file_uploader("Load Scenario (JSON)", type=["json"])
    if uploaded:
        st.sidebar.info("Scenario loaded. Adjust sliders above to match saved values.")

    # -----------------------------------------------------------------------
    # Sensitivity Analysis Overrides (sidebar)
    # -----------------------------------------------------------------------
    st.sidebar.markdown("---")
    st.sidebar.subheader("Sensitivity Analysis")
    sens_appreciation = st.sidebar.slider(
        "House Appreciation Override (%/yr)", 0.0, 6.0,
        float(home_appreciation * 100), 0.25) / 100
    sens_rv_dep = st.sidebar.slider(
        "RV Depreciation Override (%/yr, yrs 1-5)", 5.0, 12.0,
        float(rv_dep_early * 100), 0.25) / 100
    sens_rv_costs = st.sidebar.slider(
        "RV Operating Costs Multiplier", 0.70, 1.30, 1.00, 0.05)
    sens_ret_return = st.sidebar.slider(
        "Retirement Return Override (%/yr)", 4.0, 12.0,
        float(retirement_return_in * 100), 0.25) / 100

    # -----------------------------------------------------------------------
    # Build parameter dict
    # -----------------------------------------------------------------------
    params = {
        "today": today,
        "starting_cash": float(starting_cash),
        "starting_retirement": float(starting_retirement),
        "gross_annual_income": float(gross_income),
        "income_growth_rate": income_growth,
        "nc_state_rate": nc_state_rate,
        "fl_state_rate": fl_state_rate,
        "federal_effective_rate": federal_rate,
        "fica_rate": fica_rate,
        # House
        "home_value": float(home_value),
        "mortgage_balance": float(mortgage_balance_in),
        "mortgage_rate": mortgage_rate_in,
        "mortgage_months_remaining": int(mortgage_months_remaining),
        "property_tax_monthly": float(prop_tax),
        "homeowners_insurance_monthly": float(hoi),
        "home_appreciation_rate": sens_appreciation,
        "home_maintenance_pct": home_maintenance_pct_in,
        "home_utilities_monthly": float(home_utilities),
        "groceries_monthly": float(groceries),
        "cx5_fuel_monthly": float(cx5_fuel),
        # CX-5
        "cx5_balance": float(cx5_balance_in),
        "cx5_monthly_payment": float(cx5_pmt_in),
        "cx5_months_remaining": int(cx5_months_in),
        "cx5_value": float(cx5_value_in),
        "cx5_depreciation_rate": cx5_dep_in,
        "cx5_insurance_monthly": float(cx5_insurance_in),
        "cx5_rate": cx5_rate_in,
        # Aliner
        "aliner_value": float(aliner_val_in),
        "aliner_depreciation_rate": aliner_dep_in,
        "aliner_sale_date": aliner_sale_date,
        # Go decisions
        "house_sale_date": house_sale_date,
        "house_sale_price": float(house_sale_price_val) if house_sale_override else None,
        "house_sale_price_override": house_sale_override,
        "house_selling_costs_pct": house_selling_costs,
        "cx5_tradein_value": float(cx5_tradein_value),
        # Truck
        "truck_purchase_date": truck_purchase_date,
        "truck_purchase_price": float(truck_price),
        "truck_down_payment": float(truck_down),
        "truck_loan_apr": truck_apr,
        "truck_loan_months": int(truck_term),
        "truck_depreciation_rate_early": truck_dep_early,
        "truck_depreciation_rate_late": truck_dep_late,
        "truck_insurance_monthly": float(truck_insurance),
        "truck_fuel_monthly": float(truck_fuel),
        "truck_annual_maintenance": float(truck_maintenance),
        # RV
        "rv_purchase_date": rv_purchase_date,
        "rv_purchase_price": float(rv_price),
        "rv_down_payment": float(rv_down_manual) if not use_house_proceeds else 0.0,
        "rv_use_all_available_cash": use_house_proceeds,
        "rv_loan_apr": rv_apr,
        "rv_loan_months": int(rv_term),
        "rv_depreciation_rate_early": sens_rv_dep,
        "rv_depreciation_rate_late": rv_dep_late,
        "rv_insurance_monthly": float(rv_insurance),
        "rv_setup_costs": float(rv_setup_costs),
        # RV operating (with sensitivity multiplier)
        "campground_fees_monthly": float(campground_fees) * sens_rv_costs,
        "propane_monthly": float(propane) * sens_rv_costs,
        "internet_monthly": float(internet) * sens_rv_costs,
        "rv_maintenance_monthly": float(rv_maintenance) * sens_rv_costs,
        "domicile_mail_monthly": float(domicile_mail),
        "emergency_reserve_monthly": float(emerg_monthly),
        "emergency_reserve_target": float(emerg_target),
        # Domicile
        "domicile_change_date": domicile_change_date,
        # Retirement
        "employee_contribution_pct": employee_pct_in,
        "employer_match_pct": employer_pct_in,
        "retirement_return": sens_ret_return,
        "is_traditional": account_type == "Traditional 401(k)",
        "irs_employee_limit": float(irs_emp_limit),
        "irs_combined_limit": float(irs_combined),
        # Investments
        "cash_apy": cash_apy,
        "taxable_return": taxable_return,
        "emergency_cash_floor": float(emergency_floor),
        "inflation_rate": inflation_rate,
    }

    # -----------------------------------------------------------------------
    # Run simulations
    # -----------------------------------------------------------------------
    with st.spinner("Running simulation..."):
        stay_df = simulate_stay(params)
        go_df, events = simulate_go(params)

    df = pd.merge(stay_df, go_df, on=["Month", "Date"])
    df["Difference"] = df["Go_NetWorth"] - df["Stay_NetWorth"]

    # -----------------------------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------------------------
    starting_nw = compute_starting_networth(params)
    stay_yr10 = stay_df["Stay_NetWorth"].iloc[-1]
    go_yr10 = go_df["Go_NetWorth"].iloc[-1]
    retire_yr10 = stay_df["Stay_Retirement"].iloc[-1]
    stay_m1 = stay_df["Stay_NetWorth"].iloc[0]
    go_m1 = go_df["Go_NetWorth"].iloc[0]

    crossover_month = None
    diff_series = df["Difference"]
    for i in range(1, len(diff_series)):
        if (diff_series.iloc[i - 1] < 0) != (diff_series.iloc[i] < 0):
            crossover_month = df["Month"].iloc[i]
            break

    warnings = []
    # Month-1 NW should be close to starting NW (one month of activity is fine)
    if abs(stay_m1 - go_m1) > 5_000:
        warnings.append(
            f"Month-1 net worth diverges significantly: "
            f"Stay=${stay_m1:,.0f} vs Go=${go_m1:,.0f} — "
            f"check if a major Go event fires in month 1")
    if stay_yr10 < 600_000:
        warnings.append(
            f"Stay year-10 net worth ${stay_yr10:,.0f} is lower than expected — "
            f"check income, expenses, or investment return settings")
    if retire_yr10 < 300_000:
        warnings.append(
            f"Year-10 retirement balance ${retire_yr10:,.0f} is lower than expected — "
            f"check contribution rates or return assumption")

    for w in warnings:
        st.warning(f"Validation: {w}")

    # -----------------------------------------------------------------------
    # KPI CARDS
    # -----------------------------------------------------------------------
    st.subheader("10-Year Summary")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Starting Net Worth", f"${starting_nw:,.0f}")
    c2.metric("Stay NW @ Year 10", f"${stay_yr10:,.0f}",
              delta=f"+${stay_yr10 - starting_nw:,.0f} gain")
    c3.metric("Go NW @ Year 10", f"${go_yr10:,.0f}",
              delta=f"${go_yr10 - stay_yr10:,.0f} vs Stay")
    c4.metric("Retirement @ Year 10", f"${retire_yr10:,.0f}")
    if crossover_month:
        c5.metric("Crossover Month", f"Month {crossover_month}",
                  delta="Go overtakes Stay")
    else:
        leader = "Stay" if stay_yr10 > go_yr10 else "Go"
        gap = abs(stay_yr10 - go_yr10)
        c5.metric("No Crossover", f"{leader} leads by ${gap:,.0f}")

    cost_of_going = stay_yr10 - go_yr10
    r1, r2, r3 = st.columns(3)
    r1.metric("Cost of Going (10-yr)", f"${cost_of_going:,.0f}",
              help="Stay NW minus Go NW at year 10 — the long-run price of the RV lifestyle")
    r2.metric("Mortgage P&I (computed)", f"${monthly_payment(params['mortgage_balance'], params['mortgage_rate'], params['mortgage_months_remaining']):,.0f}/mo")
    r3.metric("RV Loan Payment (computed)", f"${monthly_payment(params['rv_purchase_price'] - params['rv_down_payment'], params['rv_loan_apr'], params['rv_loan_months']):,.0f}/mo")

    # -----------------------------------------------------------------------
    # CHARTS
    # -----------------------------------------------------------------------
    st.subheader("Interactive Charts")

    def add_event_markers(fig, events_list, y_ref=None):
        """Add vertical dashed lines for each life event."""
        for ev in events_list:
            fig.add_vline(x=ev["Month"], line_dash="dot",
                          line_color="rgba(128,128,128,0.5)",
                          annotation_text=ev["Event"][:25],
                          annotation_textangle=-90,
                          annotation_font_size=8)

    tab1, tab2, tab3, tab4 = st.tabs(
        ["Net Worth", "Cash Balance", "Assets vs Debt", "Retirement"])

    with tab1:
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=df["Month"], y=df["Stay_NetWorth"],
                                   name="Stay", line=dict(color="steelblue", width=2.5)))
        fig1.add_trace(go.Scatter(x=df["Month"], y=df["Go_NetWorth"],
                                   name="Go", line=dict(color="darkorange", width=2.5)))
        fig1.add_trace(go.Scatter(x=df["Month"], y=df["Difference"],
                                   name="Difference (Go−Stay)",
                                   line=dict(color="gray", width=1, dash="dot"),
                                   yaxis="y2"))
        add_event_markers(fig1, events)
        fig1.update_layout(
            title="Net Worth Over Time",
            xaxis_title="Month", yaxis_title="Net Worth ($)",
            yaxis2=dict(title="Difference ($)", overlaying="y", side="right",
                        showgrid=False),
            hovermode="x unified", yaxis_tickformat="$,.0f",
            yaxis2_tickformat="$,.0f")
        st.plotly_chart(fig1, use_container_width=True)

    with tab2:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df["Month"],
                                   y=df["Stay_Cash"] + df["Stay_TaxableInv"],
                                   name="Stay Liquid (cash + investments)",
                                   line=dict(color="steelblue", width=2.5)))
        fig2.add_trace(go.Scatter(x=df["Month"],
                                   y=df["Go_Cash"] + df["Go_TaxableInv"],
                                   name="Go Liquid (cash + investments)",
                                   line=dict(color="darkorange", width=2.5)))
        fig2.add_hline(y=float(emergency_floor), line_dash="dash",
                        line_color="red", opacity=0.6,
                        annotation_text=f"Emergency Floor ${emergency_floor:,.0f}")
        add_event_markers(fig2, events)
        fig2.update_layout(title="Liquid Wealth Over Time (Cash + Taxable Investments)",
                            xaxis_title="Month", yaxis_title="Amount ($)",
                            hovermode="x unified", yaxis_tickformat="$,.0f")
        st.plotly_chart(fig2, use_container_width=True)

    with tab3:
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=df["Month"], y=df["Stay_Assets"],
                                   name="Stay Assets",
                                   fill="tozeroy", line=dict(color="steelblue")))
        fig3.add_trace(go.Scatter(x=df["Month"], y=-df["Stay_Debt"],
                                   name="Stay Debt (negative)",
                                   fill="tozeroy", line=dict(color="lightblue")))
        fig3.add_trace(go.Scatter(x=df["Month"], y=df["Go_Assets"],
                                   name="Go Assets",
                                   fill="tozeroy", line=dict(color="darkorange")))
        fig3.add_trace(go.Scatter(x=df["Month"], y=-df["Go_Debt"],
                                   name="Go Debt (negative)",
                                   fill="tozeroy", line=dict(color="moccasin")))
        add_event_markers(fig3, events)
        fig3.update_layout(title="Assets vs Debt Over Time",
                            xaxis_title="Month", yaxis_title="Value ($)",
                            hovermode="x unified", yaxis_tickformat="$,.0f")
        st.plotly_chart(fig3, use_container_width=True)

    with tab4:
        fig4 = go.Figure()
        # Stay and Go retirement are identical (same contribution rates) by default
        fig4.add_trace(go.Scatter(x=df["Month"], y=df["Stay_Retirement"],
                                   name="Retirement Balance",
                                   line=dict(color="green", width=2.5)))
        for milestone in [100_000, 250_000, 500_000, 1_000_000]:
            if milestone < retire_yr10 * 1.5:
                fig4.add_hline(y=milestone, line_dash="dash",
                                line_color="rgba(100,100,100,0.3)",
                                annotation_text=f"${milestone//1000}K",
                                annotation_font_size=10)
        fig4.update_layout(title="Retirement Balance Over Time",
                            xaxis_title="Month", yaxis_title="Balance ($)",
                            hovermode="x unified", yaxis_tickformat="$,.0f")
        st.plotly_chart(fig4, use_container_width=True)

    # -----------------------------------------------------------------------
    # MONTH-BY-MONTH TABLE
    # -----------------------------------------------------------------------
    st.subheader("Month-by-Month Comparison Table")

    year_options = ["All"] + [f"Year {i} ({today.year + i - 1})" for i in range(1, 11)]
    year_filter = st.selectbox("Filter by Simulation Year", year_options)

    display_df = df.copy()
    if year_filter != "All":
        yr_num = int(year_filter.split()[1])
        target_year = today.year + yr_num - 1
        display_df = display_df[display_df["Date"].apply(lambda d: d.year) == target_year]

    table_cols = {
        "Month": "Month",
        "Date": "Date",
        "Stay_Cash": "Stay: Cash",
        "Stay_Assets": "Stay: Assets",
        "Stay_Retirement": "Stay: Retirement",
        "Stay_Debt": "Stay: Debt",
        "Stay_NetWorth": "Stay: Net Worth",
        "Go_Cash": "Go: Cash",
        "Go_Assets": "Go: Assets",
        "Go_Retirement": "Go: Retirement",
        "Go_Debt": "Go: Debt",
        "Go_NetWorth": "Go: Net Worth",
        "Difference": "Difference (Go−Stay)",
    }
    table_df = display_df[list(table_cols.keys())].rename(columns=table_cols)

    money_cols = [c for c in table_df.columns if c not in ("Month", "Date")]
    styled = (table_df.style
              .format({c: "${:,.0f}" for c in money_cols})
              .applymap(lambda v: "color: green" if v >= 0 else "color: red",
                        subset=["Difference (Go−Stay)"]))

    st.dataframe(styled, use_container_width=True, height=420)

    csv_buf = StringIO()
    table_df.to_csv(csv_buf, index=False)
    st.download_button("Export Table to CSV", data=csv_buf.getvalue(),
                        file_name="stay_vs_go.csv", mime="text/csv")

    # -----------------------------------------------------------------------
    # EVENT LOG
    # -----------------------------------------------------------------------
    st.subheader("Life Event Log (Go Scenario)")
    if events:
        ev_df = pd.DataFrame(events)[["Month", "Date", "Event", "NetWorthAtEvent"]]
        ev_df["NetWorthAtEvent"] = ev_df["NetWorthAtEvent"].apply(lambda x: f"${x:,.0f}")
        st.dataframe(ev_df, use_container_width=True)
    else:
        st.info("No life events fired (all dates may fall beyond simulation window).")

    # -----------------------------------------------------------------------
    # METHODOLOGY EXPANDER
    # -----------------------------------------------------------------------
    with st.expander("Show Methodology & Assumptions"):
        st.markdown(f"""
## Methodology

### Simulation Structure
- **120-month (10-year)** simulation starting from {today.strftime('%B %d, %Y')}
- Both scenarios begin with **identical net worth**: ${starting_nw:,.0f}
  (${params['starting_cash']:,.0f} cash + ${params['starting_retirement']:,.0f} retirement +
  ${params['home_value'] - params['mortgage_balance']:,.0f} house equity +
  ${params['cx5_value'] - params['cx5_balance']:,.0f} CX-5 equity +
  ${params['aliner_value']:,.0f} Aliner)
- All calculations run independently per scenario each month

### Amortization Formula
All loans (mortgage, CX-5, truck, RV) use the standard fixed-payment formula:

**Payment = P × r(1+r)ⁿ / ((1+r)ⁿ − 1)**

where P = principal balance, r = APR/12 (monthly rate), n = remaining months.

Each month: *Interest = Balance × r; Principal = Payment − Interest; New Balance = Balance − Principal.*

### Income & Taxes
- Gross income grows at {params['income_growth_rate']*100:.1f}%/yr, stepping up every 12 months
- **Traditional 401(k):** employee contributions reduce federal and state taxable income
- **Roth 401(k):** contributions are post-tax; no reduction to taxable income
- FICA applies to full gross income
- IRS contribution limits (${params['irs_employee_limit']:,.0f} employee / ${params['irs_combined_limit']:,.0f} combined) reset each January 1

### Inflation
Operating costs inflate **monthly** at `annual_rate / 12`, compounded: `cost × (1 + rate/12)^month`.
Asset depreciation is applied geometrically, not adjusted for inflation.

### Investment Returns
- Liquid wealth above ${params['emergency_cash_floor']:,.0f} emergency floor earns **{params['taxable_return']*100:.1f}% taxable return**
- Cash at or below the floor earns **{params['cash_apy']*100:.1f}% savings APY**
- Retirement balance compounds monthly at `(1 + {params['retirement_return']*100:.1f}%/12)`

### Depreciation
Monthly geometric: `value × (1 − annual_rate/12)` — matches how vehicle values actually decline.

### Go Scenario Events
Events fire at the start of the month matching the input date (by month index from today).
Processing order each month: domicile change → truck purchase → Aliner sale → house sale → RV purchase.
If two events fall in the same month, they apply sequentially in that order.

### Net Worth Formula
**Net Worth = Liquid Wealth + Retirement Balance + Non-Cash Assets − Liabilities**

- Liquid wealth = cash + taxable investments (single pool; split at ${params['emergency_cash_floor']:,.0f} floor for reporting)
- Non-cash assets: house, vehicles, RV, Aliner (as applicable per scenario and date)
- Liabilities: outstanding loan balances

### Key Assumptions & Simplifications
- House sale price = appreciated value at sale date (unless overridden)
- CX-5 trade-in negative equity rolls into truck loan if balance > trade value
- RV down payment uses all available cash above emergency floor (if "use house proceeds" is checked)
- Emergency repair reserve builds at ${params['emergency_reserve_monthly']:,.0f}/mo until ${params['emergency_reserve_target']:,.0f} is reached
- Truck fuel cost applies only while RV is also owned (i.e., while actively RVing)
- Income tax rate switches from NC ({params['nc_state_rate']*100:.2f}%) to FL ({params['fl_state_rate']*100:.2f}%) in the month of the domicile change date
        """)


if __name__ == "__main__":
    main()
