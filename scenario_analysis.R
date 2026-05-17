#!/usr/bin/env Rscript
# scenario_analysis.R
# Sensitivity analysis: conditions where Go vs Stay differ by >$50k at 5 years

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
  library(tidyr)
  library(scales)
  library(patchwork)
})

# ---------------------------------------------------------------------------
# Financial math helpers (mirrors app.py)
# ---------------------------------------------------------------------------

monthly_payment <- function(principal, annual_rate, months) {
  if (principal <= 0 || months <= 0) return(0)
  if (annual_rate == 0) return(principal / months)
  r <- annual_rate / 12
  principal * r * (1 + r)^months / ((1 + r)^months - 1)
}

amortize_month <- function(balance, annual_rate, fixed_payment) {
  if (balance <= 0) return(list(interest=0, principal=0, new_balance=0))
  r <- annual_rate / 12
  interest  <- balance * r
  principal <- min(max(fixed_payment - interest, 0), balance)
  list(interest=interest, principal=principal, new_balance=balance - principal)
}

depreciate_monthly <- function(value, annual_rate) {
  value * (1 - annual_rate / 12)
}

# ---------------------------------------------------------------------------
# Default parameters (matches app.py sidebar defaults)
# ---------------------------------------------------------------------------

today <- as.Date("2026-05-17")

default_params <- list(
  today                        = today,
  starting_cash                = 30000,
  starting_retirement          = 60000,
  gross_annual_income          = 160000,
  income_growth_rate           = 0.03,
  nc_state_rate                = 0.0399,
  fl_state_rate                = 0.0,
  federal_effective_rate       = 0.18,
  fica_rate                    = 0.0765,
  # House
  home_value                   = 400000,
  mortgage_balance             = 342000,
  mortgage_rate                = 0.05,
  mortgage_months_remaining    = 174,
  property_tax_monthly         = 300,
  homeowners_insurance_monthly = 120,
  home_appreciation_rate       = 0.02,
  home_maintenance_pct         = 0.01,
  home_utilities_monthly       = 350,
  groceries_monthly            = 800,
  # CX-5
  cx5_fuel_monthly             = 140,
  cx5_balance                  = 20000,
  cx5_monthly_payment          = 500,
  cx5_months_remaining         = 36,
  cx5_value                    = 22000,
  cx5_depreciation_rate        = 0.12,
  cx5_insurance_monthly        = 90,
  cx5_rate                     = 0.06,
  # Aliner
  aliner_value                 = 8000,
  aliner_depreciation_rate     = 0.05,
  aliner_sale_date             = today + 44,
  # Events
  house_sale_date              = today + 90,
  house_sale_price_override    = FALSE,
  house_sale_price             = 400000,
  house_selling_costs_pct      = 0.07,
  cx5_tradein_value            = 20000,
  # Truck
  truck_purchase_date          = today + 30,
  truck_purchase_price         = 62000,
  truck_down_payment           = 0,
  truck_loan_apr               = 0.0,
  truck_loan_months            = 36,
  truck_depreciation_rate_early= 0.05,
  truck_depreciation_rate_late = 0.07,
  truck_insurance_monthly      = 130,
  truck_fuel_monthly           = 400,
  truck_annual_maintenance     = 2400,
  # RV
  rv_purchase_date             = today + 44,
  rv_purchase_price            = 88000,
  rv_down_payment              = 0,
  rv_use_all_available_cash    = TRUE,
  rv_loan_apr                  = 0.075,
  rv_loan_months               = 180,
  rv_depreciation_rate_early   = 0.08,
  rv_depreciation_rate_late    = 0.05,
  rv_insurance_monthly         = 200,
  rv_setup_costs               = 6000,
  campground_fees_monthly      = 1100,
  propane_monthly              = 80,
  internet_monthly             = 190,
  rv_maintenance_monthly       = 400,
  domicile_mail_monthly        = 25,
  emergency_reserve_monthly    = 250,
  emergency_reserve_target     = 15000,
  domicile_change_date         = today + 104,
  # Retirement
  employee_contribution_pct    = 0.10,
  employer_match_pct           = 0.04,
  retirement_return            = 0.08,
  is_traditional               = TRUE,
  irs_employee_limit           = 23500,
  irs_combined_limit           = 70000,
  # Investment
  cash_apy                     = 0.04,
  taxable_return               = 0.07,
  emergency_cash_floor         = 25000,
  inflation_rate               = 0.03
)

