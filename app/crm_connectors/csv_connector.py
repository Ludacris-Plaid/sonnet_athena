"""
CSV import "connector" — not a live API integration, since most
brokerage-bundled CRMs (kvCORE/BoldTrail, BoomTown, Sierra Interactive,
etc.) don't expose a usable public API at all. This is the honest fallback:
export contacts to CSV from whatever CRM the agent actually uses, import
here. One-way, one-time per file, no ongoing sync — and it shouldn't be
presented as anything more than that.

Doesn't implement the full CRMConnector interface (test_connection,
webhooks don't apply to a file) — used directly by document_service-style
upload handling in routes_crm.py rather than through crm_sync_service's
connector-based flow.
"""
import csv
import io

# Common column name variants across CRM CSV exports, mapped to our normalized field names.
COLUMN_ALIASES = {
    "name": ["name", "full name", "contact name", "first name lastname"],
    "first_name": ["first name", "firstname"],
    "last_name": ["last name", "lastname"],
    "email": ["email", "email address"],
    "phone": ["phone", "phone number", "mobile", "cell"],
    "budget_max": ["budget", "max budget", "budget max", "price range max"],
    "preferred_city": ["city", "preferred city", "location", "area"],
    "client_type": ["type", "client type", "lead type", "buyer/seller"],
}


def _find_column(header: list[str], candidates: list[str]) -> str | None:
    lowered = {h.lower().strip(): h for h in header}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return None


def parse_csv_contacts(file_bytes: bytes) -> list[dict]:
    text = file_bytes.decode("utf-8-sig", errors="replace")  # utf-8-sig handles Excel's BOM
    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []

    col_map = {field: _find_column(header, aliases) for field, aliases in COLUMN_ALIASES.items()}

    contacts = []
    for row in reader:
        name = None
        if col_map["name"]:
            name = row.get(col_map["name"], "").strip()
        elif col_map["first_name"] or col_map["last_name"]:
            first = row.get(col_map["first_name"], "").strip() if col_map["first_name"] else ""
            last = row.get(col_map["last_name"], "").strip() if col_map["last_name"] else ""
            name = f"{first} {last}".strip()

        if not name:
            continue  # skip rows with no identifiable contact name

        client_type_raw = (row.get(col_map["client_type"], "") if col_map["client_type"] else "").lower()
        client_type = "seller" if "seller" in client_type_raw else "buyer"

        budget_raw = row.get(col_map["budget_max"], "") if col_map["budget_max"] else ""
        budget_max = None
        if budget_raw:
            digits = "".join(c for c in budget_raw if c.isdigit() or c == ".")
            budget_max = float(digits) if digits else None

        contacts.append(
            {
                "external_id": None,
                "name": name,
                "email": row.get(col_map["email"], "").strip() or None if col_map["email"] else None,
                "phone": row.get(col_map["phone"], "").strip() or None if col_map["phone"] else None,
                "client_type": client_type,
                "budget_max": budget_max,
                "preferred_city": row.get(col_map["preferred_city"], "").strip() or None if col_map["preferred_city"] else None,
                "notes": None,
            }
        )

    return contacts
