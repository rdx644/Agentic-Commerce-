"""
Campaign orchestrator — batch the flow across simulated sessions.

Purpose: "grows the merchant's revenue" becomes a measured number with
statistical confidence (mean uplift, 95% CI, standard deviation, sample count),
not an ungrounded anecdote.

Design:
- Split sessions 50/50: baseline (no agent) vs with-agent (full flow)
- Dynamic price-elasticity upsell acceptance modeling (not hardcoded 60%)
- Multi-trial Monte Carlo simulation to compute empirical confidence intervals
- All sessions go through the real guardrail — no mock paths
"""

from __future__ import annotations

import json
import logging
import math
import random
import statistics
import time
import uuid
from typing import Optional

from src.campaign.models import CampaignConfig, CampaignReport, SessionResult
from src.catalog import service as catalog_service
from src.guardrail.models import CartItem, Decision, SpendIntent
from src.guardrail import service as guardrail_service
from src.guardrail import ledger as budget_ledger
from src.upsell import service as upsell_service
from src.upsell.models import UpsellAcceptRequest, UpsellOfferRequest
from src.database import get_db_transaction, get_db

logger = logging.getLogger(__name__)


def _simulate_upsell_acceptance(offer_price_paise: int, remaining_budget_paise: int) -> bool:
    """
    Dynamic price-elasticity acceptance model.
    Customers have higher willingness-to-pay when the add-on is a smaller fraction
    of their remaining headroom.
    """
    if remaining_budget_paise <= 0:
        return False
    
    # Headroom ratio: higher headroom = higher acceptance
    headroom_ratio = min(1.0, max(0.05, remaining_budget_paise / (offer_price_paise + remaining_budget_paise)))
    # Base probability modeled with natural consumer elasticity (30% - 75%)
    base_prob = 0.25 + (0.50 * headroom_ratio)
    # Add random demographic variance
    noise = random.uniform(-0.08, 0.08)
    acceptance_prob = max(0.10, min(0.90, base_prob + noise))
    return random.random() < acceptance_prob


def run_campaign(config: CampaignConfig) -> CampaignReport:
    """
    Run a full campaign: baseline vs with-agent across simulated sessions with
    multi-trial Monte Carlo statistical analysis.
    """
    campaign_id = config.campaign_id or f"camp_{uuid.uuid4().hex[:12]}"
    manifest = catalog_service.get_manifest()
    available_items = [item for item in manifest.items if item.available]

    if len(available_items) < 2:
        raise ValueError("Need at least 2 available catalog items for campaign simulation")

    half = config.total_sessions // 2
    baseline_results: list[SessionResult] = []
    agent_results: list[SessionResult] = []

    # ── Primary Run: Persisted to Database ────────────────────────────────
    for i in range(half):
        session_id = f"{campaign_id}_baseline_{i}"
        result = _run_baseline_session(session_id, available_items, config, manifest.hash)
        baseline_results.append(result)
        _save_session_result(campaign_id, result)

    for i in range(config.total_sessions - half):
        session_id = f"{campaign_id}_agent_{i}"
        result = _run_agent_session(session_id, available_items, config, manifest.hash)
        agent_results.append(result)
        _save_session_result(campaign_id, result)

    # ── Multi-Trial Monte Carlo Analysis ──────────────────────────────────
    trial_lifts: list[float] = []
    num_trials = max(1, config.num_trials)

    for trial_idx in range(num_trials):
        t_base_rev = 0
        t_base_conv = 0
        for _ in range(half):
            res = _run_baseline_session(f"mc_base_{trial_idx}_{uuid.uuid4().hex[:6]}", available_items, config, manifest.hash)
            if res.converted:
                t_base_rev += res.basket_size_paise
                t_base_conv += 1

        t_agent_rev = 0
        t_agent_conv = 0
        for _ in range(config.total_sessions - half):
            res = _run_agent_session(f"mc_agent_{trial_idx}_{uuid.uuid4().hex[:6]}", available_items, config, manifest.hash)
            if res.converted:
                t_agent_rev += res.basket_size_paise
                t_agent_conv += 1

        lift = ((t_agent_rev - t_base_rev) / t_base_rev * 100) if t_base_rev > 0 else 0.0
        trial_lifts.append(lift)

    # Compute statistics across Monte Carlo trials
    mean_lift = float(statistics.mean(trial_lifts))
    std_dev = float(statistics.stdev(trial_lifts)) if len(trial_lifts) > 1 else 0.0
    se = std_dev / math.sqrt(len(trial_lifts)) if len(trial_lifts) > 0 else 0.0
    ci_lower = mean_lift - (1.96 * se)
    ci_upper = mean_lift + (1.96 * se)

    # ── Compute aggregate report ──────────────────────────────────────────
    report = _compute_report(campaign_id, baseline_results, agent_results)
    report.mean_revenue_lift_pct = round(mean_lift, 2)
    report.std_deviation_pct = round(std_dev, 2)
    report.ci_95_lower = round(ci_lower, 2)
    report.ci_95_upper = round(ci_upper, 2)
    report.sample_count = config.total_sessions * num_trials
    report.num_trials = num_trials

    return report


