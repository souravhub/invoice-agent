"""
STEP 4: Measure how accurate the workflow is.
Usage:  python evaluate.py

Runs every PDF in invoices/ through the workflow, compares the result to the
matching answer key in answer_keys/, and writes results/evaluation_report_<provider>_<model>.md.
"""
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .agent.workflow import STATUS_AUTO_APPROVED, build_graph, provider_and_model, run_dir, run_slug

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / "backend" / ".env")

INVOICES_DIR = PROJECT_ROOT / "invoices"
KEYS_DIR = PROJECT_ROOT / "answer_keys"
RESULTS_DIR = PROJECT_ROOT / "results"
DELAY_SECONDS = 5           # pause between invoices to stay under free-tier rate limits
RATE_LIMIT_WAIT = 60        # fallback wait before retrying an invoice that hit a rate limit
RATE_LIMIT_RETRIES = 3      # how many times to retry such an invoice
RATE_LIMIT_MAX_WAIT = 150   # never wait longer than this for one retry
ABORT_AFTER = 2             # give up the whole run after this many invoices in a row are rate limited


def suggested_wait(message):
    """
    Gemini and OpenAI both say how long to wait ("Please retry in 11.47s", "retryDelay: 11s").
    Honouring that is far better than guessing: a per-minute limit clears in seconds, while an
    exhausted daily quota will not clear at all, and blind backoff just wastes minutes.
    """
    found = re.findall(r"retry in ([\d.]+)\s*s|retryDelay['\"]?:?\s*['\"]?(\d+)s", message, re.I)
    values = [float(a or b) for a, b in found]
    return min(max(values), RATE_LIMIT_MAX_WAIT) if values else None


def looks_like_rate_limit(message):
    """True for 'too many requests' style errors, which are worth retrying after a wait.
    An empty-wallet error (OpenAI's insufficient_quota) is NOT retryable, so it is excluded."""
    m = message.lower()
    if "insufficient_quota" in m or "insufficient quota" in m:
        return False
    return any(s in m for s in ("429", "rate limit", "ratelimit", "resource exhausted",
                                "resource_exhausted", "too many requests", "quota exceeded"))

# discount and shipping were added on 2026-09-28, taking the graded fields from 9 to 11.
# Reports from before that date have totals out of 9 per invoice, so compare percentages
# rather than raw counts when looking at an older report.
FIELDS = ["vendor_name", "invoice_number", "invoice_date", "po_number", "currency",
          "line_items", "subtotal", "discount", "shipping", "tax", "total"]
BASELINE_FIELD_COUNT = 9  # what the pre-fix baseline report graded, for the note in the report
TEXT_FIELDS = {"vendor_name", "invoice_number", "po_number", "currency"}
NUMBER_FIELDS = {"subtotal", "discount", "shipping", "tax", "total"}

# Every invoice lands in exactly one of these four buckets: what the agent decided
# (auto_approved / needs_review) crossed with whether it was actually right.
BUCKETS = {
    "clean_pass": "Passed configured checks and every field was correct. No human check was requested.",
    "silent_error": "Passed configured checks but at least one field was wrong. A wrong result looked confident.",
    "caught": "Sent for review and at least one field wrong. The agent caught its own mistake.",
    "over_cautious": "Sent for review but actually every field was correct. Safe, but wastes a human's time.",
}


# ---------- Comparison rules ----------
def normalize_text(value):
    """Lowercase, drop punctuation, collapse spaces. Empty text counts as null."""
    if value is None:
        return None
    text = re.sub(r"[^\w\s]", "", str(value).lower())
    return " ".join(text.split()) or None


def numbers_match(expected, actual):
    if expected is None or actual is None:
        return expected is None and actual is None
    return abs(float(expected) - float(actual)) <= 0.01 + 1e-9  # tiny extra for float rounding


def line_items_match(expected, actual):
    """Correct only if the item count matches and every item's amount matches (in order)."""
    exp = [li.get("amount") for li in expected or []]
    act = [li.get("amount") for li in actual or []]
    return len(exp) == len(act) and all(numbers_match(e, a) for e, a in zip(exp, act))


def field_matches(field, expected, actual):
    if field in TEXT_FIELDS:
        return normalize_text(expected) == normalize_text(actual)
    if field in NUMBER_FIELDS:
        return numbers_match(expected, actual)
    if field == "line_items":
        return line_items_match(expected, actual)
    return expected == actual  # invoice_date: exact match (null == null)


