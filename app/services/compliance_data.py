"""
Reference data for compliance checks. This is deliberately NOT presented as
exhaustive or authoritative — real estate law is jurisdiction-specific,
changes constantly (see the FinCEN example below, which changed status
twice in the months before this was written), and no software should claim
to make an agent "fully compliant." Every function that returns this data
must carry a disclaimer pointing back to the agent's brokerage counsel or
state/provincial regulator.

Last reviewed: July 2026. Re-verify before relying on any of this — data
here is a starting reference, not a substitute for legal advice.
"""

# Federal Fair Housing Act (US) protected classes — 42 U.S.C. § 3604(c), stable since 1988.
US_FEDERAL_PROTECTED_CLASSES = [
    "race", "color", "religion", "sex", "disability (handicap)", "familial status", "national origin",
]

# Canada: federally, the Canadian Human Rights Act covers federally-regulated activity; housing
# discrimination is primarily governed by PROVINCIAL human rights codes, which vary. This is a
# representative, non-exhaustive list of grounds commonly protected across most provinces —
# always check the specific province's human rights code/tribunal for the authoritative list.
CANADA_COMMON_PROTECTED_GROUNDS = [
    "race", "colour", "ancestry", "place of origin", "ethnic origin", "citizenship", "creed (religion)",
    "sex", "sexual orientation", "gender identity or expression", "age", "marital status", "family status",
    "disability", "receipt of public assistance (source of income — varies by province, e.g. Ontario)",
]

# Non-exhaustive flagged phrase list, grouped by protected class. Sourced from HUD advertising
# guidance patterns (24 CFR § 100.75) and common provincial human rights guidance. Each entry
# needs human judgment — the same word can be fine or risky depending on context (e.g. "walk to
# church" as a landmark is fine; "Christian neighborhood" as a description of residents is not).
FLAGGED_PHRASES = {
    "familial_status": [
        {"phrase": "no children", "severity": "high", "note": "Directly excludes families with children — a protected class."},
        {"phrase": "adults only", "severity": "high", "note": "Illegal unless the property qualifies for the federal Housing for Older Persons Act (HOPA) senior housing exemption — verify before using."},
        {"phrase": "empty nesters", "severity": "caution", "note": "May imply a preference against families with children depending on context."},
        {"phrase": "singles only", "severity": "high", "note": "Excludes based on marital/family status."},
        {"phrase": "married couples preferred", "severity": "high", "note": "Excludes based on marital status."},
        {"phrase": "childless", "severity": "high", "note": "Directly excludes families with children."},
    ],
    "disability": [
        {"phrase": "no wheelchairs", "severity": "high", "note": "Directly discriminates based on disability."},
        {"phrase": "able-bodied", "severity": "high", "note": "Implies a disability-based preference."},
        {"phrase": "must be able to climb stairs", "severity": "caution", "note": "Describing physical requirements to live somewhere risks disability discrimination — describe the property feature instead (e.g. 'second-floor unit, no elevator')."},
        {"phrase": "no service animals", "severity": "high", "note": "Illegal — service/support animals are a required reasonable accommodation, not a 'pet' restriction."},
    ],
    "race_color_national_origin": [
        {"phrase": "exclusive neighborhood", "severity": "caution", "note": "Historically associated with racially exclusionary practices — HUD guidance flags 'exclusive' as a caution term."},
        {"phrase": "restricted", "severity": "high", "note": "Historically used to signal racial/religious exclusion — avoid entirely."},
        {"phrase": "traditional neighborhood", "severity": "caution", "note": "Vague but has been flagged in some complaints as coded language — review context."},
        {"phrase": "no [nationality]", "severity": "high", "note": "Placeholder pattern — any specific nationality/ethnicity exclusion is a clear violation."},
    ],
    "religion": [
        {"phrase": "christian home", "severity": "high", "note": "Signals a religious preference for occupants."},
        {"phrase": "no muslims", "severity": "high", "note": "Direct religious discrimination."},
        {"phrase": "christian community", "severity": "caution", "note": "Describing the community by religion of residents (not a nearby landmark) is risky."},
    ],
    "sex": [
        {"phrase": "male only", "severity": "high", "note": "Sex-based exclusion; roommate-matching exemptions are narrow and jurisdiction-specific — don't rely on this without checking."},
        {"phrase": "female preferred", "severity": "caution", "note": "Sex-based preference — only arguably defensible in narrow shared-living roommate contexts, and rules vary by jurisdiction."},
    ],
    "source_of_income": [
        {"phrase": "no section 8", "severity": "caution", "note": "Not a federal Fair Housing Act category, but source-of-income IS protected in many US states/cities and in some Canadian provinces (e.g. Ontario) — check local law."},
        {"phrase": "no vouchers", "severity": "caution", "note": "Same as above — verify local source-of-income protections."},
    ],
}

