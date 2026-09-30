# Invoice Extraction Evaluation

- Run at: 2026-09-28 12:39
- Provider / model: gemini / gemini-3-flash-preview
- Invoices evaluated: 15
- Graded from results saved by an earlier run (no new API call): 12

## How to read this report

The agent gives every invoice a verdict: **auto_approved** (safe to process) or **needs_review** (a human must look at it). Accuracy alone does not tell you whether those verdicts can be trusted, so each invoice is also placed in one of four buckets.

**A silent error is a wrong result that the agent passed on as confident.** Nobody is asked to check it, so the mistake goes straight into the business as if it were correct. This is the most important number for client trust: an invoice sent for review costs a few minutes of someone's time, but a silent error can mean paying the wrong amount. Being over-cautious is inconvenient; a silent error is a real loss.

## Headline numbers

| Measure | Value | Meaning |
|---|---|---|
| **Silent error rate** | **20.0%** (3/15) | Wrong, and nobody was told. Keep this as close to 0% as possible. |
| Escalation rate | 0.0% (0/15) | Share of invoices sent for human review. |
| Field accuracy, all invoices | 97.0% (131/135) | Every field on every invoice. |
| Field accuracy, auto-approved only | 97.0% (131/135) | How good the data is that goes through unchecked. |
| Runs that failed | 0/15 | Could not be measured (see the table below); left out of every number above. |

## Outcome buckets

| Bucket | Count | Share | What it means |
|---|---|---|---|
| clean_pass | 12/15 | 80.0% | Auto approved and every field correct. The ideal outcome: no human needed. |
| **silent_error** | 3/15 | 20.0% | Auto approved but at least one field wrong. A wrong result passed off as confident. |
| caught | 0/15 | 0.0% | Sent for review and at least one field wrong. The agent caught its own mistake. |
| over_cautious | 0/15 | 0.0% | Sent for review but actually every field was correct. Safe, but wastes a human's time. |

## Silent errors (auto approved but wrong)

### invoice_07
- **line_items**: expected `3 items, amounts [44700.0, 15600.0, 26500.0]`, got `4 items, amounts [44700.0, 15600.0, 26500.0, -8680.0]`

### invoice_08
- **line_items**: expected `4 items, amounts [1032.0, 447.5, 830.0, 445.5]`, got `5 items, amounts [1032.0, 447.5, 830.0, 445.5, 185.0]`
- **subtotal**: expected `2755.0`, got `2940.0`

### invoice_13
- **subtotal**: expected `null`, got `6510.0`


## Accuracy by field

| Field | Correct | Accuracy |
|---|---|---|
| vendor_name | 15/15 | 100.0% |
| invoice_number | 15/15 | 100.0% |
| invoice_date | 15/15 | 100.0% |
| po_number | 15/15 | 100.0% |
| currency | 15/15 | 100.0% |
| line_items | 13/15 | 86.7% |
| subtotal | 13/15 | 86.7% |
| tax | 15/15 | 100.0% |
| total | 15/15 | 100.0% |
| **Overall** | **131/135** | **97.0%** |

## Per-invoice results

| Invoice | Status | Bucket | Fields correct | Attempts | Notes |
|---|---|---|---|---|---|
| invoice_01 | auto_approved | clean_pass | 9/9 | 1 | - [graded from a saved result, no new API call] |
| invoice_02 | auto_approved | clean_pass | 9/9 | 1 | - [graded from a saved result, no new API call] |
| invoice_03 | auto_approved | clean_pass | 9/9 | 1 | - [graded from a saved result, no new API call] |
| invoice_04 | auto_approved | clean_pass | 9/9 | 1 | - [graded from a saved result, no new API call] |
| invoice_05 | auto_approved | clean_pass | 9/9 | 1 | - [graded from a saved result, no new API call] |
| invoice_06 | auto_approved | clean_pass | 9/9 | 1 | - |
| invoice_07 | auto_approved | silent_error | 8/9 | 2 | - |
| invoice_08 | auto_approved | silent_error | 7/9 | 2 | - |
| invoice_09 | auto_approved | clean_pass | 9/9 | 1 | - [graded from a saved result, no new API call] |
| invoice_10 | auto_approved | clean_pass | 9/9 | 1 | - [graded from a saved result, no new API call] |
| invoice_11 | auto_approved | clean_pass | 9/9 | 1 | - [graded from a saved result, no new API call] |
| invoice_12 | auto_approved | clean_pass | 9/9 | 1 | - [graded from a saved result, no new API call] |
| invoice_13 | auto_approved | silent_error | 8/9 | 1 | - [graded from a saved result, no new API call] |
| invoice_14 | auto_approved | clean_pass | 9/9 | 1 | - [graded from a saved result, no new API call] |
| invoice_15 | auto_approved | clean_pass | 9/9 | 1 | - [graded from a saved result, no new API call] |

## All mismatches

### invoice_07
- **line_items**: expected `3 items, amounts [44700.0, 15600.0, 26500.0]`, got `4 items, amounts [44700.0, 15600.0, 26500.0, -8680.0]`

### invoice_08
- **line_items**: expected `4 items, amounts [1032.0, 447.5, 830.0, 445.5]`, got `5 items, amounts [1032.0, 447.5, 830.0, 445.5, 185.0]`
- **subtotal**: expected `2755.0`, got `2940.0`

### invoice_13
- **subtotal**: expected `null`, got `6510.0`

