"""
Ties together property_service (comps) + llm_service (DeepSeek) to produce
grounded property analysis and neighborhood scoring.
"""
import re

from sqlalchemy.orm import Session

from app.models.property import Property
from app.models.neighborhood import Neighborhood
from app.services.property_service import find_comps
from app.services.llm_service import llm_service
from app.prompts import property_analysis, neighborhood_scoring, investment_insights


def analyze_property(db: Session, property_id, max_comps: int = 5) -> dict:
    subject = db.query(Property).filter(Property.id == property_id).first()
    if not subject:
        raise ValueError("Property not found")

    comps = find_comps(db, subject, max_comps=max_comps)

    subject_dict = {
        "address": subject.address,
        "price": subject.price,
        "beds": subject.beds,
        "baths": subject.baths,
        "sqft": subject.sqft,
        "property_type": subject.property_type,
        "year_built": subject.year_built,
        "days_on_market": subject.days_on_market,
    }

    prompt = property_analysis.build_user_prompt(subject_dict, comps)
    llm_response = llm_service.complete(property_analysis.SYSTEM_PROMPT, prompt)

    # Simple heuristic value range from comps' price-per-sqft, independent of LLM prose,
    # so the numeric estimate is deterministic and auditable rather than parsed from text.
    value_low, value_high, estimate = _estimate_from_comps(subject, comps)

    return {
        "property_id": subject.id,
        "estimated_value": estimate,
        "value_range_low": value_low,
        "value_range_high": value_high,
        "comps_used": len(comps),
        "ai_summary": llm_response.text,
        "investment_notes": None,
    }


def _estimate_from_comps(subject: Property, comps: list[dict]) -> tuple[float | None, float | None, float | None]:
    if not comps or not subject.sqft:
        return None, None, None
    pps_values = [c["price"] / c["sqft"] for c in comps if c.get("sqft")]
    if not pps_values:
        return None, None, None
    avg_pps = sum(pps_values) / len(pps_values)
    estimate = round(avg_pps * subject.sqft, -3)
    return round(estimate * 0.93, -3), round(estimate * 1.07, -3), estimate


def score_neighborhood(db: Session, neighborhood_id) -> dict:
    n = db.query(Neighborhood).filter(Neighborhood.id == neighborhood_id).first()
    if not n:
        raise ValueError("Neighborhood not found")

    n_dict = {
        "name": n.name,
        "city": n.city,
        "state": n.state,
        "median_price": n.median_price,
        "price_trend_90d_pct": n.price_trend_90d_pct,
        "avg_days_on_market": n.avg_days_on_market,
        "inventory_count": n.inventory_count,
        "turnover_rate_pct": n.turnover_rate_pct,
    }
    prompt = neighborhood_scoring.build_user_prompt(n_dict)
    llm_response = llm_service.complete(neighborhood_scoring.SYSTEM_PROMPT, prompt)

    score = _extract_score(llm_response.text)
    if score is not None:
        n.opportunity_score = score
        db.add(n)
        db.commit()

    return {"neighborhood_id": n.id, "opportunity_score": n.opportunity_score, "ai_summary": llm_response.text}


def _extract_score(text: str) -> float | None:
    match = re.search(r"(\d{1,3})\s*(?:/100|out of 100)", text)
    if match:
        val = float(match.group(1))
        return min(val, 100.0)
    return None


def investment_analysis(db: Session, property_id, assumptions: dict) -> dict:
    subject = db.query(Property).filter(Property.id == property_id).first()
    if not subject:
        raise ValueError("Property not found")

    prompt = investment_insights.build_user_prompt({"price": subject.price}, assumptions)
    llm_response = llm_service.complete(investment_insights.SYSTEM_PROMPT, prompt)
    return {"property_id": subject.id, "analysis": llm_response.text}
