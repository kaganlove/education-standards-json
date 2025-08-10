import json
from pathlib import Path

INDEX_DIR = Path("standards/_index")
PATH_INDEX_FILE = INDEX_DIR / "standard_set_paths.json"
FALLBACK_LOG_FILE = INDEX_DIR / "fallback_log.jsonl"

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

# Load the path index
if not PATH_INDEX_FILE.exists():
    raise FileNotFoundError(f"Missing {PATH_INDEX_FILE}, run pull_standards.py first.")
path_index = load_json(PATH_INDEX_FILE)

# Collect expected IDs from jurisdiction set files
expected_ids = set()
jur_files = list(INDEX_DIR.glob("standard_sets_*.json"))
for file in jur_files:
    if file.name.startswith("standard_sets_") and file.suffix == ".json":
        sets = load_json(file)
        for s in sets:
            if "id" in s:
                expected_ids.add(s["id"])

saved_ids = set(path_index.keys())
missing_ids = expected_ids - saved_ids

# Print summary
print("=== Standards Pull Verification ===")
print(f"Jurisdictions indexed: {len(jur_files)}")
print(f"Expected sets total:   {len(expected_ids)}")
print(f"Saved sets total:      {len(saved_ids)}")
print(f"Coverage:              {len(saved_ids) / len(expected_ids) * 100:.2f}%")

if missing_ids:
    print(f"\nMissing sets: {len(missing_ids)}")
    print("Example missing IDs:", list(missing_ids)[:10])
else:
    print("\nNo missing sets. All expected sets saved.")

# Fallback usage
if FALLBACK_LOG_FILE.exists():
    with open(FALLBACK_LOG_FILE, "r", encoding="utf-8") as fh:
        fallback_entries = [json.loads(line) for line in fh]
    print(f"\nFallback paths used: {len(fallback_entries)}")
    if fallback_entries:
        print("Example fallback:", fallback_entries[0])
else:
    print("\nNo fallback log file found (no path length issues encountered).")
