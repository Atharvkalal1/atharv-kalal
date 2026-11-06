"""Task 2: Controlled Corruption Injector for 12 data quality problem types."""
import copy, random, re
from datetime import datetime

BOROUGH_ZIP_PREFIXES = {
    "MANHATTAN": ("100", "101", "102"),
    "STATEN ISLAND": ("103",),
    "BRONX": ("104",),
    "QUEENS": ("110", "111", "113", "114", "116"),
    "BROOKLYN": ("112",)
}

class CorruptionInjector:
    def __init__(self, seed=42):
        self.rnd = random.Random(seed)
        
    def inject(self, records: list[dict], rate=0.05) -> tuple[list[dict], list[dict]]:
        corrupted = copy.deepcopy(records)
        ground_truth = []
        n = len(corrupted)
        k = max(1, int(n * rate))
        
        # Select indices for each corruption
        # We test 12 problems (a through l)
        problem_names = [
            "a_renamed_or_dropped_column",
            "b_column_type_change",
            "c_date_format_switch",
            "d_lat_lon_swapped",
            "e_exact_duplicates",
            "f_near_duplicates",
            "g_null_spike_agency",
            "h_closed_earlier_than_created",
            "i_zip_inconsistent_borough",
            "j_complaint_inconsistent_descriptor",
            "k_resolution_contradicts_status",
            "l_pii_in_free_text"
        ]
        
        # Track ground truth per row
        row_truth = {i: [] for i in range(n)}
        
        # (a) Renamed or dropped column
        for i in self.rnd.sample(range(n), k):
            if "agency" in corrupted[i]:
                corrupted[i]["agency_code_dropped"] = corrupted[i].pop("agency")
                row_truth[i].append("a_renamed_or_dropped_column")
                
        # (b) Column type change (unique_key int -> string or vice-versa)
        for i in self.rnd.sample(range(n), k):
            corrupted[i]["unique_key"] = f"KEY_{corrupted[i]['unique_key']}"
            row_truth[i].append("b_column_type_change")
            
        # (c) Date format switch partway through batch (YYYY-MM-DD -> MM/DD/YYYY)
        for i in self.rnd.sample(range(n), k):
            dt = corrupted[i]["created_date"]
            if dt and "-" in dt:
                parts = dt.split(" ")[0].split("-")
                time_part = dt.split(" ")[1] if " " in dt else "00:00:00"
                corrupted[i]["created_date"] = f"{parts[1]}/{parts[2]}/{parts[0]} {time_part}"
                row_truth[i].append("c_date_format_switch")

        # (d) Lat and Long swapped
        for i in self.rnd.sample(range(n), k):
            lat, lon = corrupted[i]["latitude"], corrupted[i]["longitude"]
            corrupted[i]["latitude"], corrupted[i]["longitude"] = lon, lat
            row_truth[i].append("d_lat_lon_swapped")

        # (e) Exact duplicates
        dup_targets = self.rnd.sample(range(n), k)
        for i in dup_targets:
            source = self.rnd.choice([j for j in range(n) if j not in dup_targets])
            corrupted[i] = copy.deepcopy(corrupted[source])
            row_truth[i].append("e_exact_duplicates")

        # (f) Near duplicates (same request, slightly altered timestamp or text)
        for i in self.rnd.sample(range(n), k):
            source = self.rnd.choice(range(n))
            corrupted[i] = copy.deepcopy(corrupted[source])
            val = int(re.sub(r"\D", "", str(corrupted[i]["unique_key"]))) if re.sub(r"\D", "", str(corrupted[i]["unique_key"])) else 1234567
            corrupted[i]["unique_key"] = val + 999000
            corrupted[i]["descriptor"] = corrupted[i]["descriptor"] + " - Near Duplicate Copy"
            row_truth[i].append("f_near_duplicates")

        # (g) Null spike in one agency records (e.g. DSNY)
        for i in range(n):
            if corrupted[i].get("agency") == "DSNY" and self.rnd.random() < 0.60:
                corrupted[i]["agency"] = None
                row_truth[i].append("g_null_spike_agency")

        # (h) Closed date earlier than created date
        for i in self.rnd.sample(range(n), k):
            corrupted[i]["created_date"] = "2023-08-15 14:00:00"
            corrupted[i]["closed_date"] = "2023-08-10 09:00:00" # 5 days earlier!
            row_truth[i].append("h_closed_earlier_than_created")

        # (i) ZIP code inconsistent with Borough
        for i in self.rnd.sample(range(n), k):
            corrupted[i]["borough"] = "MANHATTAN"
            corrupted[i]["incident_zip"] = "11201" # Brooklyn ZIP in Manhattan
            row_truth[i].append("i_zip_inconsistent_borough")

        # (j) Complaint Type inconsistent with Descriptor
        for i in self.rnd.sample(range(n), k):
            corrupted[i]["complaint_type"] = "Noise - Residential"
            corrupted[i]["descriptor"] = "Pothole in roadway near intersection"
            row_truth[i].append("j_complaint_inconsistent_descriptor")

        # (k) Resolution Description contradicting Status
        for i in self.rnd.sample(range(n), k):
            corrupted[i]["status"] = "Closed"
            corrupted[i]["resolution_description"] = "The inspector has not visited yet. The case is actively open and pending investigation."
            row_truth[i].append("k_resolution_contradicts_status")

        # (l) Personal data (phone numbers, emails, names) in free text
        pii_samples = [
            "Contact John Doe directly at john.doe@gmail.com or call 212-555-0199 for access.",
            "Caller Jane Smith SSN: 000-12-3456 requested call back at 917-555-8822.",
            "Please reach tenant Amit Kumar at amit_k@yahoo.com regarding keys."
        ]
        for i in self.rnd.sample(range(n), k):
            corrupted[i]["resolution_description"] = self.rnd.choice(pii_samples)
            row_truth[i].append("l_pii_in_free_text")

        for i in range(n):
            ground_truth.append({
                "row_index": i,
                "unique_key": corrupted[i].get("unique_key"),
                "is_corrupted": len(row_truth[i]) > 0,
                "corruption_types": row_truth[i]
            })
            
        print(f"Injected corruptions into batch of {n} rows at rate {rate*100:.1f}%.")
        return corrupted, ground_truth

if __name__ == "__main__":
    from project_b.profiler import DATA_FILE
    records = json.loads(DATA_FILE.read_text())[:200]
    inj = CorruptionInjector()
    c_records, gt = inj.inject(records, rate=0.05)
    corrupted_count = sum(1 for g in gt if g["is_corrupted"])
    print(f"Sample test: {corrupted_count}/{len(records)} rows corrupted.")
