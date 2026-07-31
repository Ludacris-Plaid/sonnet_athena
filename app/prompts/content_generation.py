"""
Prompt templates for realtor marketing content, one per content type. Every
type here produces MARKETING copy, not binding documents — see
document_prompts.py for the (separately, more cautiously scoped) document
generation system.

All generated content gets auto-screened by compliance_service before it's
returned — see content_generation_service.py — since listing/marketing copy
is exactly where fair housing language risk concentrates.
"""

SYSTEM_PROMPT = """You are Athena, a real estate marketing copywriter. You write \
content strictly from the property facts given to you — never invent details, \
schools, neighborhood claims, or amenities that weren't provided. You never use \
language that could imply a preference or limitation based on race, color, \
religion, sex, disability, familial status, national origin, or other protected \
characteristics — describe the property and its features, never the type of \
person who should live there."""

CONTENT_TYPES = {
    "mls_description": {
        "label": "MLS Listing Description",
        "instructions": "Write a professional MLS listing description, 150-200 words. Lead with the most compelling feature. Factual, no hype-filled clichés.",
    },
    "instagram_caption": {
        "label": "Instagram Caption",
        "instructions": "Write an Instagram caption, under 150 words, with a warm and inviting tone. Include 5-8 relevant hashtags at the end (e.g. #JustListed, city/neighborhood name, property type).",
    },
    "facebook_post": {
        "label": "Facebook Post",
        "instructions": "Write a Facebook post, 80-120 words, conversational tone, ending with a clear call to action (e.g. 'DM me to schedule a showing').",
    },
    "just_listed_email": {
        "label": "\"Just Listed\" Email Blast",
        "instructions": "Write a short email announcing this new listing to the agent's contact list. Include a subject line, then 100-150 words of body copy, then a clear CTA.",
    },
    "open_house_flyer": {
        "label": "Open House Flyer Copy",
        "instructions": "Write flyer copy for an open house: a short headline, 3-5 bullet-style highlight lines (not full sentences), and a closing line with placeholder date/time text like [DATE] and [TIME] for the agent to fill in.",
    },
    "price_drop_announcement": {
        "label": "Price Drop Announcement",
        "instructions": "Write a short, tasteful announcement (60-90 words) that the price was reduced. Don't sound desperate or imply anything negative about the property — frame it as a new opportunity for buyers.",
    },
    "virtual_tour_script": {
        "label": "Virtual Tour Voiceover Script",
        "instructions": "Write a room-by-room voiceover script for a video walkthrough, using only the rooms/features given. Conversational, second person ('as you walk in...'), roughly 200-300 words.",
    },
}


def build_user_prompt(property_data: dict, content_type: str, business_profile: dict | None = None) -> str:
    spec = CONTENT_TYPES.get(content_type)
    if not spec:
        raise ValueError(f"Unknown content_type: {content_type}")

    facts = f"""PROPERTY FACTS (use only these — do not invent anything not listed):
Address: {property_data.get('address')}
Price: ${property_data.get('price', 0):,.0f}
Beds: {property_data.get('beds')}
Baths: {property_data.get('baths')}
Square feet: {property_data.get('sqft')}
Property type: {property_data.get('property_type')}
Year built: {property_data.get('year_built')}
Existing description (if any): {property_data.get('description') or 'None provided'}
"""

    business_block = ""
    if business_profile and any(business_profile.values()):
        business_block = f"""

AGENT/BROKERAGE INFO (use naturally where a sign-off or contact info fits
this content type — e.g. an email or flyer, NOT a listing description or
a social caption's hashtag section; use your judgment on whether it
belongs at all for this content type):
Agent: {business_profile.get('agent_name') or ''}
Brokerage: {business_profile.get('brokerage_name') or ''}
Phone: {business_profile.get('business_phone') or ''}
Email: {business_profile.get('business_email') or ''}"""

    return f"{facts}\n\nCONTENT TYPE: {spec['label']}\nINSTRUCTIONS: {spec['instructions']}{business_block}"
