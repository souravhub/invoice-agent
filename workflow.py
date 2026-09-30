"""
STEP 2: Define HOW the work flows.

A "workflow agent" = a series of steps (nodes) connected by edges,
sharing one state object. Some edges are conditional (the agent "decides").

    START -> load_pdf -> extract -> validate --(ok)--> decide -> END
                            ^          |
                            +-(errors, retries left)-+

The last step, decide, turns the checks into a verdict for each invoice:
"auto_approved" (safe to process) or "needs_review" (a human must look at it).

Only genuine extraction failures are retried. Figures that do not add up are reported
for human review and never sent back to the AI (see FIX 2 near the validate step).
"""
import os
import re
from pathlib import Path
from typing import List, Optional, TypedDict

import pdfplumber
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

from schema import Invoice

MAX_RETRIES = 2
# Note: "gemini-2.5-flash" was the old default but now returns 404 (retired), so the fallback
# is a model that is still served. AI_MODEL in .env overrides this.
DEFAULT_MODELS = {"openai": "gpt-4o-mini", "gemini": "gemini-2.5-flash-lite"}

STATUS_AUTO_APPROVED = "auto_approved"
STATUS_NEEDS_REVIEW = "needs_review"

# =============================================================================
# ESCALATION RULES - the one place to change when a human must review an invoice
# =============================================================================
# Every rule below is checked after the retries have finished. A rule returns a
# short reason when it fires (-> status becomes "needs_review"), or None when it
# passes. Different clients want different rules, so add, remove or reorder the
# entries in ESCALATION_RULES at the end of this block.

MONEY_TOLERANCE = 0.01  # amounts within this much of each other count as equal
REQUIRED_FIELDS = ("vendor_name", "invoice_date", "total")  # used by rule 1

# FIX 4 (ambiguous dates) - the client's date format, used by rule 7 and by the extract prompt.
#   "DMY"     - numeric dates are day/month/year   (04/05/2026 = 4 May 2026)
#   "MDY"     - numeric dates are month/day/year   (04/05/2026 = 5 April 2026)
#   "unknown" - not agreed with the client yet: the AI is given no hint, and any invoice whose
#               date could be read either way is sent for review (rule 7)
# Set DATE_FORMAT in .env per client; this is the value used when it is not set.
DATE_FORMAT_DEFAULT = "unknown"
DATE_FORMAT_HINTS = {
    "DMY": "Numeric dates on this invoice are day/month/year: 04/05/2026 means 4 May 2026.",
    "MDY": "Numeric dates on this invoice are month/day/year: 04/05/2026 means 5 April 2026.",
}


def date_format() -> str:
    """The client's date format from .env, read at call time (see the note above RESULTS_DIR)."""
    value = (os.getenv("DATE_FORMAT") or DATE_FORMAT_DEFAULT).strip()
    value = "unknown" if value.lower() == "unknown" else value.upper()
    if value not in (*DATE_FORMAT_HINTS, "unknown"):
        raise ValueError(f"DATE_FORMAT must be DMY, MDY or unknown, got '{value}'")
    return value


def is_blank(value) -> bool:
    """True for None and for text that is empty or only spaces."""
    return value is None or (isinstance(value, str) and not value.strip())


def money_errors(invoice) -> List[str]:
    """
    The arithmetic checks, shared by the validate step and escalation rule 2.

    FIX 1 (maths): a discount and a shipping charge are now part of the sums:
        line items - discount     = subtotal
        subtotal + tax + shipping = total
    Both are treated as positive amounts; abs() is used so that a model which reports a
    discount as -8680.0 instead of 8680.0 is not marked wrong over a sign convention.
    """
    errors = []
    items_sum = sum(li.amount or 0 for li in invoice.line_items)
    discount = abs(invoice.discount) if invoice.discount else 0.0
    shipping = abs(invoice.shipping) if invoice.shipping else 0.0

    if invoice.subtotal is not None and invoice.line_items:
        expected_subtotal = items_sum - discount
        if abs(expected_subtotal - invoice.subtotal) > MONEY_TOLERANCE:
            sum_text = f"line items sum to {items_sum:.2f}"
            if discount:
                sum_text += f" less a discount of {discount:.2f} = {expected_subtotal:.2f}"
            errors.append(f"{sum_text} but subtotal is {invoice.subtotal:.2f}")

    if None not in (invoice.subtotal, invoice.tax, invoice.total):
        expected_total = invoice.subtotal + invoice.tax + shipping
        if abs(expected_total - invoice.total) > MONEY_TOLERANCE:
            parts = "subtotal + tax" + (" + shipping" if shipping else "")
            errors.append(f"{parts} = {expected_total:.2f} but total is {invoice.total:.2f}")
    return errors


# Rule 1: an invoice cannot be processed without knowing who sent it, when, and how much.
def rule_missing_required_field(invoice, state):
    missing = [name for name in REQUIRED_FIELDS if is_blank(getattr(invoice, name))]
    return "missing required field(s): " + ", ".join(missing) if missing else None


