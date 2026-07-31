SYSTEM_PROMPT = """You are Athena, a negotiation strategy assistant for a licensed \
real estate professional. You suggest offer strategies grounded strictly in the \
market data provided — days on market, comps, price history. You never claim to \
know a seller's personal motivations or financial situation; you reason only from \
listing behavior (price cuts, time on market). You always include the confidence \
level of your suggestion given the data available."""


def build_user_prompt(subject: dict, opportunity: dict, comps: list[dict]) -> str:
    comps_block = "\n".join(
        f"- {c['address']}: ${c['price']:,.0f}, {c['sqft']}sqft, "
        f"{c.get('days_on_market', 'n/a')} days on market"
        for c in comps
    ) or "No comparable data available."

    return f"""SUBJECT LISTING
Address: {subject['address']}
List price: ${subject.get('price', 0):,.0f}
Days on market: {subject.get('days_on_market', 'unknown')}
Price cut since listed: {opportunity.get('price_drop_pct', 0) or 0:.1f}%

MARKET COMPARABLES
{comps_block}

TASK
Based only on the data above:
1. Suggest an opening offer price with brief reasoning
2. Suggest one negotiation lever (e.g. closing timeline, inspection contingency) that fits this specific situation
3. State your confidence (low/medium/high) based on how much data was available
Do not speculate about the seller's personal circumstances."""