def show(field, value):
    """How a value is displayed in the mismatch list."""
    if field == "line_items":
        items = value or []
        return f"{len(items)} items, amounts {[li.get('amount') for li in items]}"
    return json.dumps(value, ensure_ascii=False)


# ---------- Run one invoice ----------
def bucket_of(row):
    """Which of the four outcome buckets this invoice falls into."""
    if row["error"]:
        return "failed"  # no measurement at all, so it is kept out of the four buckets
    auto_approved = row["status"] == STATUS_AUTO_APPROVED
    all_correct = row["fully_correct"]
    if auto_approved:
        return "clean_pass" if all_correct else "silent_error"
    return "over_cautious" if all_correct else "caught"


def evaluate_invoice(app, pdf_path, expected):
    row = {"name": pdf_path.stem, "expected": expected, "actual": None, "error": None,
           "attempts": None, "status": None, "reasons": [], "rate_limit_retries": 0,
           "rate_limited": False}

    for try_number in range(RATE_LIMIT_RETRIES + 1):
        try:
            result = app.invoke({"pdf_path": str(pdf_path)})
            row["actual"] = result["invoice"].model_dump()
            row["attempts"] = result.get("attempts")
            row["status"] = result.get("status")
            row["reasons"] = result.get("reasons") or []
            row["error"] = None
            provider, model = provider_and_model()
            saved = {"provider": provider, "model": model, "status": row["status"],
                     "reasons": row["reasons"], "attempts": row["attempts"], **row["actual"]}
            with open(run_dir() / f"{pdf_path.stem}_extracted.json", "w", encoding="utf-8") as f:
                json.dump(saved, f, indent=2, ensure_ascii=False)
            break
        except Exception as e:
            message = f"{type(e).__name__}: {e}"
            row["error"] = message if len(message) <= 300 else message[:300] + "..."
            row["status"] = "failed"  # a crash is visible, so it counts as "not auto approved"
            row["rate_limited"] = looks_like_rate_limit(message)
            if row["rate_limited"] and try_number < RATE_LIMIT_RETRIES:
                row["rate_limit_retries"] += 1
                # Use the wait the server asked for; fall back to 60s, 120s, 240s ... if it said nothing.
                wait = suggested_wait(message) or RATE_LIMIT_WAIT * (2 ** try_number)
                print(f"        rate limit hit; waiting {wait:.0f}s and retrying "
                      f"({row['rate_limit_retries']}/{RATE_LIMIT_RETRIES})", flush=True)
                time.sleep(wait)
                continue
            break  # a real failure, or retries used up

    return grade(row, expected)


def grade(row, expected):
    """Compare one result against its answer key and work out its bucket."""
    actual = row["actual"]
    row["checks"] = {f: actual is not None and field_matches(f, expected.get(f), actual.get(f))
                     for f in FIELDS}
    row["wrong_fields"] = [f for f in FIELDS if not row["checks"][f]]
    row["fully_correct"] = not row["wrong_fields"]
    row["bucket"] = bucket_of(row)
    return row


def load_saved_row(pdf_path, expected):
    """
    --reuse: grade a result saved by an earlier run instead of calling the model again.
    Only results from the SAME provider and model are reused; a result from another model
    would quietly mix two systems into one score.
    """
    path = run_dir() / f"{pdf_path.stem}_extracted.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        saved = json.load(f)
    provider, model = provider_and_model()
    if (saved.get("provider"), saved.get("model")) != (provider, model):
        return None  # saved by a different provider/model: re-run it instead
    meta = ("provider", "model", "status", "reasons", "attempts")
    row = {"name": pdf_path.stem, "expected": expected, "error": None, "rate_limit_retries": 0,
           "reused": True, "status": saved.get("status"), "reasons": saved.get("reasons") or [],
           "attempts": saved.get("attempts"),
           "actual": {k: v for k, v in saved.items() if k not in meta}}
    return grade(row, expected)


# ---------- Build the report ----------
def pct(part, whole):
    return f"{part / whole:.1%}" if whole else "n/a"


