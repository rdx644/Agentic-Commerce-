"""
Campaign data models.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class CampaignConfig(BaseModel):
    """Configuration for a campaign run."""

    campaign_id: Optional[str] = None
    total_sessions: int = Field(default=50, ge=2, le=200, description="Capped at 200 sessions to prevent resource exhaustion")
    min_budget_paise: int = Field(default=200000, description="Min session budget (₹2000)")
    max_budget_paise: int = Field(default=2000000, description="Max session budget (₹20000)")
    enable_upsell: bool = Field(default=True)
    num_trials: int = Field(default=5, ge=1, le=50, description="Number of Monte Carlo randomized trials")


class SessionResult(BaseModel):
    """Result of a single simulated session."""

    session_id: str
    group_type: str  # baseline | with_agent
    converted: bool
    basket_size_paise: int
    upsell_offered: bool = False
    upsell_accepted: bool = False
    upsell_amount_paise: int = 0
    duration_ms: int = 0
    failure_class: Optional[str] = None


class CampaignReport(BaseModel):
    """Aggregate campaign results — the measured revenue number with statistical confidence."""

    campaign_id: str
    total_sessions: int

    # Baseline group
    baseline_sessions: int
    baseline_conversions: int
    baseline_conversion_rate: float
    baseline_avg_basket_paise: int
    baseline_total_revenue_paise: int

    # With-agent group
    agent_sessions: int
    agent_conversions: int
    agent_conversion_rate: float
    agent_avg_basket_paise: int
    agent_total_revenue_paise: int
    agent_upsell_offered: int
    agent_upsell_accepted: int
    agent_upsell_rate: float

    # Point Deltas
    conversion_lift_pct: float
    basket_lift_pct: float
    revenue_lift_pct: float
    revenue_delta_paise: int

    # Multi-Trial Statistical Confidence (Monte Carlo Analysis)
    mean_revenue_lift_pct: float = 0.0
    std_deviation_pct: float = 0.0
    ci_95_lower: float = 0.0
    ci_95_upper: float = 0.0
    sample_count: int = 0
    num_trials: int = 1
