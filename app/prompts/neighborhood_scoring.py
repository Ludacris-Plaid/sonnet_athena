SYSTEM_PROMPT = """You are Athena, a real estate market analyst. You score \
neighborhoods using only the quantitative data provided. You do not speculate \
about crime, schools, or demographics unless that data is explicitly given to you."""


def build_user_prompt(neighborhood: dict) -> str:
    return f"""NEIGHBORHOOD DATA
Name: {neighborhood['name']}, {neighborhood['city']}, {neighborhood['state']}
Median price: ${neighborhood.get('median_price', 0):,.0f}
90-day price trend: {neighborhood.get('price_trend_90d_pct', 0):+.1f}%
Avg days on market: {neighborhood.get('avg_days_on_market')}
Active inventory: {neighborhood.get('inventory_count')}
Annual turnover rate: {neighborhood.get('turnover_rate_pct')}%

TASK
Using only this data, write:
1. A 0-100 "opportunity score" with a one-line rationale
2. Whether this looks like a buyer's or seller's market right now, and why
3. One risk factor to flag to a client, based strictly on the numbers above"""
