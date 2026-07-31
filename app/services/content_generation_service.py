"""
Generates realtor marketing content from property data, one or many types
at once. Every generated piece is automatically screened for fair housing
risk before being returned — this is the highest-risk surface in the whole
platform for that kind of issue, so screening isn't optional here the way
it's informational elsewhere.
"""
from sqlalchemy.orm import Session

from app.models.property import Property
from app.services.llm_service import llm_service
from app.services.compliance_service import keyword_risk_summary
from app.prompts.content_generation import SYSTEM_PROMPT, CONTENT_TYPES, build_user_prompt


def get_available_content_types() -> list[dict]:
    return [{"key": k, "label": v["label"]} for k, v in CONTENT_TYPES.items()]


def generate_content(db: Session, property_id: str, content_types: list[str]) -> list[dict]:
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise ValueError("Property not found")

    from app.models.org import Organization
    org = db.query(Organization).filter(Organization.id == prop.org_id).first()
    business_profile = {
        "agent_name": org.agent_name, "brokerage_name": org.brokerage_name,
        "business_phone": org.business_phone, "business_email": org.business_email,
    } if org else None

    property_data = {
        "address": prop.address,
        "price": prop.price,
        "beds": prop.beds,
        "baths": prop.baths,
        "sqft": prop.sqft,
        "property_type": prop.property_type,
        "year_built": prop.year_built,
        "description": prop.description,
    }

    results = []
    for content_type in content_types:
        if content_type not in CONTENT_TYPES:
            results.append({"content_type": content_type, "error": "Unknown content type"})
            continue

        prompt = build_user_prompt(property_data, content_type, business_profile)
        response = llm_service.complete(SYSTEM_PROMPT, prompt, temperature=0.7, max_tokens=500)

        risk = keyword_risk_summary(response.text)
        results.append(
            {
                "content_type": content_type,
                "label": CONTENT_TYPES[content_type]["label"],
                "content": response.text.strip(),
                "compliance_risk": risk["risk"],
                "compliance_flags": risk["flags"],
            }
        )

    return results
