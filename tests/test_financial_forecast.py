"""Financial forecast engine smoke tests."""

from datetime import date

import pandas as pd

from services.financial_forecast import build_financial_forecast, sanitize_forecast_config


def test_build_financial_forecast_baseline() -> None:
    pl = pd.DataFrame(
        [
            {"fiscal_year": 2024, "fiscal_period": 1, "label": "Jan 2024", "revenue_net": 100.0, "expense_net": 60.0, "net_pl": 40.0},
            {"fiscal_year": 2024, "fiscal_period": 2, "label": "Feb 2024", "revenue_net": 110.0, "expense_net": 62.0, "net_pl": 48.0},
        ]
    )
    config = {
        "horizon_periods": 3,
        "revenue_methods": {
            "bottom_up": {"enabled": True, "weight": 50},
            "time_series": {"enabled": True, "weight": 50},
        },
        "expense_methods": {
            "pct_of_sales": {"enabled": True, "weight": 100},
            "historical_incremental": {"enabled": False, "weight": 0},
            "scenario": {"enabled": False, "weight": 0},
        },
        "bottom_up": {
            "monthly_traffic": 1000,
            "conversion_rate_pct": 10,
            "average_order_value": 50,
            "sales_headcount": 1,
            "quota_per_rep": 5000,
        },
        "time_series": {"yoy_growth_pct": 5},
        "pct_of_sales": {"cogs_pct": 40, "marketing_pct": 10, "shipping_pct": 5},
        "historical_incremental": {"overhead_annual_growth_pct": 3},
        "scenario": {
            "best_revenue_mult": 1.1,
            "worst_revenue_mult": 0.9,
            "best_expense_mult": 0.95,
            "worst_expense_mult": 1.1,
        },
    }
    out = build_financial_forecast(config=config, pl_df=pl, fy_start_month=1, currency_prefix="$")
    assert len(out["labels"]) == 3
    assert len(out["baseline"]["revenue"]) == 3
    assert len(out["scenarios"]["best"]["net"]) == 3
    assert out["growth_table"][0]["mom_revenue_pct"] is None
    assert len(out["assumptions"]) >= 2


def test_forecast_includes_rest_of_current_fy_when_gl_has_future_months() -> None:
    """Future-dated GL must not skip remaining months of the calendar/fiscal year."""
    pl = pd.DataFrame(
        [
            {
                "fiscal_year": 2026,
                "fiscal_period": 5,
                "label": "May 2026",
                "revenue_net": 100.0,
                "expense_net": 60.0,
                "net_pl": 40.0,
            },
            {
                "fiscal_year": 2026,
                "fiscal_period": 12,
                "label": "Dec 2026",
                "revenue_net": 50.0,
                "expense_net": 30.0,
                "net_pl": 20.0,
            },
        ]
    )
    config = {
        "horizon_periods": 6,
        "revenue_methods": {"time_series": {"enabled": True, "weight": 100}},
        "expense_methods": {"pct_of_sales": {"enabled": True, "weight": 100}},
        "time_series": {"yoy_growth_pct": 5},
        "pct_of_sales": {"cogs_pct": 40, "marketing_pct": 10, "shipping_pct": 5},
    }
    out = build_financial_forecast(
        config=config,
        pl_df=pl,
        fy_start_month=1,
        today=date(2026, 5, 15),
    )
    assert out["labels"][0] == "Jun 2026"
    assert "Dec 2026" in out["labels"]


def test_custom_assumptions_in_preview() -> None:
    config = {
        "horizon_periods": 3,
        "revenue_methods": {"time_series": {"enabled": True, "weight": 100}},
        "expense_methods": {"pct_of_sales": {"enabled": True, "weight": 100}},
        "time_series": {"yoy_growth_pct": 5},
        "pct_of_sales": {"cogs_pct": 40, "marketing_pct": 10, "shipping_pct": 5},
        "custom_assumptions": [
            {"id": "a1", "side": "revenue", "text": "Launch pipeline adds 10% in H2"},
            {"id": "a2", "side": "expense", "text": "Rent step-up in September"},
        ],
    }
    out = build_financial_forecast(config=config, pl_df=pd.DataFrame(), fy_start_month=1)
    joined = " ".join(out["assumptions"])
    assert "Launch pipeline" in joined
    assert "Rent step-up" in joined


def test_sanitize_forecast_config_strips_crm() -> None:
    raw = {
        "revenue_methods": {
            "bottom_up": {"enabled": True, "weight": 50},
            "crm_pipeline": {"enabled": True, "weight": 50},
        },
        "pipeline": [{"name": "Deal", "amount": 1000}],
    }
    clean = sanitize_forecast_config(raw)
    assert "crm_pipeline" not in clean["revenue_methods"]
    assert "pipeline" not in clean
