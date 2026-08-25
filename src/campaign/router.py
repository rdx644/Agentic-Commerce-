"""
Campaign API routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.campaign.models import CampaignConfig, CampaignReport
from src.campaign import orchestrator
from src.security.auth import require_operator

router = APIRouter(prefix="/campaign", tags=["campaign"], dependencies=[Depends(require_operator)])


@router.post("/run", response_model=CampaignReport, summary="Run Campaign")
async def run_campaign(config: CampaignConfig = CampaignConfig()):
    """
    Run a campaign: baseline vs with-agent across simulated sessions.
    Returns measured conversion, basket size, and revenue delta.
    """
    return orchestrator.run_campaign(config)


@router.get("/results/{campaign_id}", response_model=CampaignReport, summary="Get Campaign Results")
async def get_results(campaign_id: str):
    """Retrieve results for a previously run campaign."""
    report = orchestrator.get_campaign_report(campaign_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Campaign '{campaign_id}' not found")
    return report