# ---------------------------------------------------------------------------
# date_to_month_index: 0-based month offset from start_date
# ---------------------------------------------------------------------------
date_to_month_index <- function(event_date, start_date) {
  dy <- as.integer(format(event_date, "%Y")) - as.integer(format(start_date, "%Y"))
  dm <- as.integer(format(event_date, "%m")) - as.integer(format(start_date, "%m"))
  max(0L, dy * 12L + dm)
}

# ---------------------------------------------------------------------------
# simulate_stay: returns net worth at each month (120 months)
# ---------------------------------------------------------------------------
simulate_stay <- function(p) {
  liquid     <- p$starting_cash
  retirement <- p$starting_retirement

  house_value          <- p$home_value
  mortgage_balance     <- p$mortgage_balance
  mortgage_months_left <- p$mortgage_months_remaining
  mortgage_pmt         <- monthly_payment(mortgage_balance, p$mortgage_rate,
                                          mortgage_months_left)
  cx5_value      <- p$cx5_value
  cx5_balance    <- p$cx5_balance
  cx5_months_left<- p$cx5_months_remaining
  cx5_pmt        <- p$cx5_monthly_payment
  aliner_value   <- p$aliner_value

  ytd_employee <- 0; ytd_combined <- 0
  current_year <- as.integer(format(p$today, "%Y"))
  nw <- numeric(120)

  for (m in 0:119) {
    yr <- as.integer(format(p$today, "%Y")) + (as.integer(format(p$today, "%m")) - 1 + m) %/% 12
    mo <- (as.integer(format(p$today, "%m")) - 1 + m) %% 12 + 1
    if (yr != current_year) {
      current_year <- yr; ytd_employee <- 0; ytd_combined <- 0
    }

    years_elapsed <- m %/% 12
    gross_monthly <- p$gross_annual_income * (1 + p$income_growth_rate)^years_elapsed / 12

    desired_employee <- gross_monthly * p$employee_contribution_pct
    desired_employer <- gross_monthly * p$employer_match_pct
    actual_employee  <- min(desired_employee, max(0, p$irs_employee_limit - ytd_employee))
    room_combined    <- max(0, p$irs_combined_limit - ytd_combined - actual_employee)
    actual_employer  <- min(desired_employer, room_combined)
    ytd_employee     <- ytd_employee + actual_employee
    ytd_combined     <- ytd_combined + actual_employee + actual_employer

    taxable_income <- gross_monthly - if (p$is_traditional) actual_employee else 0
    federal_tax    <- taxable_income * p$federal_effective_rate
    state_tax      <- taxable_income * p$nc_state_rate
    fica           <- gross_monthly * p$fica_rate
    post_tax_ret   <- if (!p$is_traditional) actual_employee else 0
    net_income     <- gross_monthly - federal_tax - state_tax - fica - post_tax_ret

    inf <- (1 + p$inflation_rate / 12)^m

    if (mortgage_months_left > 0 && mortgage_balance > 0) {
      res <- amortize_month(mortgage_balance, p$mortgage_rate, mortgage_pmt)
      mortgage_balance     <- res$new_balance
      mortgage_months_left <- mortgage_months_left - 1
      mortgage_outflow     <- mortgage_pmt
    } else mortgage_outflow <- 0

    if (cx5_balance > 0 && cx5_months_left > 0) {
      res <- amortize_month(cx5_balance, p$cx5_rate, cx5_pmt)
      cx5_balance     <- res$new_balance
      cx5_months_left <- cx5_months_left - 1
      cx5_loan_outflow<- cx5_pmt
    } else cx5_loan_outflow <- 0

    property_tax     <- p$property_tax_monthly * inf
    hoi              <- p$homeowners_insurance_monthly * inf
    utilities        <- p$home_utilities_monthly * inf
    groceries        <- p$groceries_monthly * inf
    fuel_cx5         <- p$cx5_fuel_monthly * inf
    cx5_insurance    <- p$cx5_insurance_monthly * inf
    home_maintenance <- house_value * p$home_maintenance_pct / 12

    total_outflow <- (mortgage_outflow + property_tax + hoi + utilities + groceries +
                      fuel_cx5 + cx5_insurance + home_maintenance + cx5_loan_outflow)

    liquid     <- liquid + net_income - total_outflow
    retirement <- retirement * (1 + p$retirement_return / 12) + actual_employee + actual_employer

    floor <- p$emergency_cash_floor
    if (liquid > floor) {
      liquid <- liquid + (liquid - floor) * (p$taxable_return / 12) + floor * (p$cash_apy / 12)
    } else if (liquid > 0) {
      liquid <- liquid * (1 + p$cash_apy / 12)
    }

    house_value  <- house_value  * (1 + p$home_appreciation_rate / 12)
    cx5_value    <- depreciate_monthly(cx5_value,   p$cx5_depreciation_rate)
    aliner_value <- depreciate_monthly(aliner_value, p$aliner_depreciation_rate)

    assets <- house_value + cx5_value + aliner_value
    debt   <- mortgage_balance + cx5_balance
    nw[m + 1] <- liquid + retirement + assets - debt
  }
  nw
}

