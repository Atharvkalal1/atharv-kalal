"""Detector Family (a): Declarative Schema & Rule Checks."""
import re
from datetime import datetime

BOROUGH_ZIP_MAP = {
    "MANHATTAN": ("100", "101", "102"),
    "STATEN ISLAND": ("103",),
    "BRONX": ("104",),
    "QUEENS": ("110", "111", "113", "114", "116"),
    "BROOKLYN": ("112",)
}

PII_REGEX = re.compile(
    r"(\d{3}[-.\s]??\d{3}[-.\s]??\d{4})|"                  # Phone numbers
    r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)|"       # Email addresses
    r"(\d{3}-\d{2}-\d{4})"                                 # SSN
)

REQUIRED_COLUMNS = {"unique_key", "created_date", "agency", "complaint_type", "descriptor", "incident_zip", "borough", "status"}

def detect_rule_violations(record: dict) -> list[str]:
    violations = []
    
    # 1. Missing columns
    missing = REQUIRED_COLUMNS - set(record.keys())
    if missing:
        violations.append(f"a_renamed_or_dropped_column: missing {list(missing)}")
        
    # 2. Column type
    uk = record.get("unique_key")
    if uk is not None and not isinstance(uk, int):
        violations.append(f"b_column_type_change: unique_key must be int, got {type(uk).__name__}")
        
    # 3. Date format & ordering
    c_date = record.get("created_date")
    cl_date = record.get("closed_date")
    parsed_create = None
    parsed_close = None
    
    if c_date:
        if not re.match(r"^\d{4}-\d{2}-\d{2}", str(c_date)):
            violations.append("c_date_format_switch: created_date not in ISO YYYY-MM-DD format")
        else:
            try: parsed_create = datetime.strptime(str(c_date).split(".")[0], "%Y-%m-%d %H:%M:%S")
            except: pass
            
    if cl_date:
        if not re.match(r"^\d{4}-\d{2}-\d{2}", str(cl_date)):
            violations.append("c_date_format_switch: closed_date not in ISO YYYY-MM-DD format")
        else:
            try: parsed_close = datetime.strptime(str(cl_date).split(".")[0], "%Y-%m-%d %H:%M:%S")
            except: pass
            
    if parsed_create and parsed_close and parsed_close < parsed_create:
        violations.append(f"h_closed_earlier_than_created: closed {parsed_close} < created {parsed_create}")

    # 4. Lat / Lon swapped or out of NYC bounds
    lat, lon = record.get("latitude"), record.get("longitude")
    if lat is not None and lon is not None:
        # If lat is negative (around -74) and lon is positive (around 40), they are swapped!
        if lat < 0 and lon > 0:
            violations.append(f"d_lat_lon_swapped: lat={lat}, lon={lon} (NYC coords swapped)")
        elif not (40.45 <= lat <= 40.95 and -74.30 <= lon <= -73.65) and (lat != 0 or lon != 0):
            violations.append(f"lat_lon_out_of_bounds: lat={lat}, lon={lon}")

    # 5. Zip & Borough consistency
    boro = str(record.get("borough", "")).upper()
    zip_code = str(record.get("incident_zip", ""))
    if boro in BOROUGH_ZIP_MAP and len(zip_code) >= 3:
        prefix = zip_code[:3]
        valid_prefixes = BOROUGH_ZIP_MAP[boro]
        if not any(prefix.startswith(vp) for vp in valid_prefixes):
            violations.append(f"i_zip_inconsistent_borough: zip {zip_code} invalid for borough {boro}")

    # 6. PII detection in free text
    for text_field in ("descriptor", "resolution_description"):
        val = str(record.get(text_field, ""))
        if PII_REGEX.search(val):
            violations.append(f"l_pii_in_free_text: PII detected in {text_field}")

    return violations