# Illustrative only — NOT an exhaustive or current statement of law. Confirm every item with
# the brokerage's compliance officer or the relevant state/provincial real estate regulator
# before relying on it in a live transaction.
DISCLOSURE_REFERENCE = {
    "US-generic": [
        "Most US states require some form of seller property disclosure statement covering known material defects.",
        "Lead-based paint disclosure is federally required for homes built before 1978 (42 U.S.C. § 4852d).",
    ],
    "US-CA": [
        "California requires a Transfer Disclosure Statement (TDS) and a Natural Hazard Disclosure Statement.",
    ],
    "US-TX": [
        "Texas uses the Seller's Disclosure Notice under Property Code § 5.008.",
    ],
    "US-NY": [
        "New York requires the Property Condition Disclosure Statement (PCDS), or a $500 credit to the buyer in lieu of it.",
    ],
    "US-FL": [
        "Florida case law (Johnson v. Davis) establishes a duty to disclose known material defects not readily observable.",
    ],
    "CA-ON": [
        "Ontario commonly uses the OREA Seller Property Information Statement (SPIS) — note it is optional, not legally mandatory, and using it changes liability dynamics; discuss with the seller's lawyer.",
    ],
    "CA-BC": [
        "British Columbia commonly uses a Property Disclosure Statement (PDS) — customary practice, not a strict legal mandate; confirm current BCFSA guidance.",
    ],
    "CA-AB": [
        "Alberta relies primarily on common-law duty to disclose known latent defects; there is no single mandatory provincial disclosure form.",
    ],
}

# Status of this changes — literally vacated by a federal court in March 2026, under appeal as
# of this writing. This is the clearest possible illustration of why the platform should never
# claim static, permanent compliance: verify current status at https://www.fincen.gov/rre-faqs
# before relying on this.
AML_OVERVIEW = {
    "US": {
        "summary": "The FinCEN Residential Real Estate Rule (31 CFR § 1031.320) would require closing/settlement "
                    "agents (not agents/brokers directly) to report certain non-financed transfers of residential "
                    "property to legal entities or trusts.",
        "status_note": "STATUS IS CONTESTED: the rule took effect March 1, 2026, but a federal court vacated it "
                        "nationwide on March 19, 2026; FinCEN is appealing. Reporting is not currently required "
                        "while the vacatur stands. Verify current status before advising clients.",
        "authoritative_source": "https://www.fincen.gov/rre-faqs",
    },
    "CA": {
        "summary": "Under the Proceeds of Crime (Money Laundering) and Terrorist Financing Act (PCMLTFA), real "
                    "estate brokers/sales representatives must verify client identity, determine beneficial "
                    "ownership for corporate/trust buyers, keep records, and report large cash transactions and "
                    "suspicious transactions to FINTRAC. This is an active, enforced obligation (FINTRAC has "
                    "issued real penalties to brokerages) — unlike the contested US rule above.",
        "authoritative_source": "https://fintrac-canafe.canada.ca/re-ed/real-eng",
    },
}