# Rule 2: the arithmetic must hold - line items -> subtotal, and subtotal + tax -> total.
def rule_totals_do_not_add_up(invoice, state):
    errors = money_errors(invoice)
    return "totals do not add up: " + "; ".join(errors) if errors else None


# Rule 3: an empty item table means nothing was really extracted, even if the totals look fine.
def rule_no_line_items(invoice, state):
    return "no line items were extracted" if not invoice.line_items else None


# Rule 4: the AI used up its retries and the checks still fail, so it will not fix itself.
def rule_retries_exhausted(invoice, state):
    errors = state.get("errors") or []
    attempts = state.get("attempts", 0)
    if errors and attempts > MAX_RETRIES:
        return f"still failing validation after {attempts} attempts (retries exhausted)"
    return None


# FIX 3 (escalation) - Rule 6: the answer we ended up with is not the answer the AI gave first.
# A retry means the first attempt failed a check and the AI changed its output. Whatever it
# changed was not read off the document a second time, so a human should confirm it.
def rule_answer_changed_after_retry(invoice, state):
    attempts = state.get("attempts", 0)
    if attempts > 1:
        return (f"the AI needed {attempts} attempts and changed its answer after a retry; "
                "the change was not read from the document, so it must be checked by a human")
    return None


# Rule 5: without a currency we do not know what the amounts mean.
def rule_missing_currency(invoice, state):
    return "currency is missing" if is_blank(invoice.currency) else None


# FIX 4 (ambiguous dates) - Rule 7: the printed date could mean two different days.
# 04/05/2026 is 4 May or 5 April, and nothing in the numbers says which. Without DATE_FORMAT
# the AI can only guess, and the same invoice came back as 4 May in one run and 5 April in the
# next, auto approved both times. So when the format is unknown, a human decides.
# The check reads the date as PRINTED in the invoice text, never the AI's answer, because the
# AI has already turned the date into YYYY-MM-DD and the ambiguity is gone by then.
# NN/NN/YYYY, NN-NN-YYYY or NN.NN.YYYY. The same separator must appear twice (\2), so a
# reference like "26-27/0192" is never mistaken for a date.
NUMERIC_DATE = re.compile(r"\b(\d{1,2})([/.-])(\d{1,2})\2(\d{4})\b")
DUE_DATE_LABEL = re.compile(r"\bdue\b", re.I)  # a due date is not the invoice date


def printed_invoice_date(text):
    """The first numeric date in the text that is not labelled as a due date, as (a, b)."""
    for match in NUMERIC_DATE.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        label = text[line_start:match.start()][-30:]  # the words just before the date
        if not DUE_DATE_LABEL.search(label):
            return int(match.group(1)), int(match.group(3))
    return None


def rule_ambiguous_date(invoice, state):
    if date_format() != "unknown":
        return None  # the client's format is known, and the prompt told the AI which it is
    printed = printed_invoice_date(state.get("raw_text") or "")
    if printed and printed[0] <= 12 and printed[1] <= 12 and printed[0] != printed[1]:
        return "date could be read as day/month or month/day; set DATE_FORMAT for this client"
    return None


ESCALATION_RULES = (
    rule_missing_required_field,
    rule_totals_do_not_add_up,
    rule_no_line_items,
    rule_retries_exhausted,
    rule_missing_currency,
    rule_answer_changed_after_retry,
    rule_ambiguous_date,
)


# ---------- Which AI is in use, and where its results go ----------
# These three helpers are shared by main.py and evaluate.py so both name their output files
# the same way. Read at call time, not import time: main.py imports this module before
# load_dotenv() runs, so anything read at the top of the file would miss the .env settings.
RESULTS_DIR = Path("results")


def provider_and_model():
    """The provider and model chosen in .env, with the default filled in when AI_MODEL is unset."""
    provider = (os.getenv("AI_PROVIDER") or "openai").strip().lower()
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"AI_PROVIDER must be one of {sorted(DEFAULT_MODELS)}, got '{provider}'")
    model = (os.getenv("AI_MODEL") or "").strip() or DEFAULT_MODELS[provider]
    return provider, model


def run_slug():
    """A file-name-safe tag for this run, e.g. 'ollama_qwen2.5-7b'."""
    provider, model = provider_and_model()
    return f"{provider}_{re.sub(r'[^A-Za-z0-9._-]+', '-', model)}"


def run_dir():
    """Each provider/model keeps its own results folder, so runs never overwrite each other."""
    path = RESULTS_DIR / run_slug()
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------- Pick the LLM from .env settings ----------
def get_llm():
    provider, model = provider_and_model()

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("AI_PROVIDER is 'gemini' but GEMINI_API_KEY is not set in .env")
        return ChatGoogleGenerativeAI(model=model, api_key=api_key, temperature=0)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("AI_PROVIDER is 'openai' but OPENAI_API_KEY is not set in .env")
    return ChatOpenAI(model=model, api_key=api_key, temperature=0)