# ---------------------------------------------------------------------------
# simulate_go: returns net worth at each month (120 months)
# ---------------------------------------------------------------------------
simulate_go <- function(p) {
  liquid     <- p$starting_cash
  retirement <- p$starting_retirement

  house_value          <- p$home_value
  mortgage_balance     <- p$mortgage_balance
  mortgage_months_left <- p$mortgage_months_remaining
  mortgage_pmt         <- monthly_payment(mortgage_balance, p$mortgage_rate,
                                          mortgage_months_left)
  house_sold <- FALSE

  cx5_value      <- p$cx5_value
  cx5_balance    <- p$cx5_balance
  cx5_months_left<- p$cx5_months_remaining
  cx5_pmt        <- p$cx5_monthly_payment
  cx5_active     <- TRUE

  aliner_value <- p$aliner_value
  aliner_sold  <- FALSE

  truck_owned <- FALSE; truck_value <- 0; truck_balance <- 0
  truck_pmt <- 0; truck_months_left <- 0; truck_rate <- 0

  rv_owned <- FALSE; rv_value <- 0; rv_balance <- 0
  rv_pmt <- 0; rv_months_left <- 0; rv_rate <- 0; rv_start_month <- 0
  emergency_reserve_built <- 0

  truck_month   <- date_to_month_index(p$truck_purchase_date,  p$today)
  aliner_month  <- date_to_month_index(p$aliner_sale_date,     p$today)
  house_month   <- date_to_month_index(p$house_sale_date,      p$today)
  rv_month_idx  <- date_to_month_index(p$rv_purchase_date,     p$today)
  domicile_month<- date_to_month_index(p$domicile_change_date, p$today)

  current_state_rate <- p$nc_state_rate
  domicile_changed   <- FALSE

  ytd_employee <- 0; ytd_combined <- 0
  current_year <- as.integer(format(p$today, "%Y"))
  nw <- numeric(120)

  for (m in 0:119) {
    yr <- as.integer(format(p$today, "%Y")) + (as.integer(format(p$today, "%m")) - 1 + m) %/% 12
    if (yr != current_year) {
      current_year <- yr; ytd_employee <- 0; ytd_combined <- 0
    }

    # --- Life events ---
    if (!domicile_changed && m == domicile_month) {
      current_state_rate <- p$fl_state_rate
      domicile_changed   <- TRUE
    }

    if (!truck_owned && m == truck_month) {
      truck_price   <- p$truck_purchase_price
      cx5_trade     <- p$cx5_tradein_value
      if (cx5_balance > cx5_trade) {
        eff_financed <- truck_price - p$truck_down_payment + (cx5_balance - cx5_trade)
      } else {
        eff_financed <- truck_price - p$truck_down_payment - (cx5_trade - cx5_balance)
      }
      eff_financed  <- max(eff_financed, 0)
      liquid        <- liquid - p$truck_down_payment
      truck_rate    <- p$truck_loan_apr
      truck_months_left <- p$truck_loan_months
      truck_balance <- eff_financed
      truck_pmt     <- monthly_payment(truck_balance, truck_rate, truck_months_left)
      truck_value   <- truck_price
      truck_owned   <- TRUE
      cx5_active    <- FALSE; cx5_balance <- 0; cx5_value <- 0
    }

    if (!aliner_sold && m == aliner_month) {
      liquid      <- liquid + aliner_value
      aliner_sold <- TRUE; aliner_value <- 0
    }

    if (!house_sold && m == house_month) {
      sale_price <- if (isTRUE(p$house_sale_price_override) && !is.null(p$house_sale_price))
                      p$house_sale_price else house_value
      selling_costs <- sale_price * p$house_selling_costs_pct
      net_proceeds  <- sale_price - selling_costs - mortgage_balance
      liquid        <- liquid + net_proceeds
      house_sold    <- TRUE; house_value <- 0; mortgage_balance <- 0
    }

    if (!rv_owned && m == rv_month_idx) {
      rv_price <- p$rv_purchase_price
      if (isTRUE(p$rv_use_all_available_cash)) {
        rv_down <- max(0, min(liquid - p$emergency_cash_floor, rv_price))
      } else {
        rv_down <- min(p$rv_down_payment, liquid)
      }
      liquid       <- liquid - rv_down - p$rv_setup_costs
      rv_rate      <- p$rv_loan_apr
      rv_months_left <- p$rv_loan_months
      rv_balance   <- max(rv_price - rv_down, 0)
      rv_pmt       <- monthly_payment(rv_balance, rv_rate, rv_months_left)
      rv_value     <- rv_price
      rv_owned     <- TRUE
      rv_start_month <- m
    }

    # --- Income ---
    years_elapsed <- m %/% 12
    gross_monthly <- p$gross_annual_income * (1 + p$income_growth_rate)^years_elapsed / 12
    desired_employee <- gross_monthly * p$employee_contribution_pct
    desired_employer <- gross_monthly * p$employer_match_pct
    actual_employee  <- min(desired_employee, max(0, p$irs_employee_limit - ytd_employee))
    room_combined    <- max(0, p$irs_combined_limit - ytd_combined - actual_employee)
    actual_employer  <- min(desired_employer, room_combined)
    ytd_employee <- ytd_employee + actual_employee
    ytd_combined <- ytd_combined + actual_employee + actual_employer

    taxable_income <- gross_monthly - if (p$is_traditional) actual_employee else 0
    state_tax      <- taxable_income * current_state_rate
    federal_tax    <- taxable_income * p$federal_effective_rate
    fica           <- gross_monthly * p$fica_rate
    post_tax_ret   <- if (!p$is_traditional) actual_employee else 0
    net_income     <- gross_monthly - federal_tax - state_tax - fica - post_tax_ret

    # --- Outflows ---
    inf <- (1 + p$inflation_rate / 12)^m

    if (!house_sold && mortgage_balance > 0 && mortgage_months_left > 0) {
      res <- amortize_month(mortgage_balance, p$mortgage_rate, mortgage_pmt)
      mortgage_balance     <- res$new_balance
      mortgage_months_left <- mortgage_months_left - 1
      mortgage_outflow     <- mortgage_pmt
    } else mortgage_outflow <- 0

    if (cx5_active && cx5_balance > 0 && cx5_months_left > 0) {
      res <- amortize_month(cx5_balance, p$cx5_rate, cx5_pmt)
      cx5_balance     <- res$new_balance
      cx5_months_left <- cx5_months_left - 1
      cx5_loan_outflow<- cx5_pmt
    } else cx5_loan_outflow <- 0

    cx5_ins_out  <- if (cx5_active) p$cx5_insurance_monthly * inf else 0
    cx5_fuel_out <- if (cx5_active) p$cx5_fuel_monthly * inf else 0

    if (!house_sold) {
      property_tax   <- p$property_tax_monthly * inf
      hoi            <- p$homeowners_insurance_monthly * inf
      home_utilities <- p$home_utilities_monthly * inf
      home_maint     <- house_value * p$home_maintenance_pct / 12
      house_groceries<- if (!rv_owned) p$groceries_monthly * inf else 0
    } else {
      property_tax <- hoi <- home_utilities <- home_maint <- house_groceries <- 0
    }

    if (truck_owned && truck_balance > 0 && truck_months_left > 0) {
      res <- amortize_month(truck_balance, truck_rate, truck_pmt)
      truck_balance     <- res$new_balance
      truck_months_left <- truck_months_left - 1
      truck_loan_out    <- truck_pmt
    } else truck_loan_out <- 0
    truck_ins_out  <- if (truck_owned) p$truck_insurance_monthly * inf else 0
    truck_fuel_out <- if (truck_owned && rv_owned) p$truck_fuel_monthly * inf else 0
    truck_maint_out<- if (truck_owned) p$truck_annual_maintenance / 12 * inf else 0

    if (rv_owned && rv_balance > 0 && rv_months_left > 0) {
      res <- amortize_month(rv_balance, rv_rate, rv_pmt)
      rv_balance     <- res$new_balance
      rv_months_left <- rv_months_left - 1
      rv_loan_out    <- rv_pmt
    } else rv_loan_out <- 0

    if (rv_owned) {
      rv_ins_out      <- p$rv_insurance_monthly * inf
      campground_out  <- p$campground_fees_monthly * inf
      propane_out     <- p$propane_monthly * inf
      internet_out    <- p$internet_monthly * inf
      rv_maint_out    <- p$rv_maintenance_monthly * inf
      rv_groceries    <- p$groceries_monthly * inf
      domicile_out    <- p$domicile_mail_monthly * inf
      if (emergency_reserve_built < p$emergency_reserve_target) {
        emerg_out <- min(p$emergency_reserve_monthly,
                         p$emergency_reserve_target - emergency_reserve_built)
        emergency_reserve_built <- emergency_reserve_built + emerg_out
      } else emerg_out <- 0
      rv_operating <- (rv_ins_out + campground_out + propane_out + internet_out +
                       rv_maint_out + rv_groceries + domicile_out + emerg_out)
    } else {
      rv_loan_out  <- 0; rv_operating <- 0
      if (!house_sold) rv_operating <- 0 else rv_operating <- p$groceries_monthly * inf
    }

    total_outflow <- (mortgage_outflow + property_tax + hoi + home_utilities + home_maint +
                      house_groceries + cx5_loan_outflow + cx5_ins_out + cx5_fuel_out +
                      truck_loan_out + truck_ins_out + truck_fuel_out + truck_maint_out +
                      rv_loan_out + rv_operating)

    liquid     <- liquid + net_income - total_outflow
    retirement <- retirement * (1 + p$retirement_return / 12) + actual_employee + actual_employer

    floor <- p$emergency_cash_floor
    if (liquid > floor) {
      liquid <- liquid + (liquid - floor) * (p$taxable_return / 12) + floor * (p$cash_apy / 12)
    } else if (liquid > 0) {
      liquid <- liquid * (1 + p$cash_apy / 12)
    }

    if (!house_sold)
      house_value <- house_value * (1 + p$home_appreciation_rate / 12)
    if (truck_owned) {
      tdep <- if (m / 12 < 5) p$truck_depreciation_rate_early else p$truck_depreciation_rate_late
      truck_value <- depreciate_monthly(truck_value, tdep)
    }
    if (rv_owned) {
      rdep <- if ((m - rv_start_month) / 12 < 5) p$rv_depreciation_rate_early else p$rv_depreciation_rate_late
      rv_value <- depreciate_monthly(rv_value, rdep)
    }
    if (!aliner_sold) aliner_value <- depreciate_monthly(aliner_value, p$aliner_depreciation_rate)
    if (cx5_active)   cx5_value    <- depreciate_monthly(cx5_value,   p$cx5_depreciation_rate)

    assets <- ((if (!house_sold) house_value else 0) + (if (!aliner_sold) aliner_value else 0) +
               (if (cx5_active) cx5_value else 0)    + (if (truck_owned) truck_value else 0) +
               (if (rv_owned) rv_value else 0))
    debt   <- ((if (!house_sold) mortgage_balance else 0) + (if (cx5_active) cx5_balance else 0) +
               (if (truck_owned) truck_balance else 0)    + (if (rv_owned) rv_balance else 0))
    nw[m + 1] <- liquid + retirement + assets - debt
  }
  nw
}

