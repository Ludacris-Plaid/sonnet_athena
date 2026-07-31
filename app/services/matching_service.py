"""
Matches active clients to properties based on stored client criteria
(budget, preferred city, timeline) — a straightforward filter/rank, no
speculative signals. This is what turns "I found some listings" into
"here are the 3 clients who should see this listing today."
"""
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.property import Property


def match_properties_for_client(db: Session, client: Client, limit: int = 10) -> list[dict]:
    query = db.query(Property).filter(Property.org_id == client.org_id, Property.status == "active")

    if client.preferred_city:
        query = query.filter(Property.city.ilike(f"%{client.preferred_city}%"))
    if client.budget_max:
        query = query.filter(Property.price <= client.budget_max * 1.05)  # small headroom, list price often negotiable

    candidates = query.all()

    scored = []
    for p in candidates:
        score = match_score(client, p)
        if score > 0:
            scored.append({"property": p, "match_score": score})

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return [
        {
            "property_id": s["property"].id,
            "address": s["property"].address,
            "price": s["property"].price,
            "beds": s["property"].beds,
            "sqft": s["property"].sqft,
            "match_score": round(s["match_score"], 1),
        }
        for s in scored[:limit]
    ]


def match_score(client: Client, prop: Property) -> float:
    score = 50.0

    if client.budget_max and prop.price:
        if prop.price <= client.budget_max:
            # Reward being well under budget slightly, but don't over-index on cheapest
            headroom = (client.budget_max - prop.price) / client.budget_max
            score += min(headroom * 30, 15)
        else:
            over_pct = (prop.price - client.budget_max) / client.budget_max
            score -= over_pct * 100  # penalize going over budget heavily

    if client.preferred_city and prop.city:
        if client.preferred_city.strip().lower() in prop.city.strip().lower():
            score += 20

    return max(0.0, min(100.0, score))


def find_clients_for_new_listing(db: Session, prop: Property, limit: int = 10) -> list[dict]:
    """Inverse direction: given a new listing, which clients should be told about it?"""
    clients = db.query(Client).filter(Client.org_id == prop.org_id, Client.status == "active").all()
    scored = []
    for c in clients:
        score = match_score(c, prop)
        if score >= 50:
            scored.append({"client": c, "match_score": score})
    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return [
        {"client_id": s["client"].id, "name": s["client"].name, "match_score": round(s["match_score"], 1)}
        for s in scored[:limit]
    ]
