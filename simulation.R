#!/usr/bin/env Rscript
# Stay vs. Go RV Financial Decision Simulator
# Replicates app.py simulate_stay() and simulate_go() logic month-by-month.
suppressPackageStartupMessages(library(yaml))
suppressPackageStartupMessages(library(dplyr))

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

monthly_payment <- function(principal, annual_rate, months) {
  if (principal <= 0 || months <= 0) return(0.0)
  if (annual_rate == 0) return(principal / months)
  r <- annual_rate / 12
  principal * r * (1 + r)^months / ((1 + r)^months - 1)
}

depreciate_mo <- function(value, annual_rate) {
  value * (1 - annual_rate / 12)
}

amortize_mo <- function(balance, annual_rate, fixed_payment) {
  # Returns list(interest, principal, new_balance)
  if (balance <= 0) return(list(interest = 0.0, principal = 0.0, new_balance = 0.0))
  r <- annual_rate / 12
  interest  <- balance * r
  principal <- min(max(fixed_payment - interest, 0.0), balance)
  list(interest = interest, principal = principal, new_balance = balance - principal)
}

days_to_month_idx <- function(days) {
  # Convert a days-from-today offset to a 0-based calendar month index,
  # matching Python's date_to_month_index(event_date, today) logic:
  #   (event_year - today_year)*12 + (event_month - today_month)
  today      <- Sys.Date()
  event_date <- today + days
  today_parts <- as.integer(format(today,      c("%Y", "%m")))
  ev_parts    <- as.integer(format(event_date, c("%Y", "%m")))
  idx <- (ev_parts[1] - today_parts[1]) * 12L + (ev_parts[2] - today_parts[2])
  as.integer(max(0L, idx))
}

fmt_dollar <- function(x) {
  paste0("$", formatC(round(x), format = "f", digits = 0, big.mark = ","))
}

# ---------------------------------------------------------------------------
# load_params: read YAML and flatten into a single named list
# ---------------------------------------------------------------------------

