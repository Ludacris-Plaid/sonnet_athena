from pydantic import BaseModel


class SimulationRequest(BaseModel):
    purchase_price: float
    down_payment_pct: float = 20.0
    interest_rate_pct: float = 7.0
    loan_term_years: int = 30
    monthly_rent: float = 0.0
    annual_rent_growth_pct: float = 2.5
    annual_appreciation_pct: float = 3.0
    vacancy_reserve_pct: float = 5.0
    maintenance_reserve_pct: float = 5.0
    property_mgmt_pct: float = 0.0
    annual_property_tax_pct: float = 1.0
    annual_insurance: float = 1500.0
    closing_costs_pct: float = 2.5
    hold_years: int = 5
