path = '/home/dysthemix/realtyai/app/scrapers/homeharvest_source.py'
with open(path) as f:
    c = f.read()

# Fix _get_address
old = '''    def _get_address(self, row) -> str:
        parts = []
        for key in ["street", "unit", "city", "state", "zip_code"]:
            val = row.get(key)
            if val:
                parts.append(str(val))
        return " ".join(parts).strip() or "Unknown"'''

new = '''    def _get_address(self, row) -> str:
        parts = []
        for key in ["street", "unit", "city", "state", "zip_code"]:
            val = row.get(key)
            if val is not None:
                try:
                    if not pd.isna(val):
                        parts.append(str(val))
                except Exception:
                    parts.append(str(val))
        return " ".join(parts).strip() or "Unknown"'''

c = c.replace(old, new)

# Fix photos extraction
old2 = '''    def _extract_photos(self, row) -> list[str]:
        photos = row.get("photos", [])
        if isinstance(photos, list):
            return photos
        if pd.isna(photos):
            return []
        return [photos]'''

new2 = '''    def _extract_photos(self, row) -> list[str]:
        photos = row.get("photos", [])
        if isinstance(photos, list):
            return photos
        try:
            if pd.isna(photos):
                return []
        except Exception:
            pass
        return [photos]'''

c = c.replace(old2, new2)

# Move pd import to top
lines = c.split('\n')
out = []
pd_found = False
for line in lines:
    if 'import pandas as pd' in line and not pd_found:
        pd_found = True
    elif 'import pandas as pd' in line and pd_found:
        continue
    out.append(line)
c = '\n'.join(out)
if not pd_found:
    c = 'import pandas as pd\n' + c

# Fix the row iteration loop - simplify baths
lines = c.split('\n')
out = []
for line in lines:
    if '"baths": float(row.get("full_baths", 0) or 0)' in line:
        out.append('                    "baths": None,')
    elif '"beds": int(row["beds"]) if row.get("beds")' in line:
        out.append('                    "beds": row.get("beds"),')
    elif '"price": int(row.get("list_price")) if row.get("list_price")' in line:
        out.append('                    "price": row.get("list_price"),')
    else:
        out.append(line)
c = '\n'.join(out)

with open(path, 'w') as f:
    f.write(c)
print('Fixed')