load_params <- function(path = "params.yaml") {
  raw <- yaml.load_file(path)

  p <- list()

  # personal
  p$gross_annual_income     <- raw$personal$gross_annual_income
  p$income_growth_rate      <- raw$personal$income_growth_rate
  p$starting_cash           <- raw$personal$starting_cash
  p$starting_retirement     <- raw$personal$starting_retirement

  # taxes
  p$nc_state_rate           <- raw$taxes$nc_state_rate
  p$fl_state_rate           <- raw$taxes$fl_state_rate
  p$federal_effective_rate  <- raw$taxes$federal_effective_rate
  p$fica_rate               <- raw$taxes$fica_rate

  # house
  p$home_value                   <- raw$house$home_value
  p$mortgage_balance             <- raw$house$mortgage_balance
  p$mortgage_rate                <- raw$house$mortgage_rate
  p$mortgage_months_remaining    <- raw$house$mortgage_months_remaining
  p$property_tax_monthly         <- raw$house$property_tax_monthly
  p$homeowners_insurance_monthly <- raw$house$homeowners_insurance_monthly
  p$home_appreciation_rate       <- raw$house$home_appreciation_rate
  p$home_maintenance_pct         <- raw$house$home_maintenance_pct
  p$home_utilities_monthly       <- raw$house$home_utilities_monthly
  p$groceries_monthly            <- raw$house$groceries_monthly
  p$house_selling_costs_pct      <- raw$house$house_selling_costs_pct

  # cx5
  p$cx5_value           <- raw$cx5$value
  p$cx5_balance         <- raw$cx5$balance
  p$cx5_monthly_payment <- raw$cx5$monthly_payment
  p$cx5_months_remaining <- raw$cx5$months_remaining
  p$cx5_depreciation_rate <- raw$cx5$depreciation_rate
  p$cx5_insurance_monthly <- raw$cx5$insurance_monthly
  p$cx5_fuel_monthly    <- raw$cx5$fuel_monthly
  p$cx5_rate            <- raw$cx5$loan_apr
  p$cx5_tradein_value   <- raw$cx5$tradein_value

  # aliner
  p$aliner_value            <- raw$aliner$value
  p$aliner_depreciation_rate <- raw$aliner$depreciation_rate

  # truck
  p$truck_purchase_price          <- raw$truck$purchase_price
  p$truck_down_payment            <- raw$truck$down_payment
  p$truck_loan_apr                <- raw$truck$loan_apr
  p$truck_loan_months             <- raw$truck$loan_months
  p$truck_depreciation_rate_early <- raw$truck$depreciation_rate_early
  p$truck_depreciation_rate_late  <- raw$truck$depreciation_rate_late
  p$truck_insurance_monthly       <- raw$truck$insurance_monthly
  p$truck_fuel_monthly            <- raw$truck$fuel_monthly
  p$truck_annual_maintenance      <- raw$truck$annual_maintenance

  # rv
  p$rv_purchase_price          <- raw$rv$purchase_price
  p$rv_loan_apr                <- raw$rv$loan_apr
  p$rv_loan_months             <- raw$rv$loan_months
  p$rv_depreciation_rate_early <- raw$rv$depreciation_rate_early
  p$rv_depreciation_rate_late  <- raw$rv$depreciation_rate_late
  p$rv_insurance_monthly       <- raw$rv$insurance_monthly
  p$rv_setup_costs             <- raw$rv$setup_costs
  p$rv_use_all_available_cash  <- isTRUE(raw$rv$use_all_available_cash)

  # rv_operating
  p$campground_fees_monthly   <- raw$rv_operating$campground_fees_monthly
  p$propane_monthly           <- raw$rv_operating$propane_monthly
  p$internet_monthly          <- raw$rv_operating$internet_monthly
  p$rv_maintenance_monthly    <- raw$rv_operating$maintenance_monthly
  p$domicile_mail_monthly     <- raw$rv_operating$domicile_mail_monthly
  p$emergency_reserve_monthly <- raw$rv_operating$emergency_reserve_monthly
  p$emergency_reserve_target  <- raw$rv_operating$emergency_reserve_target

  # retirement
  p$employee_contribution_pct <- raw$retirement$employee_contribution_pct
  p$employer_match_pct        <- raw$retirement$employer_match_pct
  p$retirement_return         <- raw$retirement$annual_return
  p$is_traditional            <- isTRUE(raw$retirement$is_traditional)
  p$irs_employee_limit        <- raw$retirement$irs_employee_limit
  p$irs_combined_limit        <- raw$retirement$irs_combined_limit

  # investments
  p$cash_apy             <- raw$investments$cash_apy
  p$taxable_return       <- raw$investments$taxable_return
  p$emergency_cash_floor <- raw$investments$emergency_cash_floor
  p$inflation_rate       <- raw$investments$inflation_rate

  # timeline: convert days to 0-based month indices
  tl <- raw$timeline
  p$truck_month      <- days_to_month_idx(tl$truck_purchase_days)
  p$aliner_sale_month <- days_to_month_idx(tl$aliner_sale_days)
  p$rv_month         <- days_to_month_idx(tl$rv_purchase_days)
  p$house_sale_month <- days_to_month_idx(tl$house_sale_days)
  p$domicile_month   <- days_to_month_idx(tl$domicile_change_days)

  p
}

# ---------------------------------------------------------------------------
# simulate: 120-month scenario simulator.
#   stay = TRUE  -> events disabled (house, CX-5, aliner kept; no truck/RV)
#   stay = FALSE -> all life events fire on schedule (Go scenario)
# Output columns are prefixed with "Stay_" or "Go_" so the two results can be
# joined on Month.
# ---------------------------------------------------------------------------

