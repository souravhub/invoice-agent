# Invoice Extraction Evaluation

- Run at: 2026-09-30 18:05
- Provider / model: gemini / gemini-3-flash-preview
- Fields graded per invoice: 11 (was 9 before `discount` and `shipping` were added, so field counts in older reports are out of 9 per invoice; compare the percentages, and the bucket and silent-error numbers, which are per invoice and stay comparable)
- Invoices evaluated: 15
- Graded from results saved by an earlier run (no new API call): 0

## How to read this report

The agent gives every invoice a verdict: **auto_approved** (safe to process) or **needs_review** (a human must look at it). Accuracy alone does not tell you whether those verdicts can be trusted, so each invoice is also placed in one of four buckets.

**A silent error is a wrong result that the agent passed on as confident.** Nobody is asked to check it, so the mistake goes straight into the business as if it were correct. This is the most important number for client trust: an invoice sent for review costs a few minutes of someone's time, but a silent error can mean paying the wrong amount. Being over-cautious is inconvenient; a silent error is a real loss.

## Headline numbers

| Measure | Value | Meaning |
|---|---|---|
| **Silent error rate** | **13.3%** (2/15) | Wrong, and nobody was told. Keep this as close to 0% as possible. |
| Escalation rate | 0.0% (0/15) | Share of invoices sent for human review. |
| Field accuracy, all invoices | 98.8% (163/165) | Every field on every invoice. |
| Field accuracy, auto-approved only | 98.8% (163/165) | How good the data is that goes through unchecked. |
| Runs that failed | 0/15 | Could not be measured (see the table below); left out of every number above. |

## Outcome buckets

| Bucket | Count | Share | What it means |
|---|---|---|---|
| clean_pass | 13/15 | 86.7% | Auto approved and every field correct. The ideal outcome: no human needed. |
| **silent_error** | 2/15 | 13.3% | Auto approved but at least one field wrong. A wrong result passed off as confident. |
| caught | 0/15 | 0.0% | Sent for review and at least one field wrong. The agent caught its own mistake. |
| over_cautious | 0/15 | 0.0% | Sent for review but actually every field was correct. Safe, but wastes a human's time. |

## Silent errors (auto approved but wrong)

### invoice_13
- **subtotal**: expected `null`, got `6510.0`

### invoice_15
- **invoice_date**: expected `"2026-05-04"`, got `"2026-04-05"`


## Accuracy by field

| Field | Correct | Accuracy |
|---|---|---|
| vendor_name | 15/15 | 100.0% |
| invoice_number | 15/15 | 100.0% |
| invoice_date | 14/15 | 93.3% |
| po_number | 15/15 | 100.0% |
| currency | 15/15 | 100.0% |
| line_items | 15/15 | 100.0% |
| subtotal | 14/15 | 93.3% |
| discount | 15/15 | 100.0% |
| shipping | 15/15 | 100.0% |
| tax | 15/15 | 100.0% |
| total | 15/15 | 100.0% |
| **Overall** | **163/165** | **98.8%** |

## Per-invoice results

| Invoice | Status | Bucket | Fields correct | Attempts | Notes |
|---|---|---|---|---|---|
| invoice_01 | auto_approved | clean_pass | 11/11 | 1 | - |
| invoice_02 | auto_approved | clean_pass | 11/11 | 1 | - |
| invoice_03 | auto_approved | clean_pass | 11/11 | 1 | - |
| invoice_04 | auto_approved | clean_pass | 11/11 | 1 | - |
| invoice_05 | auto_approved | clean_pass | 11/11 | 1 | - |
| invoice_06 | auto_approved | clean_pass | 11/11 | 1 | - |
| invoice_07 | auto_approved | clean_pass | 11/11 | 1 | - |
| invoice_08 | auto_approved | clean_pass | 11/11 | 1 | - |
| invoice_09 | auto_approved | clean_pass | 11/11 | 1 | - |
| invoice_10 | auto_approved | clean_pass | 11/11 | 1 | - |
| invoice_11 | auto_approved | clean_pass | 11/11 | 1 | - |
| invoice_12 | auto_approved | clean_pass | 11/11 | 1 | - |
| invoice_13 | auto_approved | silent_error | 10/11 | 1 | - |
| invoice_14 | auto_approved | clean_pass | 11/11 | 1 | - |
| invoice_15 | auto_approved | silent_error | 10/11 | 1 | - |

## All mismatches

### invoice_13
- **subtotal**: expected `null`, got `6510.0`

### invoice_15
- **invoice_date**: expected `"2026-05-04"`, got `"2026-04-05"`


---

## Follow-up: FIX 4 and FIX 5

- Run at: 2026-09-30 (after the full run above)
- Provider / model: gemini / gemini-3-flash-preview (same as above and as the baseline)
- `DATE_FORMAT`: `unknown`
- Invoices re-run: **invoice_03, invoice_13, invoice_15 only** (fresh extractions, graded with the same strict 11-field grader; answer keys unchanged)

