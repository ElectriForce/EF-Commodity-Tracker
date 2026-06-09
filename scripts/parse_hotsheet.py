
import anthropic
import base64
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

PDF_PATH = os.environ.get("PDF_PATH")
DATA_FILE = Path("data/prices.json")

def extract_date_from_filename(filename: str) -> str:
    """
    Try to extract a date from the filename.
    Supports formats like:
      6-2-26, 06-02-26, 6-2-2026, 06-02-2026
      5-26-26, 5-5-26, etc.
    Falls back to today if no date found.
    """
    name = Path(filename).stem  # strip extension
    # Match patterns like 6-2-26 or 6-2-2026 or 06-02-26
    match = re.search(r'(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})', name)
    if match:
        m, d, y = match.groups()
        y = int(y)
        if y < 100:
            y += 2000
        try:
            parsed = datetime(y, int(m), int(d))
            result = parsed.strftime('%Y-%m-%d')
            print(f"Extracted date from filename: {result}")
            return result
        except ValueError:
            pass
    today = date.today().isoformat()
    print(f"No date found in filename, using today: {today}")
    return today


def parse_pdf(pdf_path: str) -> list:
    client = anthropic.Anthropic()
    with open(pdf_path, "rb") as f:
        pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")

    print(f"Sending {pdf_path} to Anthropic API...")

    # Pass 1: extract all text from the PDF
    text_response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_data,
                    },
                },
                {
                    "type": "text",
                    "text": "List every single item and price from this electrical supply price sheet. Format each line exactly as: ITEM NAME | PRICE\nInclude every item. Do not skip any. Do not add any other text."
                }
            ],
        }]
    )

    raw_text = text_response.content[0].text.strip()
    print(f"Got raw text ({len(raw_text)} chars), now structuring...")

    # Pass 2: structure into JSON
    json_response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=16000,
        system="""Convert the provided price list into a JSON array. Each object must have exactly:
- "name": string (item name)
- "category": one of: THHN, NM-B, MC Cable, XHHW, EMT, Galv, PVC, IMC, Alum, Fittings, Bare Copper
- "price": number (no $ sign)

Categorize based on item name:
- THHN → category THHN
- NM-B → category NM-B
- MCA or HCA → category MC Cable
- XHHW → category XHHW
- EMT conduit/couplings/connectors/elbows → category EMT
- GAL → category Galv
- PVC-Sched → category PVC
- IMC → category IMC
- ALU → category Alum
- Bare or bare copper → category Bare Copper
- SS COUP, CMP COUP, SS CONN, CMP CONN → category Fittings

Return ONLY the JSON array. No markdown, no explanation, no extra text.""",
        messages=[{
            "role": "user",
            "content": f"Convert this price list to JSON:\n\n{raw_text}"
        }]
    )

    raw = json_response.content[0].text.strip()
    clean = raw.replace("```json", "").replace("```", "").strip()

    start = clean.find('[')
    end = clean.rfind(']')
    if start == -1 or end == -1:
        raise ValueError(f"No JSON array found in response. Got: {clean[:200]}")

    items = json.loads(clean[start:end+1])
    print(f"Extracted {len(items)} items")
    return items


def load_history() -> list:
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return []


def save_history(history: list):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(history, f, indent=2)
    print(f"Saved {len(history)} snapshots to {DATA_FILE}")


def archive_pdf(pdf_path: str):
    src = Path(pdf_path)
    dest_dir = Path("inbox/processed")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    src.rename(dest)
    print(f"Archived {src.name} to inbox/processed/")


def main():
    if not PDF_PATH:
        print("No PDF_PATH set")
        return

    snapshot_date = extract_date_from_filename(PDF_PATH)
    items = parse_pdf(PDF_PATH)

    history = load_history()
    history = [s for s in history if s.get("date") != snapshot_date]
    history.append({
        "date": snapshot_date,
        "source": Path(PDF_PATH).name,
        "items": items
    })
    history.sort(key=lambda x: x["date"])

    save_history(history)
    archive_pdf(PDF_PATH)
    print(f"Done — {len(items)} prices saved for {snapshot_date}")


if __name__ == "__main__":
    main()