def _run_baseline_session(
    session_id: str,
    items: list,
    config: CampaignConfig,
    catalog_hash: str,
) -> SessionResult:
    """Simulate a baseline session (no upsell agent)."""
    start = time.time()

    budget = random.randint(config.min_budget_paise, config.max_budget_paise)
    cart_size = random.randint(1, min(3, len(items)))
    cart_items_raw = random.sample(items, cart_size)

    budget_ledger.init_session_budget(session_id, budget)

    cart_items = [CartItem(item_id=item.item_id, quantity=1) for item in cart_items_raw]
    total = sum(item.price_paise for item in cart_items_raw)

    intent = SpendIntent(
        session_id=session_id,
        items=cart_items,
        stated_ceiling_paise=budget,
        catalog_hash=catalog_hash,
        actor="system",
        intent_type="checkout",
    )

    decision = guardrail_service.check_spend(intent)
    duration = int((time.time() - start) * 1000)

    converted = decision.decision == Decision.PASS
    return SessionResult(
        session_id=session_id,
        group_type="baseline",
        converted=converted,
        basket_size_paise=total if converted else 0,
        duration_ms=duration,
        failure_class=decision.failure_class.value if decision.failure_class else None,
    )


def _run_agent_session(
    session_id: str,
    items: list,
    config: CampaignConfig,
    catalog_hash: str,
) -> SessionResult:
    """Simulate an agent session with dynamic upsell."""
    start = time.time()

    budget = random.randint(config.min_budget_paise, config.max_budget_paise)
    cart_size = random.randint(1, min(3, len(items)))
    cart_items_raw = random.sample(items, cart_size)

    budget_ledger.init_session_budget(session_id, budget)

    cart_items = [CartItem(item_id=item.item_id, quantity=1) for item in cart_items_raw]
    total = sum(item.price_paise for item in cart_items_raw)

    intent = SpendIntent(
        session_id=session_id,
        items=cart_items,
        stated_ceiling_paise=budget,
        catalog_hash=catalog_hash,
        actor="agent",
        intent_type="checkout",
    )

    decision = guardrail_service.check_spend(intent)

    if decision.decision != Decision.PASS:
        duration = int((time.time() - start) * 1000)
        return SessionResult(
            session_id=session_id,
            group_type="with_agent",
            converted=False,
            basket_size_paise=0,
            duration_ms=duration,
            failure_class=decision.failure_class.value if decision.failure_class else None,
        )

    # Base cart passed — try dynamic upsell
    upsell_offered = False
    upsell_accepted = False
    upsell_amount = 0

    if config.enable_upsell:
        state = budget_ledger.get_session_state(session_id)
        remaining = state.remaining_paise if state else 0

        if remaining > 0:
            offer_request = UpsellOfferRequest(
                session_id=session_id,
                cart_item_ids=[item.item_id for item in cart_items_raw],
                remaining_budget_paise=remaining,
                capability_token=decision.capability_token,
            )
            offer_response = upsell_service.generate_offer(offer_request)

            if offer_response.offer:
                upsell_offered = True
                # Dynamic acceptance based on price elasticity & budget headroom
                if _simulate_upsell_acceptance(offer_response.offer.price_paise, remaining):
                    accept_response = upsell_service.accept_upsell(UpsellAcceptRequest(
                        session_id=session_id,
                        offer=offer_response.offer,
                        capability_token=decision.capability_token,
                    ))
                    if accept_response.accepted:
                        upsell_accepted = True
                        upsell_amount = offer_response.offer.price_paise
                        total += upsell_amount

    duration = int((time.time() - start) * 1000)

    return SessionResult(
        session_id=session_id,
        group_type="with_agent",
        converted=True,
        basket_size_paise=total,
        upsell_offered=upsell_offered,
        upsell_accepted=upsell_accepted,
        upsell_amount_paise=upsell_amount,
        duration_ms=duration,
    )


