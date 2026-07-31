SYSTEM_PROMPT = """You are Athena, an expert real estate analyst assistant embedded \
in a platform used by licensed realtors. You produce grounded, factual analysis \
based only on the data provided to you. You never invent comps, prices, or facts \
that are not in the input. If data is insufficient, say so plainly. Keep language \
professional, concise, and free of hype."""


def build_user_prompt(subject: dict, comps: list[dict]) -> str:
    comps_block = "\n".join(
        f"- {c['address']}: ${c['price']:,.0f}, {c['beds']}bd/{c['baths']}ba, "
        f"{c['sqft']}sqft, sold/listed {c.get('days_on_market', 'n/a')} days ago, "
        f"similarity {c['similarity_score']:.2f}"
        for c in comps
    ) or "No comparable properties available."

    return f"""SUBJECT PROPERTY
Address: {subject['address']}
Price: ${subject.get('price', 0):,.0f}
Beds/Baths: {subject.get('beds')}/{subject.get('baths')}
Sqft: {subject.get('sqft')}
Type: {subject.get('property_type')}
Year built: {subject.get('year_built')}
Days on market: {subject.get('days_on_market')}

COMPARABLE PROPERTIES
{comps_block}

TASK
Given only the data above, provide:
1. An estimated value range (low/high) with brief justification
2. A 2-3 sentence summary of how this property compares to its comps
3. One practical negotiation or positioning note for the realtor

Be direct. Do not pad with generic real estate platitudes."""
