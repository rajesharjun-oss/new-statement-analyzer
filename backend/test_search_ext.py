import json
import glob
import os

def check_json():
    all_jsons = glob.glob("../**/*.json", recursive=True)
    print(f"Checking {len(all_jsons)} JSONs...")
    for j in all_jsons:
        try:
            with open(j, "r", encoding="utf-8") as f:
                data = json.load(f)
                txns = data.get("transactions", [])
                for t in txns:
                    if "EXTENSION FEE" in (t.get("description", "") or "").upper():
                        print(f"File: {j}")
                        print(f"Found: {t}")
        except Exception as e:
            pass

if __name__ == "__main__":
    check_json()