def _save_session_result(campaign_id: str, result: SessionResult) -> None:
    """Persist session result to DB."""
    with get_db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO campaign_sessions
            (campaign_id, session_id, group_type, converted, basket_size_paise,
             upsell_offered, upsell_accepted, upsell_amount_paise, duration_ms, failure_class)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                campaign_id,
                result.session_id,
                result.group_type,
                int(result.converted),
                result.basket_size_paise,
                int(result.upsell_offered),
                int(result.upsell_accepted),
                result.upsell_amount_paise,
                result.duration_ms,
                result.failure_class,
            ),
        )


def _compute_report(
    campaign_id: str,
    baseline: list[SessionResult],
    agent: list[SessionResult],
) -> CampaignReport:
    """Compute aggregate metrics from session results."""
    # Baseline metrics
    b_total = len(baseline)
    b_conv = sum(1 for r in baseline if r.converted)
    b_revenue = sum(r.basket_size_paise for r in baseline if r.converted)
    b_avg_basket = b_revenue // b_conv if b_conv > 0 else 0
    b_conv_rate = b_conv / b_total if b_total > 0 else 0.0

    # Agent metrics
    a_total = len(agent)
    a_conv = sum(1 for r in agent if r.converted)
    a_revenue = sum(r.basket_size_paise for r in agent if r.converted)
    a_avg_basket = a_revenue // a_conv if a_conv > 0 else 0
    a_conv_rate = a_conv / a_total if a_total > 0 else 0.0
    a_upsell_offered = sum(1 for r in agent if r.upsell_offered)
    a_upsell_accepted = sum(1 for r in agent if r.upsell_accepted)
    a_upsell_rate = a_upsell_accepted / a_upsell_offered if a_upsell_offered > 0 else 0.0

    # Deltas
    conv_lift = ((a_conv_rate - b_conv_rate) / b_conv_rate * 100) if b_conv_rate > 0 else 0.0
    basket_lift = ((a_avg_basket - b_avg_basket) / b_avg_basket * 100) if b_avg_basket > 0 else 0.0
    revenue_lift = ((a_revenue - b_revenue) / b_revenue * 100) if b_revenue > 0 else 0.0

    return CampaignReport(
        campaign_id=campaign_id,
        total_sessions=b_total + a_total,
        baseline_sessions=b_total,
        baseline_conversions=b_conv,
        baseline_conversion_rate=round(b_conv_rate, 4),
        baseline_avg_basket_paise=b_avg_basket,
        baseline_total_revenue_paise=b_revenue,
        agent_sessions=a_total,
        agent_conversions=a_conv,
        agent_conversion_rate=round(a_conv_rate, 4),
        agent_avg_basket_paise=a_avg_basket,
        agent_total_revenue_paise=a_revenue,
        agent_upsell_offered=a_upsell_offered,
        agent_upsell_accepted=a_upsell_accepted,
        agent_upsell_rate=round(a_upsell_rate, 4),
        conversion_lift_pct=round(conv_lift, 2),
        basket_lift_pct=round(basket_lift, 2),
        revenue_lift_pct=round(revenue_lift, 2),
        revenue_delta_paise=a_revenue - b_revenue,
    )


def get_campaign_report(campaign_id: str) -> Optional[CampaignReport]:
    """Reconstruct a campaign report from stored session results."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM campaign_sessions WHERE campaign_id = %s",
            (campaign_id,),
        ).fetchall()

    if not rows:
        return None

    baseline = []
    agent = []
    for row in rows:
        result = SessionResult(
            session_id=row["session_id"],
            group_type=row["group_type"],
            converted=bool(row["converted"]),
            basket_size_paise=row["basket_size_paise"],
            upsell_offered=bool(row["upsell_offered"]),
            upsell_accepted=bool(row["upsell_accepted"]),
            upsell_amount_paise=row["upsell_amount_paise"],
            duration_ms=row["duration_ms"] or 0,
            failure_class=row["failure_class"],
        )
        if row["group_type"] == "baseline":
            baseline.append(result)
        else:
            agent.append(result)

    return _compute_report(campaign_id, baseline, agent)