def build_report(rows, not_run=0):
    provider, model = provider_and_model()

    # A run that crashed (rate limit, bad key) measured nothing, so it is reported
    # separately instead of being mixed into the accuracy numbers.
    failed_rows = [r for r in rows if r["error"]]
    measured = [r for r in rows if not r["error"]]
    n = len(measured)

    auto_rows = [r for r in measured if r["status"] == STATUS_AUTO_APPROVED]
    review_count = n - len(auto_rows)
    counts = {b: sum(1 for r in measured if r["bucket"] == b) for b in BUCKETS}
    silent_rows = [r for r in measured if r["bucket"] == "silent_error"]

    total_correct = sum(sum(r["checks"].values()) for r in measured)
    total_checks = n * len(FIELDS)
    auto_correct = sum(sum(r["checks"].values()) for r in auto_rows)
    auto_checks = len(auto_rows) * len(FIELDS)

    lines = [
        "# Invoice Extraction Evaluation", "",
        f"- Run at: {datetime.now():%Y-%m-%d %H:%M}",
        f"- Provider / model: {provider} / {model}",
        f"- Fields graded per invoice: {len(FIELDS)}"
        + (f" (was {BASELINE_FIELD_COUNT} before `discount` and `shipping` were added, so field "
           f"counts in older reports are out of {BASELINE_FIELD_COUNT} per invoice; compare the "
           "percentages, and the bucket and silent-error numbers, which are per invoice and stay "
           "comparable)" if len(FIELDS) != BASELINE_FIELD_COUNT else ""),
        f"- Invoices evaluated: {len(rows)}"
        + (f" ({n} produced a result, {len(failed_rows)} failed to run)" if failed_rows else ""),
        f"- Graded from results saved by an earlier run (no new API call): "
        f"{sum(1 for r in rows if r.get('reused'))}",
        *([f"- **Run stopped early: {not_run} invoice(s) were never attempted** (the API kept "
           "refusing with rate-limit errors), so this report does not cover the whole test set."]
          if not_run else []), "",
        "## How to read this report", "",
        "The agent gives every invoice a verdict: **auto_approved** (passed its configured checks; "
        "not payment authorization) or **needs_review** (a human must look at it). Accuracy alone "
        "does not tell you whether "
        "those verdicts can be trusted, so each invoice is also placed in one of four buckets.",
        "",
        "**A silent error is a wrong result that the agent passed on as confident.** Nobody is "
        "asked to check it, so the mistake goes straight into the business as if it were correct. "
        "This is the most important number for client trust: an invoice sent for review costs a "
        "few minutes of someone's time, but a silent error can mean paying the wrong amount. "
        "Being over-cautious is inconvenient; a silent error is a real loss.",
        "",
        "## Headline numbers", "",
        "| Measure | Value | Meaning |",
        "|---|---|---|",
        f"| **Silent error rate** | **{pct(len(silent_rows), n)}** ({len(silent_rows)}/{n}) | "
        "Wrong, and nobody was told. Keep this as close to 0% as possible. |",
        f"| Escalation rate | {pct(review_count, n)} ({review_count}/{n}) | "
        "Share of invoices sent for human review. |",
        f"| Field accuracy, all invoices | {pct(total_correct, total_checks)} "
        f"({total_correct}/{total_checks}) | Every field on every invoice. |",
        f"| Field accuracy, auto-approved only | {pct(auto_correct, auto_checks)} "
        f"({auto_correct}/{auto_checks}) | How good the data is that goes through unchecked. |",
        f"| Runs that failed | {len(failed_rows)}/{len(rows)} | Could not be measured (see the table "
        "below); left out of every number above. |",
        "",
        "## Outcome buckets", "",
        "| Bucket | Count | Share | What it means |",
        "|---|---|---|---|",
    ]
    for b, meaning in BUCKETS.items():
        label = f"**{b}**" if b == "silent_error" else b
        lines.append(f"| {label} | {counts[b]}/{n} | {pct(counts[b], n)} | {meaning} |")

    lines += [
        "", "## Silent errors (auto approved but wrong)", "",
    ]
    if not silent_rows:
        lines.append("None. Every auto-approved invoice was fully correct.")
    else:
        for r in silent_rows:
            lines.append(f"### {r['name']}")
            for f in r["wrong_fields"]:
                lines.append(f"- **{f}**: expected `{show(f, r['expected'].get(f))}`, "
                             f"got `{show(f, r['actual'].get(f))}`")
            lines.append("")

    lines += [
        "", "## Accuracy by field", "",
        "| Field | Correct | Accuracy |",
        "|---|---|---|",
    ]
    total_correct = 0
    for f in FIELDS:
        correct = sum(r["checks"][f] for r in measured)
        total_correct += correct
        lines.append(f"| {f} | {correct}/{n} | {correct / n:.1%} |")
    total_checks = n * len(FIELDS)
    lines.append(f"| **Overall** | **{total_correct}/{total_checks}** | **{total_correct / total_checks:.1%}** |")

    lines += ["", "## Per-invoice results", "",
              "| Invoice | Status | Bucket | Fields correct | Attempts | Notes |",
              "|---|---|---|---|---|---|"]
    for r in rows:
        correct = sum(r["checks"].values())
        if r["error"]:
            note = "ERROR: " + r["error"].replace("|", "/").replace("\n", " ")
        elif r["reasons"]:
            note = "Reasons: " + "; ".join(r["reasons"])
        else:
            note = "-"
        if r.get("rate_limit_retries"):
            outcome = "still failed" if r["error"] else "then succeeded"
            note += f" [{r['rate_limit_retries']} rate-limit retries, {outcome}]"
        if r.get("reused"):
            note += " [graded from a saved result, no new API call]"
        lines.append(f"| {r['name']} | {r['status']} | {r['bucket']} | {correct}/{len(FIELDS)} | "
                     f"{r['attempts'] or '-'} | {note} |")

    lines += ["", "## All mismatches", ""]
    any_mismatch = False
    for r in rows:
        wrong = [f for f in FIELDS if not r["checks"][f]]
        if not wrong:
            continue
        any_mismatch = True
        lines.append(f"### {r['name']}")
        if r["error"]:
            lines += ["- The workflow failed, so every field counts as wrong.", ""]
            continue
        for f in wrong:
            lines.append(f"- **{f}**: expected `{show(f, r['expected'].get(f))}`, "
                         f"got `{show(f, r['actual'].get(f))}`")
        lines.append("")
    if not any_mismatch:
        lines.append("None. Every field matched on every invoice.")
    return "\n".join(lines) + "\n"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # so €/£ print safely on Windows
    RESULTS_DIR.mkdir(exist_ok=True)
    pdfs = sorted(INVOICES_DIR.glob("*.pdf"))
    app = build_graph()

    reuse = "--reuse" in sys.argv  # grade saved results where they exist, call the API only where missing
    rows = []
    called_api = False
    stopped_early = 0  # invoices never attempted because the run gave up on rate limits
    for i, pdf in enumerate(pdfs, start=1):
        key_path = KEYS_DIR / f"{pdf.stem}.json"
        if not key_path.exists():
            print(f"Skipping {pdf.name}: no answer key at {key_path}")
            continue
        with open(key_path, encoding="utf-8") as f:
            expected = json.load(f)

        row = load_saved_row(pdf, expected) if reuse else None
        if row is not None:
            print(f"[{i}/{len(pdfs)}] {pdf.name}: reusing saved result (no API call)", flush=True)
        else:
            # A local Ollama model has no rate limit, so there is nothing to wait for.
            pause = 0 if provider_and_model()[0] == "ollama" else DELAY_SECONDS
            if called_api and pause:
                time.sleep(pause)
            print(f"[{i}/{len(pdfs)}] Extracting {pdf.name} ...", flush=True)
            row = evaluate_invoice(app, pdf, expected)
            called_api = True
        summary = ("FAILED" if row["error"]
                   else f"{row['status']} | {sum(row['checks'].values())}/{len(FIELDS)} fields correct "
                        f"| {row['bucket']}")
        print(f"        {summary}", flush=True)
        rows.append(row)

        # Stop early when the API keeps refusing: an exhausted daily quota will not clear today,
        # and retrying every remaining invoice would waste many minutes for no measurement.
        rate_limited_tail = [r.get("rate_limited") for r in rows[-ABORT_AFTER:]]
        if len(rate_limited_tail) == ABORT_AFTER and all(rate_limited_tail):
            stopped_early = len(pdfs) - i
            print(f"\nStopping: {ABORT_AFTER} invoices in a row were rate limited. "
                  f"{stopped_early} invoice(s) not attempted. Wait for the quota to reset, or switch "
                  f"provider/model in .env, then run again (--reuse keeps what already succeeded).",
                  flush=True)
            break

    if not rows:
        print("No invoices with answer keys found.")
        return

    report = build_report(rows, not_run=stopped_early)
    # The provider and model are part of the file name, so one model's report never
    # overwrites another's (e.g. evaluation_report_ollama_qwen2.5-7b.md).
    out = RESULTS_DIR / f"evaluation_report_{run_slug()}.md"
    out.write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Report saved to {out}")


if __name__ == "__main__":
    main()