# ---------------------------------------------------------------------------
# Helper: run both sims with a modified parameter, return nw_diff at month 60
# ---------------------------------------------------------------------------
nw_diff_at_60 <- function(p) {
  stay_nw <- simulate_stay(p)[60]
  go_nw   <- simulate_go(p)[60]
  go_nw - stay_nw
}

# Baseline
base_diff <- nw_diff_at_60(default_params)
cat(sprintf("Baseline Go−Stay at month 60: $%+.0f\n", base_diff))
cat(sprintf("  Stay NW: $%.0f   Go NW: $%.0f\n\n",
            simulate_stay(default_params)[60],
            simulate_go(default_params)[60]))

# ---------------------------------------------------------------------------
# 1. One-way sensitivity  (tornado)
# ---------------------------------------------------------------------------
sweep_param <- function(pname, values, label, fmt=scales::dollar) {
  diffs <- sapply(values, function(v) {
    p <- default_params; p[[pname]] <- v; nw_diff_at_60(p)
  })
  data.frame(param=label, value=values, diff=diffs, stringsAsFactors=FALSE)
}

tornado_data <- bind_rows(
  sweep_param("rv_purchase_price",        seq(50000, 130000, 5000), "RV purchase price"),
  sweep_param("truck_purchase_price",     seq(35000,  90000, 5000), "Truck purchase price"),
  sweep_param("home_appreciation_rate",   seq(0.00,   0.07, 0.005), "House appreciation rate"),
  sweep_param("rv_loan_apr",              seq(0.04,   0.13, 0.005), "RV loan APR"),
  sweep_param("campground_fees_monthly",  seq(500,   2000,  100),   "Campground fees/mo"),
  sweep_param("rv_depreciation_rate_early", seq(0.04, 0.14, 0.01), "RV depreciation (early)")
)

