"""
Suggests an opening offer + negotiation lever, grounded in comps + real
price-history data (not speculation about the seller).
"""
from sqlalchemy.orm import Session

from app.models.property import Property
from app.services.property_service import find_comps
from app.services.opportunity_service import price_drop_score
from app.services.llm_service import llm_service
from app.prompts import negotiation


def suggest_negotiation_strategy(db: Session, property_id: str) -> dict:
    subject = db.query(Property).filter(Property.id == property_id).first()
    if not subject:
        raise ValueError("Property not found")

    comps = find_comps(db, subject, max_comps=5)
    _, drop_pct = price_drop_score(db, subject)

    subject_dict = {"address": subject.address, "price": subject.price, "days_on_market": subject.days_on_market}
    opportunity_dict = {"price_drop_pct": drop_pct}

    prompt = negotiation.build_user_prompt(subject_dict, opportunity_dict, comps)
    response = llm_service.complete(negotiation.SYSTEM_PROMPT, prompt, temperature=0.3, max_tokens=500)

    return {
        "property_id": subject.id,
        "price_drop_pct": drop_pct,
        "comps_used": len(comps),
        "strategy": response.text,
    }
