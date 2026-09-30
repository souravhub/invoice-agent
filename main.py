"""
STEP 3: Run it.
Usage:  python main.py sample_invoice.pdf
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from workflow import build_graph, provider_and_model, run_dir

load_dotenv()  # reads OPENAI_API_KEY from .env


def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "sample_invoice.pdf"
    app = build_graph()
    result = app.invoke({"pdf_path": pdf_path})

    invoice = result["invoice"]
    print(json.dumps(invoice.model_dump(), indent=2))

    # The verdict: either it can be processed automatically, or a human must look at it.
    status = result["status"]
    reasons = result["reasons"]
    print("\n" + "=" * 60)
    print(f"STATUS: {status.upper().replace('_', ' ')}   (attempts used: {result['attempts']})")
    if reasons:
        print("Reasons a human must review it:")
        for r in reasons:
            print(f"  - {r}")
    print("=" * 60)

    # Saved in the same shape and the same per-model folder that evaluate.py uses, so results
    # from different providers/models never overwrite each other.
    provider, model = provider_and_model()
    output = {
        "provider": provider,
        "model": model,
        "status": status,
        "reasons": reasons,
        "attempts": result["attempts"],
        **invoice.model_dump(),
    }
    out = run_dir() / (Path(pdf_path).stem + "_extracted.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
