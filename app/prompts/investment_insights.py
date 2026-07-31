SYSTEM_PROMPT = """You are Athena, an investment analysis assistant for licensed \
real estate professionals. You calculate straightforward, conservative estimates \
and clearly label all assumptions. You are not a financial advisor and you say so \
when a request strays into personalized financial advice territory."""


def build_user_prompt(property_data: dict, assumptions: dict) -> str:
    return f"""PROPERTY
Price: ${property_data.get('price', 0):,.0f}
Estimated monthly rent: ${assumptions.get('monthly_rent', 0):,.0f}
Down payment %: {assumptions.get('down_payment_pct', 20)}%
Interest rate: {assumptions.get('interest_rate', 7.0)}%
Est. annual maintenance/vacancy reserve: {assumptions.get('reserve_pct', 10)}% of rent

TASK
Using standard, conservative real estate investment formulas, estimate:
1. Approximate monthly cash flow
2. Cap rate
3. Cash-on-cash return
Show your assumptions explicitly. Flag if any required input is missing rather \
than guessing a number."""
