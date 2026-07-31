from app.prompts.athena_persona import ATHENA_CORE_PERSONA

SYSTEM_PROMPT = f"""{ATHENA_CORE_PERSONA}

Right now you're drafting a message from this realtor to ANOTHER agent —
the listing agent representing a property, not a client. Keep it
professional, brief, and purposeful (requesting a showing, asking a
question about the listing, submitting interest on behalf of a buyer).
This is agent-to-agent industry correspondence — warmer and more direct
than a cold email, but still professional register, not the internal
work-partner voice you'd use with your own agent."""


def build_prompt(property_data: dict, purpose: str, extra_context: str | None) -> str:
    context_line = f"\n\nADDITIONAL CONTEXT FROM THE AGENT:\n{extra_context}" if extra_context else ""
    return f"""LISTING:
{property_data['address']}, {property_data['city']}, {property_data['state']}
Price: ${property_data.get('price', 0):,.0f}
Listing agent: {property_data.get('listing_agent_name', 'the listing agent')}
Brokerage: {property_data.get('listing_brokerage', 'their brokerage')}

PURPOSE: {purpose}{context_line}

Write a short, professional email to the listing agent."""
