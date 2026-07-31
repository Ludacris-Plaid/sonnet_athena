"""
Deterministic investment math (cap rate, cash-on-cash, multi-year cash flow
and equity projection) computed in plain Python — not by the LLM, so the
numbers are auditable. The LLM is only used afterward, optionally, to
narrate the result. This mirrors analysis_service's pattern of "compute
first, explain second."
"""
from dataclasses import dataclass, asdict


@dataclass
class SimulationAssumptions:
    purchase_price: float
    down_payment_pct: float = 20.0
    interest_rate_pct: float = 7.0
    loan_term_years: int = 30
    monthly_rent: float = 0.0
    annual_rent_growth_pct: float = 2.5
    annual_appreciation_pct: float = 3.0
    vacancy_reserve_pct: float = 5.0        # % of rent reserved for vacancy
    maintenance_reserve_pct: float = 5.0    # % of rent reserved for maintenance
    property_mgmt_pct: float = 0.0          # % of rent, 0 if self-managed
    annual_property_tax_pct: float = 1.0    # % of purchase price
    annual_insurance: float = 1500.0
    closing_costs_pct: float = 2.5
    hold_years: int = 5


def _monthly_mortgage_payment(loan_amount: float, annual_rate_pct: float, term_years: int) -> float:
    monthly_rate = (annual_rate_pct / 100) / 12
    n_payments = term_years * 12
    if monthly_rate == 0:
        return loan_amount / n_payments
    return loan_amount * (monthly_rate * (1 + monthly_rate) ** n_payments) / ((1 + monthly_rate) ** n_payments - 1)


def simulate(a: SimulationAssumptions) -> dict:
    down_payment = a.purchase_price * (a.down_payment_pct / 100)
    loan_amount = a.purchase_price - down_payment
    closing_costs = a.purchase_price * (a.closing_costs_pct / 100)
    total_cash_invested = down_payment + closing_costs

    monthly_payment = _monthly_mortgage_payment(loan_amount, a.interest_rate_pct, a.loan_term_years)
    annual_debt_service = monthly_payment * 12

    yearly_projection = []
    balance = loan_amount
    monthly_rate = (a.interest_rate_pct / 100) / 12
    current_rent = a.monthly_rent
    current_value = a.purchase_price

    for year in range(1, a.hold_years + 1):
        annual_gross_rent = current_rent * 12
        vacancy_loss = annual_gross_rent * (a.vacancy_reserve_pct / 100)
        maintenance = annual_gross_rent * (a.maintenance_reserve_pct / 100)
        mgmt_fee = annual_gross_rent * (a.property_mgmt_pct / 100)
        property_tax = a.purchase_price * (a.annual_property_tax_pct / 100)
        insurance = a.annual_insurance

        operating_expenses = vacancy_loss + maintenance + mgmt_fee + property_tax + insurance
        noi = annual_gross_rent - operating_expenses  # Net Operating Income, before debt service
        annual_cash_flow = noi - annual_debt_service

        # Amortize principal paid down this year (approximation via monthly loop)
        principal_paid_this_year = 0.0
        for _ in range(12):
            interest_payment = balance * monthly_rate
            principal_payment = monthly_payment - interest_payment
            balance = max(0.0, balance - principal_payment)
            principal_paid_this_year += principal_payment

        current_value *= 1 + (a.annual_appreciation_pct / 100)
        equity = current_value - balance

        yearly_projection.append(
            {
                "year": year,
                "gross_rent": round(annual_gross_rent, 2),
                "operating_expenses": round(operating_expenses, 2),
                "noi": round(noi, 2),
                "annual_cash_flow": round(annual_cash_flow, 2),
                "principal_paid": round(principal_paid_this_year, 2),
                "property_value": round(current_value, 2),
                "loan_balance": round(balance, 2),
                "equity": round(equity, 2),
            }
        )
        current_rent *= 1 + (a.annual_rent_growth_pct / 100)

    year_1 = yearly_projection[0]
    cap_rate = (year_1["noi"] / a.purchase_price * 100) if a.purchase_price else None
    cash_on_cash = (year_1["annual_cash_flow"] / total_cash_invested * 100) if total_cash_invested else None

    final_year = yearly_projection[-1]
    total_cash_flow = sum(y["annual_cash_flow"] for y in yearly_projection)
    total_equity_gain = final_year["equity"] - down_payment
    total_return = total_cash_flow + total_equity_gain
    simple_annualized_return_pct = (
        (total_return / total_cash_invested / a.hold_years * 100) if total_cash_invested else None
    )

    return {
        "assumptions": asdict(a),
        "down_payment": round(down_payment, 2),
        "closing_costs": round(closing_costs, 2),
        "total_cash_invested": round(total_cash_invested, 2),
        "monthly_mortgage_payment": round(monthly_payment, 2),
        "year_1_cap_rate_pct": round(cap_rate, 2) if cap_rate is not None else None,
        "year_1_cash_on_cash_pct": round(cash_on_cash, 2) if cash_on_cash is not None else None,
        "yearly_projection": yearly_projection,
        "hold_period_summary": {
            "total_cash_flow": round(total_cash_flow, 2),
            "total_equity_gain": round(total_equity_gain, 2),
            "total_return": round(total_return, 2),
            "simple_annualized_return_pct": round(simple_annualized_return_pct, 2)
            if simple_annualized_return_pct is not None
            else None,
        },
    }


def interpret_simulation(assumptions: "SimulationAssumptions", result: dict) -> str:
    """
    Plain-English read on a simulation's numbers — the AI touchpoint the
    standalone Investment Calculator was missing. Deliberately doesn't
    touch the math (that stays deterministic in simulate() above) — this
    just narrates what the already-computed numbers mean in practice,
    same "compute first, narrate second" pattern used everywhere else in
    this codebase (opportunity scoring, CMA analysis, etc).
    """
    from app.services.llm_service import llm_service
    from app.prompts.athena_persona import ATHENA_CORE_PERSONA

    system_prompt = f"""{ATHENA_CORE_PERSONA}

Right now you're giving a real estate agent a plain-English read on an
investment calculation they just ran — grounded strictly in the numbers
given below, never inventing figures. Be direct about whether this looks
like a strong, weak, or middling deal and why, in 3-5 sentences. If a
number stands out as unusual (e.g. negative cash-on-cash, an
unusually high cap rate), say so plainly rather than glossing over it."""

    prompt = f"""ASSUMPTIONS:
Purchase price: ${assumptions.purchase_price:,.0f}
Monthly rent: ${assumptions.monthly_rent:,.0f}
Down payment: {assumptions.down_payment_pct}%
Interest rate: {assumptions.interest_rate_pct}%
Hold period: {assumptions.hold_years} years

RESULTS:
Year 1 cap rate: {result.get('year_1_cap_rate_pct')}%
Year 1 cash-on-cash return: {result.get('year_1_cash_on_cash_pct')}%
Monthly mortgage payment: ${result.get('monthly_mortgage_payment', 0):,.0f}
Total cash invested: ${result.get('total_cash_invested', 0):,.0f}
Annualized return over the hold period: {result.get('hold_period_summary', {}).get('simple_annualized_return_pct')}%

Give your read."""

    response = llm_service.complete(system_prompt, prompt, temperature=0.5, max_tokens=350)
    return response.text.strip()
