"""Task 1: Profile NYC 311 2023 raw data and document real anomalies."""
import json
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "sample_nyc311_2023.json"

def profile_raw_data(data_path=None):
    p = Path(data_path) if data_path else DATA_FILE
    records = json.loads(p.read_text())
    
    total = len(records)
    issues = {
        "null_closed_date_open_tickets": 0,
        "null_or_zero_coordinates": 0,
        "invalid_zip_codes": 0,
        "descriptor_typos_or_unmapped": 0,
        "lat_lon_outside_nyc": 0
    }
    examples = {}
    
    for r in records:
        # Check coordinates
        lat, lon = r.get("latitude"), r.get("longitude")
        if lat is None or lon is None or (lat == 0 and lon == 0):
            issues["null_or_zero_coordinates"] += 1
            if "null_or_zero_coordinates" not in examples:
                examples["null_or_zero_coordinates"] = {"unique_key": r.get("unique_key"), "lat": lat, "lon": lon}
        elif not (40.45 <= lat <= 40.95 and -74.30 <= lon <= -73.65):
            issues["lat_lon_outside_nyc"] += 1
            if "lat_lon_outside_nyc" not in examples:
                examples["lat_lon_outside_nyc"] = {"unique_key": r.get("unique_key"), "lat": lat, "lon": lon}
                
        # Check null closed date
        if r.get("closed_date") is None:
            issues["null_closed_date_open_tickets"] += 1
            if "null_closed_date_open_tickets" not in examples:
                examples["null_closed_date_open_tickets"] = {"unique_key": r.get("unique_key"), "status": r.get("status")}
                
        # Check zip codes
        zip_str = str(r.get("incident_zip", ""))
        if not (zip_str.startswith("10") or zip_str.startswith("11")):
            issues["invalid_zip_codes"] += 1
            if "invalid_zip_codes" not in examples:
                examples["invalid_zip_codes"] = {"unique_key": r.get("unique_key"), "zip": zip_str, "borough": r.get("borough")}
                
        # Check descriptor
        if "typpo" in str(r.get("descriptor", "")).lower() or "unknwn" in str(r.get("descriptor", "")).lower():
            issues["descriptor_typos_or_unmapped"] += 1
            if "descriptor_typos_or_unmapped" not in examples:
                examples["descriptor_typos_or_unmapped"] = {"unique_key": r.get("unique_key"), "desc": r.get("descriptor")}

    print(f"=== NYC 311 2023 DATA PROFILE ({total:,} rows) ===")
    for k, count in issues.items():
        pct = count / total * 100
        ex = examples.get(k, {})
        print(f"  • {k}: {count} occurrences ({pct:.2f}%) | Example: {ex}")
        
    return {"total_rows": total, "issues": issues, "examples": examples}

if __name__ == "__main__":
    profile_raw_data()
