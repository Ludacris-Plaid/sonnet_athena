from app.prompts.athena_persona import ATHENA_CORE_PERSONA

SYSTEM_PROMPT_BRIEF = f"""{ATHENA_CORE_PERSONA}

Right now you're preparing this agent for a conversation with a client. \
Summarize the relationship using ONLY the timeline data given — never invent \
facts, preferences, or events not in the data. If there's very little history, \
say so plainly rather than padding. This is a real briefing before a real call \
— give it the weight and specificity that deserves."""

SYSTEM_PROMPT_NEXT_ACTION = f"""{ATHENA_CORE_PERSONA}

Right now you're telling this agent the single most useful next action to take \
with a client, grounded strictly in the timeline and profile data given. Be \
specific and concrete (not "follow up soon" but "it's been 9 days since they \
asked about financing — send the pre-approval checklist"). If something's \
clearly being let slip, this is exactly the moment for your constructively \
pushy register — say it plainly. If nothing suggests urgency, say the \
relationship looks current and there's nothing pressing."""

SYSTEM_PROMPT_TAGS = """You suggest 1-3 short, useful tags for a real estate CRM \
contact based on their profile and recent activity. Tags should be practical \
categories a realtor would filter by (e.g. "first-time buyer", "investor", \
"referral", "price-sensitive") — never speculative labels about a person's \
character or protected characteristics. Respond with ONLY a comma-separated \
list of tags, nothing else."""


def build_brief_prompt(client_data: dict, timeline: list[dict]) -> str:
    timeline_block = "\n".join(
        f"- [{e['timestamp']}] {e['type']}: {e.get('summary', '')}" for e in timeline[:30]
    ) or "No activity recorded yet."

    return f"""CLIENT PROFILE:
Name: {client_data.get('name')}
Type: {client_data.get('client_type')}
Budget: ${client_data.get('budget_max', 0):,.0f}
Preferred area: {client_data.get('preferred_city')}
Pipeline stage: {client_data.get('pipeline_stage')}
Pre-approved: {client_data.get('pre_approved')}

RECENT TIMELINE (most recent first):
{timeline_block}

Give a 3-5 sentence briefing an agent could read in 30 seconds before calling this client."""


def build_next_action_prompt(client_data: dict, timeline: list[dict]) -> str:
    timeline_block = "\n".join(
        f"- [{e['timestamp']}] {e['type']}: {e.get('summary', '')}" for e in timeline[:20]
    ) or "No activity recorded yet."

    return f"""CLIENT PROFILE:
Name: {client_data.get('name')}
Pipeline stage: {client_data.get('pipeline_stage')}
Last contacted: {client_data.get('last_contacted_at') or 'never'}

RECENT TIMELINE:
{timeline_block}

What's the single most useful next action for the agent to take with this client, and why?"""


def build_tags_prompt(client_data: dict) -> str:
    return f"""CLIENT PROFILE:
Type: {client_data.get('client_type')}
Budget: ${client_data.get('budget_max', 0):,.0f}
Pre-approved: {client_data.get('pre_approved')}
Timeline: {client_data.get('timeline')}
Lead source: {client_data.get('lead_source')}
Existing tags: {client_data.get('tags')}

Suggest tags."""