# Range per parameter (for tornado ordering)
tornado_summary <- tornado_data %>%
  group_by(param) %>%
  summarise(lo=min(diff), hi=max(diff), span=hi-lo, .groups="drop") %>%
  arrange(span)

# ── Plot 1: Tornado chart ────────────────────────────────────────────────────
p1 <- ggplot(tornado_summary,
             aes(y=reorder(param, span))) +
  geom_segment(aes(x=lo, xend=hi,
                   yend=reorder(param, span)),
               linewidth=8, color="#4C72B0", alpha=0.7) +
  geom_vline(xintercept=base_diff, linetype="dashed", color="black", linewidth=0.7) +
  geom_vline(xintercept=c(-50000, 50000), linetype="dotted", color="firebrick", linewidth=0.8) +
  scale_x_continuous(labels=dollar, breaks=seq(-200000, 200000, 50000)) +
  labs(title="One-way sensitivity: Go − Stay net worth at 5 years",
       subtitle="Red dotted lines = ±$50k threshold | Dashed = baseline",
       x="Go − Stay net worth difference ($)", y=NULL) +
  theme_minimal(base_size=13) +
  theme(panel.grid.major.y=element_blank())

# ── Plot 2: Line traces per parameter ───────────────────────────────────────
tornado_data_norm <- tornado_data %>%
  group_by(param) %>%
  mutate(pct = (value - min(value)) / (max(value) - min(value)))

