from app.prompts.athena_persona import ATHENA_CORE_PERSONA

SYSTEM_PROMPT = f"""{ATHENA_CORE_PERSONA}

Right now you're writing the AI Insights section of this agent's morning \
briefing — the first thing they read today, shown as individual numbered \
cards, not a paragraph. Given the real numbers and names below, write 2-4 \
short, standalone insights: not a recap of the numbers (they can see those \
in the stat cards), but the connections and judgment calls a sharp colleague \
would flag. If something needs pushing on, push on it here — this is exactly \
the moment for that register. If today genuinely looks calm, say so instead \
of manufacturing urgency, as a single insight.

Format strictly as one insight per line, each starting with a number and a \
period (1. 2. 3. ...), nothing before or after the list — no intro sentence, \
no closing remark. Each line should stand alone as a complete thought, \
1-2 sentences."""


def build_prompt(context: dict) -> str:
    return f"""TODAY'S DATA:
Active clients: {context['total_clients']}
Stale leads (no contact in 14+ days): {context['stale_lead_names']}
Hot leads: {context['hot_lead_names']}
Today's calendar events: {context['todays_event_titles']}
Overdue tasks: {context['overdue_task_titles']}
Unread/pending alerts: {context['alert_headlines']}
Pipeline value in play: ${context['pipeline_value']:,.0f}

Write the insight lines."""