# ---------- Shared state passed between every node ----------
class InvoiceState(TypedDict, total=False):
    pdf_path: str
    raw_text: str
    invoice: Optional[Invoice]
    errors: List[str]       # extraction problems: worth asking the AI to try again
    math_errors: List[str]  # printed figures that do not add up: reported, never retried
    attempts: int
    status: str          # "auto_approved" or "needs_review"
    reasons: List[str]   # why it needs review (empty when auto approved)


# ---------- Node 1: read the PDF ----------
def load_pdf(state: InvoiceState) -> InvoiceState:
    pages = []
    with pdfplumber.open(state["pdf_path"]) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    text = "\n\n--- PAGE BREAK ---\n\n".join(pages)
    if not text.strip():
        raise ValueError("No text found. This PDF may be scanned; it needs OCR first.")
    return {"raw_text": text, "attempts": 0, "errors": []}


# ---------- Node 2: LLM extraction with structured output ----------
def extract(state: InvoiceState) -> InvoiceState:
    llm = get_llm()
    structured_llm = llm.with_structured_output(Invoice)  # <- the key line

    prompt = (
        "You are an invoice data extraction assistant. Extract the fields from the "
        "invoice text below. Use null for anything not present; never invent values. "
        "Amounts must be plain numbers without currency symbols or commas.\n\n"
    )
    # FIX 4 (ambiguous dates): when the client's date format is known, say so. When it is
    # "unknown" nothing is added, and rule 7 escalates any date that could be read both ways.
    hint = DATE_FORMAT_HINTS.get(date_format())
    if hint:
        prompt += hint + "\n\n"
    prompt += f"INVOICE TEXT:\n{state['raw_text']}"
    # On a retry, tell the model what it missed last time (extraction problems only, never sums)
    if state.get("errors"):
        prompt += "\n\nYour previous extraction had these problems, fix them:\n- " + "\n- ".join(state["errors"])

    invoice = structured_llm.invoke(prompt)
    return {"invoice": invoice, "attempts": state.get("attempts", 0) + 1}


# ---------- Node 3: rule-based validation (no LLM) ----------
# FIX 2 (retry policy): the checks are split into two kinds, because only one kind is worth
# sending back to the AI.
#
#   errors      - the AI genuinely missed something (no vendor, no total, no line items).
#                 Reading the document again can fix this, so these DO trigger a retry.
#   math_errors - the printed figures do not add up (a discount, a freight charge, a rounding
#                 difference, or a genuine mistake by the vendor). These are NEVER sent back.
#
# Why: asking a model to fix arithmetic it cannot honestly fix pushes it to fabricate data.
# When we used to feed "subtotal + tax does not equal total" back as a complaint, the model
# obliged by inventing a line item and rewriting the subtotal until the sums closed. The
# output looked perfect, passed every check, and was wrong - a silent error. A mismatch in
# the printed figures is a fact about the invoice, so it is reported for human review instead.
def extraction_errors(invoice) -> List[str]:
    """Things the AI plausibly got wrong and could fix by reading the text again."""
    errors = []
    if not invoice.vendor_name:
        errors.append("vendor_name is missing")
    if invoice.total is None:
        errors.append("total is missing")
    if not invoice.line_items:
        errors.append("no line items were extracted")
    return errors


def validate(state: InvoiceState) -> InvoiceState:
    inv = state["invoice"]
    return {"errors": extraction_errors(inv), "math_errors": money_errors(inv)}


# ---------- Conditional edge: the "decision" ----------
def should_retry(state: InvoiceState) -> str:
    # Only extraction failures are retried. math_errors deliberately play no part here.
    if state["errors"] and state["attempts"] <= MAX_RETRIES:
        return "retry"
    return "done"


# ---------- Node 4: the verdict (no LLM) ----------
def decide(state: InvoiceState) -> InvoiceState:
    reasons = []
    for rule in ESCALATION_RULES:
        reason = rule(state["invoice"], state)
        if reason:
            reasons.append(reason)
    return {
        "status": STATUS_NEEDS_REVIEW if reasons else STATUS_AUTO_APPROVED,
        "reasons": reasons,
    }


# ---------- Wire it all together ----------
def build_graph():
    g = StateGraph(InvoiceState)
    g.add_node("load_pdf", load_pdf)
    g.add_node("extract", extract)
    g.add_node("validate", validate)
    g.add_node("decide", decide)

    g.add_edge(START, "load_pdf")
    g.add_edge("load_pdf", "extract")
    g.add_edge("extract", "validate")
    g.add_conditional_edges("validate", should_retry, {"retry": "extract", "done": "decide"})
    g.add_edge("decide", END)
    return g.compile()
