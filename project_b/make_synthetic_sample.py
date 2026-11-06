"""Builds a SYNTHETIC stand-in for NYC 311 2023 so the whole repo runs offline. It is NOT real data and every report says so.
Natural noise (null coordinates, 'Unspecified' borough, a few closed<created rows, open tickets with text) is seeded at documented
rates so false-alarm rates are not trivially zero. Real data: python -m project_b.fetch_nyc311
    python -m project_b.make_synthetic_sample [--n 12000]"""
import json, random, sys
from datetime import datetime, timedelta
from project_b.common import SYNTH_FILE, ZIP_RANGES

AGENCIES = {  # agency: (name, [(complaint_type, [descriptors])])
 "NYPD": ("New York City Police Department", [("Noise - Residential", ["Loud Music/Party", "Banging/Pounding", "Loud Talking"]),
          ("Illegal Parking", ["Blocked Hydrant", "Double Parked Blocking Traffic", "Blocked Sidewalk"]), ("Blocked Driveway", ["No Access", "Partial Access"])]),
 "HPD": ("Department of Housing Preservation and Development", [("HEAT/HOT WATER", ["ENTIRE BUILDING", "APARTMENT ONLY"]),
          ("PLUMBING", ["BATHROOM", "KITCHEN", "TOILET"]), ("PAINT/PLASTER", ["WALLS", "CEILING"])]),
 "DSNY": ("Department of Sanitation", [("Missed Collection", ["Trash", "Recycling", "Organics"]), ("Dirty Conditions", ["Trash", "Sidewalk"]),
          ("Sanitation Condition", ["Overflowing Litter Basket", "Garbage Collection"])]),
 "DOT": ("Department of Transportation", [("Street Condition", ["Pothole", "Cave-in", "Rough, Pitted or Cracked Roads"]),
          ("Traffic Signal Condition", ["Controller", "Signal Out"]), ("Street Light Condition", ["Street Light Out", "Lamppost Damaged"])]),
 "DEP": ("Department of Environmental Protection", [("Water System", ["Leak", "No Water", "Low Pressure"]), ("Sewer", ["Catch Basin Clogged", "Sewer Backup"])]),
 "DPR": ("Department of Parks and Recreation", [("Damaged Tree", ["Branch or Limb Has Fallen Down", "Tree Leaning/Uprooted"]), ("Overgrown Tree/Branches", ["Blocking Street", "Blocking Sidewalk"])]),
}
CLOSED_TXT = {"NYPD": ["The Police Department responded to the complaint and took action to fix the condition.",
                       "The Police Department responded to the complaint and with the information available observed no evidence of the violation at that time.",
                       "The Police Department issued a summons."],
              "HPD": ["The Department of Housing Preservation and Development inspected the property and the condition was corrected.",
                      "HPD inspected the location and did not find a violation.", "The owner certified that the condition was corrected."],
              "DSNY": ["The Department of Sanitation collected the material.", "The Department of Sanitation inspected and found no violation.", "Sanitation crew cleaned the location."],
              "DOT": ["The Department of Transportation repaired the condition.", "DOT inspected and the condition did not need repair.", "The signal was fixed by DOT crews."],
              "DEP": ["The Department of Environmental Protection completed the repair.", "DEP inspected and found no leak."],
              "DPR": ["The Department of Parks and Recreation pruned the tree.", "Parks inspected and no action was required."]}
OPEN_TXT = ["Your request has been received and is being reviewed.", "The agency has been notified and will respond.", None]
BORO = {"MANHATTAN": (40.70, 40.88, -74.02, -73.91), "BRONX": (40.79, 40.91, -73.93, -73.77), "BROOKLYN": (40.57, 40.74, -74.04, -73.86),
        "QUEENS": (40.55, 40.79, -73.96, -73.70), "STATEN ISLAND": (40.50, 40.64, -74.25, -74.05)}


def build(n=12000, seed=2023):
    r = random.Random(seed); rows = []
    for i in range(n):
        ag = r.choices(list(AGENCIES), weights=[30, 22, 15, 14, 9, 10])[0]; name, cts = AGENCIES[ag]
        ct, descs = r.choice(cts); boro = r.choices(list(BORO), weights=[24, 20, 28, 23, 5])[0]
        rng = r.choice(ZIP_RANGES[boro]); z = str(r.randint(*rng))
        a, b, lo, hi = BORO[boro]; lat, lon = round(r.uniform(a, b), 6), round(r.uniform(lo, hi), 6)
        created = datetime(2023, 1, 1) + timedelta(seconds=r.randint(0, 365 * 86400 - 1))
        status = r.choices(["Closed", "Open", "In Progress", "Assigned", "Pending", "Started"], weights=[88, 4, 3, 2, 2, 1])[0]
        closed = None if status != "Closed" else created + timedelta(seconds=int(r.lognormvariate(11, 1.3)))
        if status == "Closed" and r.random() < 0.004: closed = created - timedelta(seconds=r.randint(60, 86400))      # natural noise
        res = r.choice(CLOSED_TXT[ag]) if status == "Closed" else r.choice(OPEN_TXT)
        if r.random() < 0.03: lat = lon = None                                                                       # natural noise
        if r.random() < 0.02: boro = "Unspecified"
        if r.random() < 0.01: z = None
        rows.append({"unique_key": 58000000 + i * 7 + r.randint(0, 6), "created_date": created.strftime("%Y-%m-%dT%H:%M:%S.000"),
                     "closed_date": closed.strftime("%Y-%m-%dT%H:%M:%S.000") if closed else None, "agency": ag, "agency_name": name,
                     "complaint_type": ct, "descriptor": r.choice(descs), "incident_zip": z, "borough": boro, "status": status,
                     "resolution_description": res, "latitude": lat, "longitude": lon})
    rows.sort(key=lambda x: x["created_date"])
    return rows


if __name__ == "__main__":
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 12000
    SYNTH_FILE.parent.mkdir(exist_ok=True)
    SYNTH_FILE.write_text("\n".join(json.dumps(x) for x in build(n)))
    print(f"wrote {n} SYNTHETIC rows -> {SYNTH_FILE}")
