from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.org import User
from app.schemas.portfolio import SimulationRequest
from app.services.portfolio_simulator import SimulationAssumptions, simulate, interpret_simulation

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.post("/simulate")
def simulate_investment(payload: SimulationRequest, user: User = Depends(get_current_user)):
    assumptions = SimulationAssumptions(**payload.model_dump())
    return simulate(assumptions)


@router.post("/interpret")
def interpret_investment(payload: SimulationRequest, user: User = Depends(get_current_user)):
    """Runs the same deterministic simulation, then adds a plain-English AI read on top — the numbers stay exact, this just explains what they mean."""
    assumptions = SimulationAssumptions(**payload.model_dump())
    result = simulate(assumptions)
    return {"result": result, "interpretation": interpret_simulation(assumptions, result)}