simulate <- function(p, stay = FALSE) {
  # In Stay mode, push every life-event month past the 120-month horizon so
  # the corresponding event branches never trigger. The rest of the loop is
  # identical to the Go scenario.
  if (stay) {
    p$truck_month       <- .Machine$integer.max
    p$aliner_sale_month <- .Machine$integer.max
    p$rv_month          <- .Machine$integer.max
    p$house_sale_month  <- .Machine$integer.max
    p$domicile_month    <- .Machine$integer.max
  }

  liquid     <- p$starting_cash
  retirement <- p$starting_retirement

  # House
  house_value          <- p$home_value
  mortgage_balance     <- p$mortgage_balance
  mortgage_rate        <- p$mortgage_rate
  mortgage_months_left <- p$mortgage_months_remaining
  mortgage_pmt         <- monthly_payment(mortgage_balance, mortgage_rate, mortgage_months_left)
  house_sold           <- FALSE

  # CX-5
  cx5_value       <- p$cx5_value
  cx5_balance     <- p$cx5_balance
  cx5_months_left <- p$cx5_months_remaining
  cx5_pmt         <- p$cx5_monthly_payment
  cx5_rate        <- p$cx5_rate
  cx5_active      <- TRUE

  # Aliner
  aliner_value <- p$aliner_value
  aliner_sold  <- FALSE

  # Truck
  truck_owned      <- FALSE
  truck_value      <- 0.0
  truck_balance    <- 0.0
  truck_pmt        <- 0.0
  truck_months_left <- 0L
  truck_rate       <- 0.0

  # RV
  rv_owned         <- FALSE
  rv_value         <- 0.0
  rv_balance       <- 0.0
  rv_pmt           <- 0.0
  rv_months_left   <- 0L
  rv_rate          <- 0.0
  rv_start_month   <- 0L   # 0-based month index when RV was purchased
  emerg_reserve_built <- 0.0

  # State tax rate (switches at domicile change)
  current_state_rate <- p$nc_state_rate
  domicile_changed   <- FALSE

  # YTD retirement tracking
  ytd_employee <- 0.0
  ytd_combined <- 0.0
  current_year <- as.integer(format(Sys.Date(), "%Y"))

  rows <- vector("list", 120)

  for (m in 1:120) {
    m0 <- m - 1L   # 0-based index — events fire when m0 == event_month_idx

    yr <- current_year + (m0 %/% 12L)

    # YTD reset
    if (m > 1L) {
      prev_yr <- current_year + ((m0 - 1L) %/% 12L)
      if (yr != prev_yr) {
        ytd_employee <- 0.0
        ytd_combined <- 0.0
      }
    }

    # ----------------------------------------------------------------
    # LIFE EVENTS (fire before monthly cash-flow, in fixed order)
    # ----------------------------------------------------------------

    # 1. Domicile change: switch to FL state income tax rate
    if (!domicile_changed && m0 == p$domicile_month) {
      current_state_rate <- p$fl_state_rate
      domicile_changed   <- TRUE
    }

    # 2. Truck purchase + CX-5 trade-in
    if (!truck_owned && m0 == p$truck_month) {
      truck_price    <- p$truck_purchase_price
      truck_down_pmt <- p$truck_down_payment
      cx5_trade      <- p$cx5_tradein_value

      # CX-5 negative equity rolls into truck loan
      if (cx5_balance > cx5_trade) {
        effective_financed <- truck_price - truck_down_pmt + (cx5_balance - cx5_trade)
      } else {
        effective_financed <- truck_price - truck_down_pmt - (cx5_trade - cx5_balance)
      }
      effective_financed <- max(effective_financed, 0.0)

      liquid <- liquid - truck_down_pmt

      truck_rate        <- p$truck_loan_apr
      truck_months_left <- as.integer(p$truck_loan_months)
      truck_balance     <- effective_financed
      truck_pmt         <- monthly_payment(truck_balance, truck_rate, truck_months_left)
      truck_value       <- truck_price
      truck_owned       <- TRUE

      # CX-5 disposed
      cx5_active  <- FALSE
      cx5_balance <- 0.0
      cx5_value   <- 0.0
    }

    # 3. Aliner sale: convert to cash at current depreciated value
    if (!aliner_sold && m0 == p$aliner_sale_month) {
      liquid       <- liquid + aliner_value
      aliner_sold  <- TRUE
      aliner_value <- 0.0
    }

    # 4. House sale
    if (!house_sold && m0 == p$house_sale_month) {
      sale_price    <- house_value   # use appreciated value (no override in base case)
      selling_costs <- sale_price * p$house_selling_costs_pct
      net_proceeds  <- sale_price - selling_costs - mortgage_balance
      liquid        <- liquid + net_proceeds
      house_sold    <- TRUE
      house_value   <- 0.0
      mortgage_balance <- 0.0
    }

    # 5. RV purchase
    if (!rv_owned && m0 == p$rv_month) {
      rv_price <- p$rv_purchase_price
      floor    <- p$emergency_cash_floor

      if (p$rv_use_all_available_cash) {
        rv_down <- max(0.0, min(liquid - floor, rv_price))
      } else {
        rv_down <- min(p$rv_down_payment, liquid)
      }

      liquid <- liquid - rv_down
      liquid <- liquid - p$rv_setup_costs

      rv_rate        <- p$rv_loan_apr
      rv_months_left <- as.integer(p$rv_loan_months)
      rv_balance     <- max(rv_price - rv_down, 0.0)
      rv_pmt         <- monthly_payment(rv_balance, rv_rate, rv_months_left)
      rv_value       <- rv_price
      rv_owned       <- TRUE
      rv_start_month <- m0
    }

    # ----------------------------------------------------------------
    # MONTHLY INCOME & TAXES
    # ----------------------------------------------------------------
    years_elapsed <- m0 %/% 12L
    gross_monthly <- p$gross_annual_income * (1 + p$income_growth_rate)^years_elapsed / 12

    desired_employee <- gross_monthly * p$employee_contribution_pct
    desired_employer <- gross_monthly * p$employer_match_pct
    actual_employee  <- min(desired_employee, max(0, p$irs_employee_limit - ytd_employee))
    room_combined    <- max(0, p$irs_combined_limit - ytd_combined - actual_employee)
    actual_employer  <- min(desired_employer, room_combined)
    ytd_employee <- ytd_employee + actual_employee
    ytd_combined <- ytd_combined + actual_employee + actual_employer

    taxable_income <- gross_monthly - (if (p$is_traditional) actual_employee else 0.0)
    federal_tax    <- taxable_income * p$federal_effective_rate
    state_tax      <- taxable_income * current_state_rate
    fica           <- gross_monthly * p$fica_rate
    post_tax_ret_deduction <- if (!p$is_traditional) actual_employee else 0.0
    net_income <- gross_monthly - federal_tax - state_tax - fica - post_tax_ret_deduction

    # ----------------------------------------------------------------
    # MONTHLY OUTFLOWS (inflation-adjusted)
    # ----------------------------------------------------------------
    inf <- (1 + p$inflation_rate / 12)^m0

    # Mortgage (while house not sold)
    if (!house_sold && mortgage_balance > 0 && mortgage_months_left > 0) {
      am <- amortize_mo(mortgage_balance, mortgage_rate, mortgage_pmt)
      mortgage_balance     <- am$new_balance
      mortgage_months_left <- mortgage_months_left - 1L
      mortgage_outflow     <- mortgage_pmt
    } else {
      mortgage_outflow <- 0.0
    }

    # CX-5 loan
    if (cx5_active && cx5_balance > 0 && cx5_months_left > 0) {
      am2 <- amortize_mo(cx5_balance, cx5_rate, cx5_pmt)
      cx5_balance      <- am2$new_balance
      cx5_months_left  <- cx5_months_left - 1L
      cx5_loan_outflow <- cx5_pmt
    } else {
      cx5_loan_outflow <- 0.0
    }

    cx5_insurance_out <- if (cx5_active) p$cx5_insurance_monthly * inf else 0.0
    cx5_fuel_out      <- if (cx5_active) p$cx5_fuel_monthly * inf else 0.0

    # House operating costs
    if (!house_sold) {
      prop_tax       <- p$property_tax_monthly * inf
      hoi            <- p$homeowners_insurance_monthly * inf
      home_util      <- p$home_utilities_monthly * inf
      home_maint     <- house_value * p$home_maintenance_pct / 12
      # Groceries: shift to RV bucket once RV is owned
      house_groceries <- if (rv_owned) 0.0 else p$groceries_monthly * inf
    } else {
      prop_tax        <- 0.0
      hoi             <- 0.0
      home_util       <- 0.0
      home_maint      <- 0.0
      house_groceries <- 0.0
    }

    # Truck loan + operating
    if (truck_owned && truck_balance > 0 && truck_months_left > 0) {
      am3 <- amortize_mo(truck_balance, truck_rate, truck_pmt)
      truck_balance     <- am3$new_balance
      truck_months_left <- truck_months_left - 1L
      truck_loan_out    <- truck_pmt
    } else {
      truck_loan_out <- 0.0
    }
    truck_ins  <- if (truck_owned) p$truck_insurance_monthly * inf else 0.0
    # Truck fuel only while actively RVing (both truck AND rv owned)
    truck_fuel <- if (truck_owned && rv_owned) p$truck_fuel_monthly * inf else 0.0
    truck_maint <- if (truck_owned) p$truck_annual_maintenance / 12 * inf else 0.0

    # RV loan + operating
    if (rv_owned && rv_balance > 0 && rv_months_left > 0) {
      am4 <- amortize_mo(rv_balance, rv_rate, rv_pmt)
      rv_balance     <- am4$new_balance
      rv_months_left <- rv_months_left - 1L
      rv_loan_out    <- rv_pmt
    } else {
      rv_loan_out <- 0.0
    }

    rv_ins         <- 0.0
    campground_out <- 0.0
    propane_out    <- 0.0
    internet_out   <- 0.0
    rv_maint_out   <- 0.0
    rv_groceries   <- 0.0
    domicile_mail  <- 0.0
    emerg_out      <- 0.0

    if (rv_owned) {
      rv_ins         <- p$rv_insurance_monthly * inf
      campground_out <- p$campground_fees_monthly * inf
      propane_out    <- p$propane_monthly * inf
      internet_out   <- p$internet_monthly * inf
      rv_maint_out   <- p$rv_maintenance_monthly * inf
      rv_groceries   <- p$groceries_monthly * inf
      domicile_mail  <- p$domicile_mail_monthly * inf
      # Emergency reserve buildup: $250/mo until $15K reached
      if (emerg_reserve_built < p$emergency_reserve_target) {
        emerg_out <- min(p$emergency_reserve_monthly,
                         p$emergency_reserve_target - emerg_reserve_built)
        emerg_reserve_built <- emerg_reserve_built + emerg_out
      } else {
        emerg_out <- 0.0
      }
    } else {
      rv_loan_out <- 0.0
      # "Homeless but not yet RVing": house sold but no RV yet — still need groceries
      if (house_sold) {
        rv_groceries <- p$groceries_monthly * inf
      }
    }

    total_outflow <- (mortgage_outflow + prop_tax + hoi + home_util + home_maint +
                      house_groceries +
                      cx5_loan_outflow + cx5_insurance_out + cx5_fuel_out +
                      truck_loan_out + truck_ins + truck_fuel + truck_maint +
                      rv_loan_out + rv_ins + campground_out + propane_out +
                      internet_out + rv_maint_out + rv_groceries +
                      domicile_mail + emerg_out)

    # ----------------------------------------------------------------
    # UPDATE LIQUID WEALTH
    # ----------------------------------------------------------------
    liquid <- liquid + net_income - total_outflow

    # Retirement compounding
    retirement <- retirement * (1 + p$retirement_return / 12) + actual_employee + actual_employer

    # Investment return on excess liquid
    floor <- p$emergency_cash_floor
    if (liquid > floor) {
      liquid <- liquid + (liquid - floor) * (p$taxable_return / 12) + floor * (p$cash_apy / 12)
    } else if (liquid > 0) {
      liquid <- liquid * (1 + p$cash_apy / 12)
    }

    # ----------------------------------------------------------------
    # ASSET DEPRECIATION
    # ----------------------------------------------------------------
    if (!house_sold) {
      house_value <- house_value * (1 + p$home_appreciation_rate / 12)
    }

    if (truck_owned) {
      yrs_truck <- m0 / 12
      t_dep <- if (yrs_truck < 5) p$truck_depreciation_rate_early else p$truck_depreciation_rate_late
      truck_value <- depreciate_mo(truck_value, t_dep)
    }

    if (rv_owned) {
      yrs_rv <- (m0 - rv_start_month) / 12
      r_dep  <- if (yrs_rv < 5) p$rv_depreciation_rate_early else p$rv_depreciation_rate_late
      rv_value <- depreciate_mo(rv_value, r_dep)
    }

    if (!aliner_sold) {
      aliner_value <- depreciate_mo(aliner_value, p$aliner_depreciation_rate)
    }

    if (cx5_active) {
      cx5_value <- depreciate_mo(cx5_value, p$cx5_depreciation_rate)
    }

    # ----------------------------------------------------------------
    # NET WORTH SNAPSHOT
    # ----------------------------------------------------------------
    cash_reported <- min(liquid, floor)
    taxable_inv   <- max(0.0, liquid - floor)

    assets <- ((if (!house_sold) house_value else 0.0) +
               (if (!aliner_sold) aliner_value else 0.0) +
               (if (cx5_active) cx5_value else 0.0) +
               (if (truck_owned) truck_value else 0.0) +
               (if (rv_owned) rv_value else 0.0))

    debt <- ((if (!house_sold) mortgage_balance else 0.0) +
             (if (cx5_active) cx5_balance else 0.0) +
             (if (truck_owned) truck_balance else 0.0) +
             (if (rv_owned) rv_balance else 0.0))

    net_worth <- liquid + retirement + assets - debt

    rows[[m]] <- list(
      Month           = m,
      Cash            = cash_reported,
      TaxableInv      = taxable_inv,
      Assets          = assets,
      Retirement      = retirement,
      Debt            = debt,
      NetWorth        = net_worth,
      HouseValue      = if (!house_sold) house_value else 0.0,
      MortgageBalance = if (!house_sold) mortgage_balance else 0.0,
      CX5Value        = if (cx5_active) cx5_value else 0.0,
      CX5Balance      = if (cx5_active) cx5_balance else 0.0,
      AlineValue      = if (!aliner_sold) aliner_value else 0.0,
      TruckValue      = if (truck_owned) truck_value else 0.0,
      TruckBalance    = if (truck_owned) truck_balance else 0.0,
      RVValue         = if (rv_owned) rv_value else 0.0,
      RVBalance       = if (rv_owned) rv_balance else 0.0,
      GrossMonthly    = gross_monthly,
      NetIncome       = net_income,
      TotalOutflow    = total_outflow,
      # Per-category cost breakdown
      mortgage_out    = mortgage_outflow,
      prop_tax        = prop_tax,
      hoi             = hoi,
      home_util       = home_util,
      home_maint      = home_maint,
      truck_loan_out  = truck_loan_out,
      truck_ins       = truck_ins,
      truck_fuel      = truck_fuel,
      truck_maint     = truck_maint,
      rv_loan_out     = rv_loan_out,
      rv_ins          = rv_ins,
      campground_out  = campground_out,
      propane_out     = propane_out,
      internet_out    = internet_out,
      rv_maint_out    = rv_maint_out,
      groceries       = rv_groceries + house_groceries,
      domicile_mail   = domicile_mail,
      emerg_reserve   = emerg_out
    )
  }

  out <- dplyr::bind_rows(rows)
  # Prefix scenario columns (everything except Month) so Stay/Go results can
  # be joined into a single wide table.
  prefix <- if (stay) "Stay_" else "Go_"
  names(out)[names(out) != "Month"] <- paste0(prefix, names(out)[names(out) != "Month"])
  out
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

args <- commandArgs(trailingOnly = TRUE)
yaml_path <- if (length(args) >= 1) args[1] else "params.yaml"

cat("Loading parameters from:", yaml_path, "\n")
p <- load_params(yaml_path)

cat("Running Stay simulation...\n")
stay_df <- simulate(p, stay = TRUE)

cat("Running Go simulation...\n")
go_df <- simulate(p, stay = FALSE)

# Merge on Month
df <- dplyr::inner_join(stay_df, go_df, by = "Month")
df <- dplyr::mutate(df, Difference = Go_NetWorth - Stay_NetWorth)

# ---------------------------------------------------------------------------
# (a) 10-year summary table
# ---------------------------------------------------------------------------
cat("\n")
cat("=======================================================================\n")
cat("  STAY vs. GO — 10-YEAR NET WORTH SUMMARY\n")
cat("=======================================================================\n")

milestone_months <- c(12, 24, 36, 60, 84, 120)
milestone_labels <- c("Yr 1", "Yr 2", "Yr 3", "Yr 5", "Yr 7", "Yr 10")

summary_tbl <- df %>%
  dplyr::filter(Month %in% milestone_months) %>%
  dplyr::mutate(
    Label = milestone_labels[match(Month, milestone_months)]
  ) %>%
  dplyr::select(Label, Month, Stay_NetWorth, Go_NetWorth, Difference)

# Print header
cat(sprintf("%-6s  %5s  %15s  %15s  %15s\n",
            "Period", "Month", "Stay NW", "Go NW", "Difference"))
cat(paste(rep("-", 62), collapse = ""), "\n")

for (i in seq_len(nrow(summary_tbl))) {
  row <- summary_tbl[i, ]
  cat(sprintf("%-6s  %5d  %15s  %15s  %15s\n",
              row$Label,
              row$Month,
              fmt_dollar(row$Stay_NetWorth),
              fmt_dollar(row$Go_NetWorth),
              fmt_dollar(row$Difference)))
}

# ---------------------------------------------------------------------------
# (b) Cost of going
# ---------------------------------------------------------------------------
stay_yr10 <- stay_df$Stay_NetWorth[120]
go_yr10   <- go_df$Go_NetWorth[120]
cost_of_going <- stay_yr10 - go_yr10

cat("\n")
cat("-----------------------------------------------------------------------\n")
cat(sprintf("  Cost of Going (Stay Yr10 - Go Yr10): %s\n", fmt_dollar(cost_of_going)))
cat("  (positive = Stay scenario ends richer; negative = Go scenario ends richer)\n")
cat("-----------------------------------------------------------------------\n")

# ---------------------------------------------------------------------------
# (c) Crossover month
# ---------------------------------------------------------------------------
crossover_month <- NA_integer_

for (i in 2:nrow(df)) {
  if ((df$Difference[i - 1] < 0) != (df$Difference[i] < 0)) {
    crossover_month <- df$Month[i]
    break
  }
}

cat("\n")
if (!is.na(crossover_month)) {
  cat(sprintf("  Crossover: Go first exceeds Stay in Month %d\n", crossover_month))
} else {
  leader <- if (stay_yr10 > go_yr10) "Stay" else "Go"
  gap    <- abs(stay_yr10 - go_yr10)
  cat(sprintf("  No crossover detected. %s leads throughout by up to %s.\n",
              leader, fmt_dollar(gap)))
}

# ---------------------------------------------------------------------------
# (d) Depreciation table: RAM 2500 vs CX-5 vs RV
# ---------------------------------------------------------------------------
cat("\n")
cat("=======================================================================\n")
cat("  DEPRECIATION COST OF OWNERSHIP (Year-by-Year)\n")
cat("=======================================================================\n")
cat(sprintf("%-4s  %14s  %12s  %18s  %12s  %17s  %14s\n",
            "Year", "RAM 2500 Dep", "CX-5 Dep", "Truck Premium vs CX5",
            "RV Dep", "Total Incremental", "Incremental/mo"))
cat(paste(rep("-", 97), collapse = ""), "\n")

tv_dep   <- p$truck_purchase_price
rv_dep_v <- p$rv_purchase_price
cx5_dep_v <- p$cx5_value

for (yr in 1:10) {
  t_rate  <- if (yr <= 5) p$truck_depreciation_rate_early else p$truck_depreciation_rate_late
  r_rate  <- if (yr <= 5) p$rv_depreciation_rate_early else p$rv_depreciation_rate_late
  c5_rate <- p$cx5_depreciation_rate

  tv_s    <- tv_dep
  rv_s    <- rv_dep_v
  cx5_s   <- cx5_dep_v

  for (mo in 1:12) {
    tv_dep    <- depreciate_mo(tv_dep,    t_rate)
    rv_dep_v  <- depreciate_mo(rv_dep_v,  r_rate)
    cx5_dep_v <- depreciate_mo(cx5_dep_v, c5_rate)
  }

  truck_dep_yr  <- tv_s - tv_dep
  rv_dep_yr     <- rv_s - rv_dep_v
  cx5_dep_yr    <- cx5_s - cx5_dep_v
  truck_premium <- truck_dep_yr - cx5_dep_yr
  total_incr    <- truck_premium + rv_dep_yr
  incr_per_mo   <- total_incr / 12

  cat(sprintf("%4d  %14s  %12s  %20s  %12s  %17s  %14s\n",
              yr,
              fmt_dollar(truck_dep_yr),
              fmt_dollar(cx5_dep_yr),
              fmt_dollar(truck_premium),
              fmt_dollar(rv_dep_yr),
              fmt_dollar(total_incr),
              fmt_dollar(incr_per_mo)))
}

total_truck_dep <- p$truck_purchase_price - tv_dep
total_rv_dep    <- p$rv_purchase_price - rv_dep_v
total_cx5_dep   <- p$cx5_value - cx5_dep_v

cat(paste(rep("-", 97), collapse = ""), "\n")
cat(sprintf("%-4s  %14s  %12s  %20s  %12s  %17s  %14s\n",
            "TOT",
            fmt_dollar(total_truck_dep),
            fmt_dollar(total_cx5_dep),
            fmt_dollar(total_truck_dep - total_cx5_dep),
            fmt_dollar(total_rv_dep),
            fmt_dollar((total_truck_dep - total_cx5_dep) + total_rv_dep),
            fmt_dollar(((total_truck_dep - total_cx5_dep) + total_rv_dep) / 120)))

# ---------------------------------------------------------------------------
# (e) Go cost breakdown for first full month after house sale
# ---------------------------------------------------------------------------
cat("\n")
cat("=======================================================================\n")
cat("  GO SCENARIO — COST BREAKDOWN FOR FIRST FULL MONTH AFTER HOUSE SALE\n")
cat("=======================================================================\n")

house_sale_m <- p$house_sale_month + 1L   # convert 0-based idx to 1-based Month label
first_full_month <- house_sale_m + 1L     # first FULL month after house sale

if (first_full_month > 120) {
  cat("  House sale falls too late in simulation window — no full month available.\n")
} else {
  breakdown_row <- go_df %>% dplyr::filter(Month == first_full_month)

  cost_cols <- paste0("Go_", c(
    "mortgage_out", "prop_tax", "hoi", "home_util", "home_maint",
    "truck_loan_out", "truck_ins", "truck_fuel", "truck_maint",
    "rv_loan_out", "rv_ins", "campground_out", "propane_out",
    "internet_out", "rv_maint_out", "groceries", "domicile_mail", "emerg_reserve"
  ))

  labels <- c(
    "Mortgage P&I", "Property Tax", "Homeowners Insurance", "Home Utilities", "Home Maintenance",
    "Truck Loan", "Truck Insurance", "Truck Fuel", "Truck Maintenance",
    "RV Loan", "RV Insurance", "Campground Fees", "Propane", "Internet",
    "RV Maintenance", "Groceries", "Domicile / Mail", "Emergency Reserve"
  )

  vals <- sapply(cost_cols, function(col) breakdown_row[[col]])
  total_cost <- sum(vals)

  # Build ranked data frame and print
  cost_df <- data.frame(
    Category = labels,
    Amount   = vals,
    Pct      = vals / total_cost * 100,
    stringsAsFactors = FALSE
  )
  cost_df <- cost_df[order(-cost_df$Amount), ]

  cat(sprintf("  Month %d (first full month post-house-sale)\n\n", first_full_month))
  cat(sprintf("  %-25s  %12s  %7s\n", "Category", "Amount", "% Total"))
  cat(paste(rep("-", 50), collapse = ""), "\n")

  for (i in seq_len(nrow(cost_df))) {
    r <- cost_df[i, ]
    if (r$Amount > 0) {
      cat(sprintf("  %-25s  %12s  %6.1f%%\n",
                  r$Category, fmt_dollar(r$Amount), r$Pct))
    }
  }

  cat(paste(rep("-", 50), collapse = ""), "\n")
  cat(sprintf("  %-25s  %12s  %6.1f%%\n", "TOTAL", fmt_dollar(total_cost), 100.0))
  cat(sprintf("\n  Net Income that month: %s\n",
              fmt_dollar(breakdown_row$Go_NetIncome)))
  cat(sprintf("  Monthly surplus (deficit): %s\n",
              fmt_dollar(breakdown_row$Go_NetIncome - total_cost)))
}

# ---------------------------------------------------------------------------
# Session info
# ---------------------------------------------------------------------------
cat("\n")
cat("=======================================================================\n")
cat("  SESSION INFO\n")
cat("=======================================================================\n")
yaml_ver  <- tryCatch(as.character(packageVersion("yaml")),  error = function(e) "unknown")
dplyr_ver <- tryCatch(as.character(packageVersion("dplyr")), error = function(e) "unknown")
r_ver     <- paste(R.version$major, R.version$minor, sep = ".")
cat(sprintf("  R version   : %s\n", r_ver))
cat(sprintf("  yaml version: %s\n", yaml_ver))
cat(sprintf("  dplyr version: %s\n", dplyr_ver))
cat("=======================================================================\n")