p2 <- ggplot(tornado_data, aes(x=value, y=diff, color=param)) +
  geom_line(linewidth=1) +
  geom_hline(yintercept=c(-50000, 50000), linetype="dotted", color="firebrick") +
  geom_hline(yintercept=0, linetype="dashed") +
  facet_wrap(~param, scales="free_x", ncol=2) +
  scale_y_continuous(labels=dollar) +
  scale_x_continuous(labels=function(x) {
    ifelse(abs(x) >= 1000, paste0("$", x/1000, "k"), x)
  }) +
  labs(title="Go − Stay difference vs. each parameter (others at default)",
       subtitle="Above 0 = Go is better; red lines = ±$50k",
       x=NULL, y="Go − Stay ($)") +
  theme_minimal(base_size=11) +
  theme(legend.position="none", strip.text=element_text(face="bold"))

# ---------------------------------------------------------------------------
# 2. Two-way heatmaps
# ---------------------------------------------------------------------------
make_heatmap_data <- function(p1name, p1vals, p2name, p2vals) {
  expand.grid(p1=p1vals, p2=p2vals) %>%
    mutate(diff = mapply(function(v1, v2) {
      p <- default_params; p[[p1name]] <- v1; p[[p2name]] <- v2
      nw_diff_at_60(p)
    }, p1, p2))
}

cat("Computing heatmap 1: RV price × House appreciation...\n")
h1 <- make_heatmap_data(
  "rv_purchase_price",      seq(55000, 125000, 5000),
  "home_appreciation_rate", seq(0.00,  0.06,   0.005)
)

cat("Computing heatmap 2: Campground fees × RV loan APR...\n")
h2 <- make_heatmap_data(
  "campground_fees_monthly", seq(600,  1800, 100),
  "rv_loan_apr",             seq(0.04, 0.12, 0.005)
)

