import json, os, pathlib, datetime

repo = pathlib.Path(__file__).resolve().parent

# create standards/common-core/math if it doesn't exist
out_dir = repo / "standards" / "common-core" / "math"
out_dir.mkdir(parents=True, exist_ok=True)

payload = {
    "framework": "Common Core",
    "subject": "math",
    "grade": "grade-8",
    "version": datetime.date.today().isoformat(),
    "source": "https://www.corestandards.org/Math/Content/",
    "standards": [
        {
            "code": "8.EE.A.1",
            "statement": "[PLACEHOLDER] Know and apply properties of integer exponents to generate equivalent numerical expressions.",
            "notes": "Expressions & Equations",
            "tags": ["exponents","EE"]
        }
    ]
}

out_path = out_dir / "grade-8.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

print("Wrote:", out_path)