**What changed in the code**

- **FIX 4 (ambiguous dates):** a new client setting `DATE_FORMAT` (`DMY`, `MDY` or `unknown`, default `unknown`) in the rules block of `workflow.py`. When it is `DMY` or `MDY`, the extraction prompt tells the AI which order numeric dates use. When it is `unknown`, a new escalation rule (rule 7) reads the invoice date **as printed in the invoice text** (not the AI's answer, and skipping any date labelled "due"). If it is `NN/NN/YYYY` with both numbers 12 or less and not equal, the invoice goes to `needs_review` with the reason "date could be read as day/month or month/day; set DATE_FORMAT for this client".
- **FIX 5 (subtotal and tax only if printed):** the `subtotal` and `tax` descriptions in `schema.py` now tell the AI to record them only if the invoice prints them, to leave both empty when only a total is shown, and never to calculate them.

**Results**

| Invoice | Before FIX 4/5 | After FIX 4/5 | Fields correct | Why |
|---|---|---|---|---|
| invoice_03 | clean_pass | **over_cautious** | 11/11 | Printed date `09/03/2026` could be either order, so rule 7 sends it for review. The AI read it correctly (2026-09-03). |
| invoice_13 | silent_error | **clean_pass** | 11/11 | The bill prints only a total; subtotal and tax now come back empty, matching the answer key. |
| invoice_15 | silent_error | **caught** | 10/11 | Printed date `04/05/2026` could be either order, so rule 7 sends it for review. The AI again answered 2026-04-05 against the key's 2026-05-04, but a person now checks it. |

**Combined view across all 15 invoices** (12 invoices from the full run above, plus the 3 re-run here):

| Measure | Before fix | After fix (full run) | After FIX 4 and 5 (combined) |
|---|---|---|---|
| **Silent error rate** | 20.0% | 13.3% | **0.0%** |
| clean_pass | 80.0% | 86.7% | 86.7% |
| caught | 0.0% | 0.0% | 6.7% (invoice_15) |
| over_cautious | 0.0% | 0.0% | 6.7% (invoice_03) |
| Escalation rate | 0.0% | 0.0% | 13.3% |
| Field accuracy, all invoices | 97.0% | 98.8% | 99.4% |
| Field accuracy, auto-approved only | 97.0% | 98.8% | 100.0% |

**Limits of this follow-up**

- The other 12 invoices were **not re-run** with FIX 4 and FIX 5. FIX 4's rule was checked offline against the text of all 15 invoices and flags only 03 and 15. FIX 5 changes the instructions the AI receives on every invoice; all 12 of the others print a subtotal and a tax line, so a change is unlikely, but it has not been measured. The combined column is therefore a projection for those 12, not a fresh measurement.
- invoice_15 is `caught` rather than `over_cautious` only because the AI's guess happened to differ from the answer key. Either way, it is now escalated instead of auto approved, which is what matters.
- The re-run above used the first version of rule 7, which only recognised dates written with slashes (`NN/NN/YYYY`). It was widened afterwards; see the next section.

### Rule 7 widened to hyphens and dots (offline check, no AI calls)

Rule 7 now also matches `NN-NN-YYYY` and `NN.NN.YYYY` (for example `12-09-2026` and `04.05.2026`), with the same condition: both numbers 12 or less and not equal. The same separator must appear on both sides, so references such as `SEH/26-27/0192` are not mistaken for dates.

Checked offline against the text of all 15 invoices, with `DATE_FORMAT=unknown`:

| Invoice | Invoice date as printed | Flagged by rule 7? |
|---|---|---|
| invoice_03 | `09/03/2026` | **Yes** (as before) |
| invoice_10 | `15.09.2026` | No: 15 can only be the day |
| invoice_11 | `12-09-2026` | **Yes (new)** |
| invoice_15 | `04/05/2026` | **Yes** (as before) |
| the other 11 | dates written in words (e.g. `15 September 2026`, `05-Sep-2026`) | No |

invoice_11 was read correctly in the full run (2026-09-12), so with the widened rule it is expected to move from clean_pass to **over_cautious**. That changes the projected totals:

| Measure | After FIX 4 and 5, slash-only rule (above) | After FIX 4 and 5, widened rule (projected) |
|---|---|---|
| **Silent error rate** | 0.0% | **0.0%** |
| clean_pass | 86.7% | 80.0% |
| caught | 6.7% (15) | 6.7% (15) |
| over_cautious | 6.7% (03) | 13.3% (03, 11) |
| Escalation rate | 13.3% | **20.0%** |
| Field accuracy, all invoices | 99.4% | 99.4% |
| Field accuracy, auto-approved only | 100.0% | 100.0% |

Setting `DATE_FORMAT` to `DMY` or `MDY` for a client turns rule 7 off, so all three would then be auto approved if read correctly.
