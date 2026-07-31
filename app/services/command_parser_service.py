"""
Deterministic slash/imperative command parsing for the chat interface —
inspired by Meridian Company OS's "Kimi Space" pattern (an operator chat
surface that recognizes structured commands like "assign X to Y, p1" and
dispatches them directly, falling back to free-form LLM chat only when no
command matches).

Note on provenance: the linked repo (github.com/codejunkie99/meridian-company-os)
returned a 404 on direct fetch when this was built — likely renamed, made
private, or removed since it was indexed. This is a fresh implementation of
the general pattern as described in that index, not a port of its actual
code (which was never seen).

Why this is worth having independent of Hermes/LLM routing: routine ops
("assign this client to me", "mark this task done") are faster, cheaper,
and more reliable as direct parses than round-tripping through an LLM
intent classifier — same reasoning as any command palette. Free-form
messages that don't match a pattern fall through to orchestrator_service's
normal LLM-based routing unchanged.
"""
import re
from dataclasses import dataclass


@dataclass
class ParsedCommand:
    command: str
    args: dict


# Patterns are intentionally simple and explicit — this is a fast path for
# power users typing structured shorthand, not a natural-language parser.
_PATTERNS = [
    (re.compile(r"^assign\s+client\s+(?P<client>.+?)\s+to\s+(?P<owner>.+)$", re.I), "assign_client"),
    (re.compile(r"^mark\s+task\s+(?P<task_id>\S+)\s+(?:as\s+)?done$", re.I), "complete_task"),
    (re.compile(r"^move\s+client\s+(?P<client>.+?)\s+to\s+(?P<status>\w+)$", re.I), "update_client_status"),
    (re.compile(r"^budget\s+report$", re.I), "budget_report"),
    (re.compile(r"^sync\s+crm(?:\s+(?P<provider>\w+))?$", re.I), "sync_crm"),
]


def try_parse_command(text: str) -> ParsedCommand | None:
    stripped = text.strip()
    for pattern, command_name in _PATTERNS:
        match = pattern.match(stripped)
        if match:
            return ParsedCommand(command=command_name, args=match.groupdict())
    return None