cat("Computing heatmap 3: RV price × Truck price...\n")
h3 <- make_heatmap_data(
  "rv_purchase_price",    seq(55000, 125000, 5000),
  "truck_purchase_price", seq(35000,  90000, 5000)
)

heatmap_plot <- function(df, x_label, y_label, title,
                         x_fmt=dollar, y_fmt=dollar) {
  limit <- max(abs(df$diff), 50000)
  ggplot(df, aes(x=p1, y=p2, fill=diff)) +
    geom_tile() +
    geom_contour(aes(z=diff), breaks=c(-50000, 0, 50000),
                 color="white", linewidth=0.6) +
    scale_fill_gradient2(low="#d73027", mid="white", high="#1a9641",
                         midpoint=0, limits=c(-limit, limit),
                         labels=dollar, name="Go−Stay ($)") +
    scale_x_continuous(labels=x_fmt) +
    scale_y_continuous(labels=y_fmt) +
    labs(title=title,
         subtitle="Green = Go better | Red = Stay better | White contours = $0 and ±$50k",
         x=x_label, y=y_label) +
    theme_minimal(base_size=12)
}

ph1 <- heatmap_plot(h1,
  "RV purchase price ($)", "House appreciation rate",
  "RV price × House appreciation",
  y_fmt=scales::percent)

ph2 <- heatmap_plot(h2,
  "Campground fees/mo ($)", "RV loan APR",
  "Campground fees × RV loan APR",
  x_fmt=dollar, y_fmt=scales::percent)

ph3 <- heatmap_plot(h3,
  "RV purchase price ($)", "Truck purchase price ($)",
  "RV price × Truck price")

# ---------------------------------------------------------------------------
# 3. Identify threshold crossings  (where diff crosses ±$50k)
# ---------------------------------------------------------------------------
cat("\n=== Threshold crossings (>$50k advantage at 5 years) ===\n\n")

threshold_report <- function(pname, vals, label, fmt_fn=function(x) x) {
  diffs <- sapply(vals, function(v) {
    p <- default_params; p[[pname]] <- v; nw_diff_at_60(p)
  })
  go_better  <- vals[diffs >  50000]
  stay_better<- vals[diffs < -50000]
  cat(sprintf("%-35s  Go>$50k when: %s\n                                     Stay>$50k when: %s\n",
    label,
    if (length(go_better))   paste(sapply(go_better,   fmt_fn), collapse=", ") else "never",
    if (length(stay_better)) paste(sapply(stay_better, fmt_fn), collapse=", ") else "never"))
}

threshold_report("rv_purchase_price",
  seq(50000,130000,5000), "RV price",
  function(x) sprintf("$%.0fk", x/1000))
threshold_report("truck_purchase_price",
  seq(35000,90000,5000),  "Truck price",
  function(x) sprintf("$%.0fk", x/1000))
threshold_report("home_appreciation_rate",
  seq(0, 0.07, 0.005),    "House apprec. rate",
  function(x) sprintf("%.1f%%", x*100))
threshold_report("rv_loan_apr",
  seq(0.04, 0.13, 0.005), "RV loan APR",
  function(x) sprintf("%.1f%%", x*100))
threshold_report("campground_fees_monthly",
  seq(500, 2000, 100),    "Campground fees/mo",
  function(x) sprintf("$%.0f", x))
threshold_report("rv_depreciation_rate_early",
  seq(0.04, 0.14, 0.01),  "RV depreciation (early)",
  function(x) sprintf("%.0f%%", x*100))

# ---------------------------------------------------------------------------
# Save plots
# ---------------------------------------------------------------------------
out_dir <- "/home/user/life-decision"

ggsave(file.path(out_dir, "fig1_tornado.png"),   p1,  width=10, height=5,  dpi=150)
ggsave(file.path(out_dir, "fig2_sensitivity.png"),p2, width=12, height=10, dpi=150)
ggsave(file.path(out_dir, "fig3_heatmap_rv_apprec.png"), ph1, width=9, height=6, dpi=150)
ggsave(file.path(out_dir, "fig4_heatmap_camp_apr.png"),  ph2, width=9, height=6, dpi=150)
ggsave(file.path(out_dir, "fig5_heatmap_rv_truck.png"),  ph3, width=9, height=6, dpi=150)

cat("\nPlots saved.\n")

