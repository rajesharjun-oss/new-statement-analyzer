import argparse
from pathlib import Path

import pdfplumber


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--rows", type=int, default=60)
    args = parser.parse_args()

    with pdfplumber.open(args.pdf) as pdf:
        page = pdf.pages[args.page - 1]
        grouped = {}
        for word in page.extract_words():
            y = round(word["top"] / 3) * 3
            grouped.setdefault(y, []).append(word)
        for y in sorted(grouped)[: args.rows]:
            parts = [
                f"{word['text']}@{word['x0']:.1f}-{word['x1']:.1f}"
                for word in sorted(grouped[y], key=lambda item: item["x0"])
            ]
            print(f"{y:>6}: " + " | ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
