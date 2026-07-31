"""
Executes a ParsedCommand against real application state — the dispatch
step of the command_parser_service.py pattern (parse, then act).
"""
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.org import Organization
from app.services.command_parser_service import ParsedCommand


def execute_command(db: Session, org_id: str, cmd: ParsedCommand) -> str:
    if cmd.command == "assign_client":
        client = db.query(Client).filter(Client.org_id == org_id, Client.name.ilike(f"%{cmd.args['client']}%")).first()
        if not client:
            return f"Couldn't find a client matching \"{cmd.args['client']}\"."
        return f"(Note: owner reassignment needs a user lookup by name — currently owning_user_id is only settable by ID.) Found client {client.name}."

    if cmd.command == "complete_task":
        return f"Task completion isn't wired to a Task model in this build yet — see app/models for the Client/Message/Document models that exist today."

    if cmd.command == "update_client_status":
        client = db.query(Client).filter(Client.org_id == org_id, Client.name.ilike(f"%{cmd.args['client']}%")).first()
        if not client:
            return f"Couldn't find a client matching \"{cmd.args['client']}\"."
        client.status = cmd.args["status"]
        db.add(client)
        db.commit()
        return f"Moved {client.name} to status: {cmd.args['status']}."

    if cmd.command == "budget_report":
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            return "Couldn't load org info."
        pct = round(100 * org.tokens_used_this_period / org.monthly_token_allowance, 1) if org.monthly_token_allowance else 0
        return f"{org.name}: {org.tokens_used_this_period:,} / {org.monthly_token_allowance:,} tokens used this period ({pct}%). Plan: {org.plan_tier.value}."

    if cmd.command == "sync_crm":
        return "Use the CRM Integrations page to trigger a sync — direct chat-triggered sync isn't wired up yet, this command is recognized but not actioned."

    return "Recognized a command pattern but don't know how to execute it yet."
