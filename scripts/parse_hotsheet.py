import anthropic
import base64
import json
import os
from datetime import date
from pathlib import Path

PDF_PATH = os.environ.get("PDF_PATH")
DATA_FILE = Path("data/prices.json")

def parse_pdf(pdf_path: str) -> list:
    client = anthropic.Anthropic()
    with open(pdf_path, "rb") as f:
        pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")

    print(f"Sending {pdf_path} to Anthropic API...")
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=8000,
        system="""You are a data extraction assistant. Extract all material prices from this electrical supply hot sheet PDF.
Return ONLY a JSON array, no markdown, no explanation. Each object must have exactly these fields:
- "name": string (item name as shown, e.g. "THHN 14 BLK SOL CU")
- "category": string — assign one of: THHN, NM-B, MC Cable, XHHW, EMT, Galv, PVC, IMC, Alum, Fittings, Bare Copper
- "price": number (numeric value only, no $ sign)
Do not include any text before or after the JSON array.""",
        messages=[
            {
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
                        "text": "Extract all items and prices from this hot sheet. Return JSON array only."
                    }
                ],
            }
        ],
    )

    raw = message.content[0].text.strip()
    clean = raw.replace("```json", "").replace("```", "").strip()
    items = json.loads(clean)
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
    """Move PDF from inbox/ to inbox/processed/ so it doesn't retrigger"""
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

    today = date.today().isoformat()
    items = parse_pdf(PDF_PATH)

    history = load_history()
    # Remove any existing entry for today
    history = [s for s in history if s.get("date") != today]
    history.append({
        "date": today,
        "source": Path(PDF_PATH).name,
        "items": items
    })
    # Keep sorted by date
    history.sort(key=lambda x: x["date"])

    save_history(history)
    archive_pdf(PDF_PATH)
    print(f"Done — {len(items)} prices saved for {today}")


if __name__ == "__main__":
    main()