# ---------------------------------------------------------------------------
# Supplementary: extended ranges + combination scenarios
# ---------------------------------------------------------------------------
cat("\n=== What would it take for Go to win? ===\n\n")

# Sweep house appreciation into negative territory + very cheap RV
cat("Computing heatmap 6: RV price × House appreciation (extended into negative)...\n")
h6 <- make_heatmap_data(
  "rv_purchase_price",      seq(30000, 120000, 5000),
  "home_appreciation_rate", seq(-0.08,  0.04,  0.005)
)

ph6 <- heatmap_plot(h6,
  "RV purchase price ($)", "House appreciation rate (negative = declining market)",
  "When can Go win? — RV price × House appreciation (extended range)",
  y_fmt=scales::percent)

ggsave(file.path(out_dir, "fig6_heatmap_rv_negapprec.png"), ph6, width=10, height=6, dpi=150)

# What house apprec rate is needed for Go to break even, as a function of RV price?
cat("Computing break-even curve...\n")
rv_prices  <- seq(30000, 110000, 5000)
apprec_vals<- seq(-0.10, 0.06, 0.001)
break_even <- data.frame(rv_price=rv_prices, break_even_apprec=NA_real_)
for (i in seq_along(rv_prices)) {
  diffs <- sapply(apprec_vals, function(a) {
    p <- default_params
    p$rv_purchase_price       <- rv_prices[i]
    p$home_appreciation_rate  <- a
    nw_diff_at_60(p)
  })
  # Find first value where diff goes positive (Go starts winning)
  idx <- which(diffs > 0)
  break_even$break_even_apprec[i] <- if (length(idx)) apprec_vals[min(idx)] else NA
}

p_breakeven <- ggplot(break_even %>% filter(!is.na(break_even_apprec)),
       aes(x=rv_price/1000, y=break_even_apprec*100)) +
  geom_line(color="#1a9641", linewidth=1.5) +
  geom_point(color="#1a9641", size=2) +
  geom_hline(yintercept=0, linetype="dashed") +
  scale_x_continuous(labels=function(x) paste0("$",x,"k")) +
  scale_y_continuous(labels=function(y) paste0(y,"%")) +
  labs(
    title="Break-even house appreciation rate for 'Go' to match 'Stay' at 5 years",
    subtitle="Go wins only when house appreciation is below the curve — requires sustained decline",
    x="RV purchase price", y="Break-even house appreciation rate"
  ) +
  theme_minimal(base_size=13)

ggsave(file.path(out_dir, "fig7_breakeven_curve.png"), p_breakeven, width=9, height=5, dpi=150)

# Report break-even appreciation needed per RV price
cat("\nRV price → house appreciation rate needed for Go to break even:\n")
for (i in seq_along(rv_prices)) {
  be <- break_even$break_even_apprec[i]
  cat(sprintf("  RV $%3.0fk: break-even apprec = %s\n",
    rv_prices[i]/1000,
    if (is.na(be)) "never (within -10% to +6%)" else sprintf("%+.1f%%/yr", be*100)))
}

# Three extreme "Go-favoring" combo scenarios
cat("\n=== Extreme combo scenarios ===\n")
combos <- list(
  list(label="Cheap used RV+truck, housing crash",
       rv_purchase_price=45000, truck_purchase_price=40000,
       home_appreciation_rate=-0.03),
  list(label="Cheap RV, moderate housing decline",
       rv_purchase_price=55000, home_appreciation_rate=-0.02),
  list(label="Dream deal: cheap everything + low campground",
       rv_purchase_price=50000, truck_purchase_price=42000,
       home_appreciation_rate=-0.01, campground_fees_monthly=700)
)
for (combo in combos) {
  p_combo <- default_params
  label   <- combo$label
  for (nm in setdiff(names(combo), "label")) p_combo[[nm]] <- combo[[nm]]
  stay60 <- simulate_stay(p_combo)[60]
  go60   <- simulate_go(p_combo)[60]
  diff60 <- go60 - stay60
  cat(sprintf("%-48s  Go-Stay = %+10.0f  (%s)\n", label, diff60,
    ifelse(diff60 > 50000, "GO wins >$50k",
    ifelse(diff60 > 0,     "Go wins",
    ifelse(diff60 > -50000,"Stay wins <$50k","Stay wins >$50k")))))
}

cat("\nSupplementary plots saved.\n")
