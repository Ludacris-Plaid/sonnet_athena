"""Fix HomeHarvest source to convert pd.NA to None"""
path = '/home/dysthemix/realtyai/app/scrapers/homeharvest_source.py'
with open(path) as f:
    c = f.read()

# After building listing, add pd.NA → None cleanup
old = '''                    "photos": photos,
                    "year_built": int(row["year_built"]) if row.get("year_built") else None,'''
new = '''                    "photos": photos,
                    "year_built": int(row["year_built"]) if row.get("year_built") else None,
                    "garage_spaces": int(row["garage"]) if row.get("garage") else None,
                    "lot_size_sqft": int(row["lot_sqft"]) if row.get("lot_sqft") else None,'''

c = c.replace(old, new)

# Add pd.NA cleanup after the listing is built
old2 = '''                }
                        listings.append(listing)'''
new2 = '''                }
                    # Convert any pd.NA values to None for DB compatibility
                    for _k, _v in list(listing.items()):
                        if hasattr(_v, '__module__') and 'pandas' in getattr(_v, '__module__', '') and 'NA' in type(_v).__name__:
                            listing[_k] = None
                        listings.append(listing)'''

c = c.replace(old2, new2)

with open(path, 'w') as f:
    f.write(c)
print('Fixed pd.NA conversion')
