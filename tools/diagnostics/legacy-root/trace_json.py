import json

filepath = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\6bb5b133-1f25-4b51-a58a-c3a690bafa59.phase2.raw.json"

with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

try:
    json.loads(text)
    print("Parsed successfully via file read!")
except json.JSONDecodeError as e:
    print(f"JSONDecodeError at line {e.lineno}, column {e.colno}: {e.msg}")
    
    # Show context around error
    lines = text.split('\n')
    start = max(0, e.lineno - 3)
    end = min(len(lines), e.lineno + 3)
    print("\n--- Context ---")
    for i in range(start, end):
        prefix = ">> " if i == e.lineno - 1 else "   "
        print(f"{prefix}{i+1}: {lines[i]}")
