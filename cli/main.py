"""
RealtyAI CLI — for local testing/demoing without the API layer.

Usage:
  python -m cli.main analyze-property <property_id>
  python -m cli.main compare-neighborhoods --city Edmonton --state AB
  python -m cli.main run-ingestion --city Edmonton --state AB --org-id <uuid>
  python -m cli.main seed-demo-org
"""
import typer
from rich.console import Console
from rich.table import Table

from app.core.database import SessionLocal, init_db
from app.models.org import Organization, PlanTier
from app.models.property import Property
from app.models.neighborhood import Neighborhood
from app.services.property_service import ingest_listings
from app.services.analysis_service import analyze_property as analyze_property_svc, score_neighborhood as score_neighborhood_svc

app = typer.Typer(help="RealtyAI CLI")
console = Console()


@app.command()
def seed_demo_org():
    """Create a demo organization to test against (no auth needed for CLI use)."""
    init_db()
    db = SessionLocal()
    org = Organization(name="Demo Realty Co", plan_tier=PlanTier.MEDIUM)
    db.add(org)
    db.commit()
    db.refresh(org)
    console.print(f"[green]Created demo org:[/green] {org.id}")
    db.close()


@app.command()
def run_ingestion(city: str, state: str, org_id: str, limit: int = 25):
    """Pull listings from the configured LISTINGS_SOURCE (demo or reso)."""
    db = SessionLocal()
    props = ingest_listings(db, org_id=org_id, city=city, state=state, limit=limit)
    console.print(f"[green]Ingested {len(props)} listings for {city}, {state}[/green]")
    db.close()


@app.command()
def analyze_property(property_id: str, max_comps: int = 5):
    db = SessionLocal()
    result = analyze_property_svc(db, property_id, max_comps=max_comps)
    console.print(f"[bold]Estimated value:[/bold] ${result['estimated_value']:,.0f}" if result["estimated_value"] else "No estimate available")
    console.print(f"[bold]Range:[/bold] ${result['value_range_low']:,.0f} - ${result['value_range_high']:,.0f}" if result["value_range_low"] else "")
    console.print("\n[bold]AI Summary:[/bold]")
    console.print(result["ai_summary"])
    db.close()


@app.command()
def compare_neighborhoods(city: str, state: str):
    db = SessionLocal()
    neighborhoods = db.query(Neighborhood).filter(Neighborhood.city == city, Neighborhood.state == state).all()
    if not neighborhoods:
        console.print("[yellow]No neighborhoods found. Add some via the API or seed script first.[/yellow]")
        return

    table = Table(title=f"Neighborhoods in {city}, {state}")
    table.add_column("Name")
    table.add_column("Median Price")
    table.add_column("90d Trend")
    table.add_column("Opportunity Score")

    for n in neighborhoods:
        if n.opportunity_score is None:
            score_neighborhood_svc(db, n.id)
            db.refresh(n)
        table.add_row(
            n.name,
            f"${n.median_price:,.0f}" if n.median_price else "n/a",
            f"{n.price_trend_90d_pct:+.1f}%" if n.price_trend_90d_pct is not None else "n/a",
            f"{n.opportunity_score:.0f}/100" if n.opportunity_score is not None else "n/a",
        )
    console.print(table)
    db.close()


if __name__ == "__main__":
    app()
