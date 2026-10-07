# Invoice Extraction Agent: Project Notes

**What it does:** reads an invoice PDF and turns it into clean, structured data (vendor, invoice number, date, PO number, currency, line items, subtotal, tax, total). It then checks that the numbers add up.

**Built with:** Python 3.14, LangChain, LangGraph, and a switchable AI model (OpenAI or Google Gemini).

**Status (22 September 2026):** working end to end. It scored **45/45 fields correct (100%)** on a 5-invoice test set using Gemini.

---

## 1. How it works

The agent is a short pipeline of steps. Each step passes its results to the next.

```
PDF -> load_pdf (read the text) -> extract (AI fills in a form) -> validate (check) -> decide (verdict)
                                      ^                              |
                                      +--- retry, up to 2 more ------+   (only if a field is MISSING,
                                                                          never because sums disagree)
```

1. **load_pdf** pulls the plain text out of the PDF. No AI is used here.
2. **extract** sends the text to the AI, which must fill in a fixed form defined in `backend/agent/schema.py`. The AI can't reply in free text; it has to return data in exactly this shape.
3. **validate** uses plain code rules, not AI, and sorts what it finds into two kinds:
   - **missing information** (no vendor, no total, no line items): the AI is asked to try again, up to 2 more times
   - **figures that do not add up** (`items - discount = subtotal`, `subtotal + tax + shipping = total`): reported, never sent back to the AI
4. **decide** gives every invoice a verdict: `auto_approved`, or `needs_review` with plain-language reasons. See section 6 for the rules and for why sums are never sent back to the AI.

### Project files

| File / folder | Purpose |
|---|---|
| `backend/agent/schema.py` | The form the AI must fill in: which fields we want and what each one means |
| `backend/agent/workflow.py` | The pipeline steps, how they connect, and which AI provider is used |
| `backend/peek_pdf.py` | Prints the text pulled out of a PDF (no AI; useful for debugging) |
| `make_sample_invoice.py` | Creates the first sample invoice |
| `make_test_invoices.py` | Creates the other test invoices and their answer keys |
| `backend/evaluate.py` | Runs every test invoice, scores the accuracy and the escalation quality |
| `invoices/` | 15 test invoice PDFs (`invoice_01` to `invoice_15`) |
| `answer_keys/` | The correct answers for each test invoice, plus `notes` on judgment calls |
| `results/` | Reports, and the AI's raw output per provider and model (e.g. `gemini_gemini-3-flash-preview/`) |
| `backend/.env` | Private settings and API keys. **Never share or commit this file.** |
| `backend/requirements.txt` | The Python packages the backend needs |

---

## 2. Quick start (new team member)

### Prerequisites

- **Python 3.14** from python.org. During install, turn on **"Add to PATH"** and **long paths**.
- **VS Code** (the code editor) and **Git** (version control) are recommended.
- An API key for **OpenAI** (platform.openai.com) or **Google Gemini**.

### Setup

```powershell
python -m venv venv                                            # 1. create a private package folder for this project
.\venv\Scripts\python.exe -m pip install -r backend\requirements.txt   # 2. install the packages into it
```

3. Copy `backend/.env.example` to **`backend/.env`** and add these settings:

| Setting | Meaning |
|---|---|
| `AI_PROVIDER` | `openai` or `gemini`. If it's left out, OpenAI is used. |
| `OPENAI_API_KEY` | Needed when the provider is `openai` |
| `GEMINI_API_KEY` | Needed when the provider is `gemini` |
| `AI_MODEL` | Optional. If it's left out: `gpt-4o-mini` for OpenAI, `gemini-2.5-flash-lite` for Gemini. |

> **Warning: free-tier Gemini keys and data privacy.** With a free-tier Gemini key, data sent to the API may be used by Google to improve its products. Only use fake or generated invoices with a free key. **Never send real company or client invoices.**

### Everyday commands

```powershell
.\venv\Scripts\python.exe -m backend.peek_pdf                       # see the text the AI will receive
.\venv\Scripts\python.exe -m backend.evaluate                       # score accuracy on all test invoices
```

**Tip:** run `.\venv\Scripts\Activate.ps1` once per terminal. After that, plain `python` works in that terminal.

### Common setup issues

| Problem | Cause | Fix |
|---|---|---|
| `python` says "Python was not found" | Windows has a fake `python` shortcut that points to the Microsoft Store | Install Python from python.org and add it to PATH |
| `Activate.ps1` is blocked ("running scripts is disabled") | PowerShell's safety setting | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and answer Y |
| `.env.example` arrives as `env.example` | Some downloads drop files that start with a dot | Rename it to `.env` |
| "insufficient quota" error from OpenAI | The API account has no credits | Add credits at platform.openai.com. A ChatGPT subscription does **not** include API access. |
| Error 429 or "resource exhausted" | Too many requests on a rate-limited key (for example, a shared free key) | Wait a minute and try again |
| A notice about "automatic function calling (AFC)" appears | A harmless message from Google's library | Ignore it |

---

## 3. Demo script (about 5 minutes)

1. **Show the input:** open `invoices/invoice_04.pdf`, a busy invoice with 10 line items and tax split into two lines.
2. **Show what the AI receives:** run `python -m backend.peek_pdf`. The table becomes plain lines of text, with no columns or layout.
3. **Check one invoice:** upload `invoices/invoice_04.pdf` in the web app. It shows clean structured data, the combined tax, and the configured-check status.
4. **Show the accuracy score:** run `python -m backend.evaluate`. It shows the per-field accuracy table and the overall score.
5. **Show flexibility:** change `AI_PROVIDER` in `backend/.env` to switch AI vendors without changing any code.

---

## 4. Day 1: setup and first run

### Steps completed

- Set up the Python environment and installed the project packages into a virtual environment.
- Made the AI provider **switchable** through `.env` (`AI_PROVIDER`, `GEMINI_API_KEY`, `AI_MODEL`):
  - added the `langchain-google-genai` package
  - added a `get_llm()` function in `backend/agent/workflow.py` that creates the right AI connection
  - this means the project isn't tied to a single AI vendor or its billing
- **Fixed a hidden bug in the original runner:** settings are read only when the AI is actually called, so environment configuration is applied correctly.
- Created `backend/peek_pdf.py` to inspect the text pulled out of a PDF.
- Ran the first full extraction on the sample invoice.

### Observations

- **The AI only sees plain text, not the layout.** The invoice table reaches the AI as ordinary lines of words and numbers, for example:

  ```
  A4 Printer Paper (500 sheets) 20 350.00 7,000.00
  ```

  Columns, colors, boxes and bold text are lost. The AI works out which number is the quantity and which is the price from the order of the words.
- **Scanned PDFs contain no text.** `load_pdf` stops with a clear error for them. They need OCR (turning a picture of text into real text) first.
- **First run result:** every field was correct on the first attempt. The AI also cleaned up the data:
  - "15 September 2026" became `2026-09-15`
  - "7,000.00" became the plain number `7000`
  - it worked out the currency (`INR`) from the "(INR)" column headings

### Lessons learned

1. **Plan for setup time.** Installing tools, setting up API keys and sorting out billing takes a significant part of day 1.
2. **Confirm the API account has credits before the project starts.** A chat subscription and API access are billed separately.
3. **Make the AI provider a setting, not hard-coded.** Switching vendors becomes a one-line change.
4. **Use one virtual environment per project.**
5. **Inspect what the AI actually receives.** Layout information is lost before the AI sees the document.
6. **Keep API keys only in `.env`.** Never put them in code, documents, chats or screenshots.
7. **Free-tier AI keys are fine for testing with fake data.** Real client data needs a paid account with proper data terms.

---

## 5. Day 2: testing and accuracy

### Steps completed

- Built a 5-invoice test set with answer keys.
- Built `backend/evaluate.py` to score accuracy automatically.
- Checked that the grader catches wrong answers.
- Ran the full evaluation on Gemini.

### The test set

- Each invoice has a different vendor, currency and page design, and a deliberate **trap**.

| Invoice | Vendor | Currency | Trap |
|---|---|---|---|
| invoice_01 | Acme Office Supplies | INR | Baseline sample |
| invoice_02 | Northwind Catering GmbH | EUR | **No PO number.** The correct answer is "none" (`null`), not something made up. |
| invoice_03 | Blue Ridge Software LLC | USD | **US date `09/03/2026`**, which means 3 September. There's also a due date that must not be picked instead. |
| invoice_04 | Sharma Electricals & Hardware | INR | **10 line items** in a crowded table. Tax is split into CGST 9% + SGST 9%, so the correct tax is their sum. |
| invoice_05 | Brightline Design Studio | GBP | The final amount is labeled **"Amount Due"** (no "Total"). The PO number is labeled "Your reference." |

### Answer keys (ground truth)

- An **answer key** is the correct answer for each invoice, written down in advance. It's also called **ground truth**. The AI's output is compared against it.
- `make_test_invoices.py` writes each invoice's data **once** and uses it to create both the PDF and its answer key. The two can't disagree, and the totals are calculated by the script, not typed by hand.
- The answer key for `invoice_01` was taken from the AI's output and checked by hand against the PDF. Future answer keys should be created independently of the AI being tested.
- The `invoice_05` answer key treats **"Your reference"** as the PO number. This is a judgment call, not a clear fact. If the agent ever disagrees, check whether the agent or the answer key is wrong. In real projects, agree on these field definitions with the client before testing.

### Scoring rules in backend/evaluate.py

- These rules are forgiving about small differences that don't matter, and strict about dates and money.

| Field type | Rule | Example that counts as correct |
|---|---|---|
| Text (vendor, invoice number, PO, currency) | Ignore capital letters, punctuation and extra spaces | `Acme Office Supplies Pvt. Ltd.` matches `acme office supplies pvt ltd` |
| Numbers (subtotal, tax, total) | Within 0.01 | `100.00` matches `100.009` |
| Date | Must be exactly the same | Only `2026-09-03` matches `2026-09-03` |
| Line items | Counted as **one** field: same number of items, and every item's amount matches | |
| Empty values | "None" (`null`) only matches "none" | |

- Other details:
  - It waits **5 seconds between invoices**, to stay within free-tier rate limits.
  - If an invoice fails (for example, a rate-limit error), all its fields count as wrong and the run continues.
  - The report is saved to `results/evaluation_report_<provider>_<model>.md` (for example `evaluation_report_gemini_gemini-3-flash-preview.md`), and each invoice's raw AI output is saved to `results/<provider>_<model>/`.

### Checking the grader

- The grader was given **deliberately wrong answers** to confirm it catches them:
  - an extra word in the vendor name
  - a total that's off by 0.02
  - day and month swapped in the date
  - a PO number where the answer should be "none"
  - a missing line item
  - a wrong line item amount
- It rejected every wrong answer and accepted the near-matches (like `Pvt. Ltd.` vs `pvt ltd`). **9 out of 9 checks behaved as expected.**

### Result

| Provider / model | Invoices | Fields correct | Accuracy | Retries needed |
|---|---|---|---|---|
| Gemini / gemini-3-flash-preview | 5 | 45/45 | **100%** | 0 |

- All the traps were handled correctly: the missing PO, the US date, the 10 items with split tax, and "Amount Due."

### Lessons learned

1. **Measure, don't guess.** Answer keys plus a scoring script turn "it seems to work" into a number that can be repeated.
2. **Put traps in the test set on purpose.** Easy test cases give false confidence.
3. **Generate each PDF and its answer key from the same data.**
4. **Agree the matching rules in advance** and write them down.
5. **Test the grader,** not just the AI.
6. **Allow for API rate limits.** Pause between calls, and make sure one failure doesn't stop the whole run.

---

## 6. Day 3: verdicts, hard invoices, and the first real failure

Day 2 ended at 100% on five easy invoices. Day 3 was about asking harder questions: does the
agent know when it is unsure, and what happens when invoices stop being tidy?

### Steps completed

- Gave the agent a **verdict** for every invoice instead of a list of warnings.
- Built **10 deliberately hard test invoices** (invoice_06 to invoice_15).
- Added **escalation quality** to the evaluation, not just field accuracy.
- Ran the full 15-invoice evaluation, found a serious problem, and traced its cause.
- Applied **three fixes**, and extended the answer keys to grade two new fields.

### Escalation: the agent now gives a verdict

The pipeline gained a fourth step, `decide`, which runs after the retries are finished:

```
PDF -> load_pdf -> extract -> validate --(ok)--> decide -> END
```

Every invoice now comes back with three extra pieces of information:

| Field | Meaning |
|---|---|
| `status` | `auto_approved` (safe to process) or `needs_review` (a human must look) |
| `reasons` | why it needs review, in plain sentences (empty when auto approved) |
| `attempts` | how many times the AI was asked |

The rules that send an invoice for review all sit in **one clearly marked block near the top of
`backend/agent/workflow.py`**, because different clients will want different rules:

| Rule | Sends for review when |
|---|---|
| missing required field | vendor name, invoice date or total is empty |
| totals do not add up | items (minus discount) ≠ subtotal, or subtotal + tax + shipping ≠ total |
| no line items | the item table came back empty |
| retries exhausted | the retries ran out and checks still fail |
| missing currency | no currency was found |
| answer changed after a retry | more than one attempt was needed (added later on Day 3) |

### The four buckets, and why silent errors matter most

Accuracy alone cannot tell you whether the verdicts can be trusted, so every invoice is sorted
by **what the agent decided** against **whether it was actually right**:

| Bucket | Agent said | Really was | Meaning |
|---|---|---|---|
| `clean_pass` | auto approved | correct | The ideal: no human needed |
| `silent_error` | auto approved | wrong | **Wrong, and nobody was told** |
| `caught` | needs review | wrong | The agent caught its own mistake |
| `over_cautious` | needs review | correct | Safe, but wastes a human's time |

**A silent error is the number that decides whether a client can trust the system.** An escalated
invoice costs a few minutes of someone's time. A silent error can mean paying the wrong amount,
because nobody was ever asked to look. Being over-cautious is an inconvenience; a silent error
is a real loss. Field accuracy can look excellent while silent errors make the system unusable.

### The 10 hard test invoices

Each one breaks an assumption that the five easy invoices never tested:

| Invoice | What it tests |
|---|---|
| invoice_06 | 3 pages, items spread across them, totals only on the last page |
| invoice_07 | a discount line, so items do not sum to the subtotal |
| invoice_08 | freight added after the subtotal, so subtotal + tax ≠ total |
| invoice_09 | a credit note: negative amounts and a negative total |
| invoice_10 | German labels (Rechnung, MwSt., Summe), date 15.09.2026, and "1.997,00" meaning 1997 |
| invoice_11 | Hindi (Devanagari) mixed with English |
| invoice_12 | two unrelated invoices in one PDF; only the first is the answer |
| invoice_13 | an informal bill with no invoice number, no PO and no tax line |
| invoice_14 | four similar reference numbers (invoice, PO, customer ID, account ref) |
| invoice_15 | an ambiguous date, 04/05/2026, with no clue anywhere on the page |

Where the right answer is genuinely debatable, the answer key carries a **`notes`** field
explaining the judgment call, so a disagreement can be told apart from a mistake.

### The result: 97% accurate, and still not trustworthy

| Measure | Result |
|---|---|
| Field accuracy | **97.0%** (131/135) |
| clean_pass | 12/15 |
| **silent_error** | **3/15 (20%)** - invoices 07, 08 and 13 |
| caught | 0/15 |
| over_cautious | 0/15 |

This is the most important lesson of the week. **97% accuracy sounds excellent, and 20% silent
errors makes the system unusable as it stands.** One in five invoices went through with wrong
data and nobody was told. The two numbers describe the same run.

### Root cause: the retry loop taught the AI to invent data

Invoices 07 and 08 shared one cause, and it was not the AI being careless. Both needed
**2 attempts**.

Re-running invoice_08 with a single AI call and no retry showed the first attempt was
**perfect**: 4 items, subtotal 2,755.00, tax 192.85, total 3,132.85, exactly the answer key.
The validation step then reported, correctly, that `subtotal + tax` did not equal the total,
because the 185.00 freight charge sits outside both. That complaint was handed back to the AI
with "fix these problems". So it did - by changing the data:

| | First attempt (correct) | After the retry |
|---|---|---|
| line items | 4 real items | 5 items: an invented "Freight & Handling 185.00" |
| subtotal | 2,755.00 | 2,940.00 (2,755 + 185) |

Now everything reconciled, every check passed, and the agent auto approved a wrong answer.
invoice_07 was the same story: the AI added the discount as a fourth line item so the numbers
closed. invoice_13 was different and milder: the AI filled in a subtotal (6,510.00) that the
informal bill never printed, which is a disagreement about conventions rather than a mistake.

**The safety net did not merely miss invoices 07 and 08. It created them.** Without the retry,
both would have been correct extractions flagged for review. The lesson: if a check cannot be
satisfied honestly, asking a model to satisfy it invites invention.

### The three fixes

**Fix 1 - give the truth somewhere to live (`backend/agent/schema.py` and the maths).**
Optional `discount` and `shipping` fields were added, with descriptions telling the model to
record them only when the invoice shows them and never to invent them. The arithmetic became
`items - discount = subtotal` and `subtotal + tax + shipping = total`.
*Reasoning:* the model was forced to lie because the form had no box for what the invoice said.
Fix the form first.

**Fix 2 - stop asking the AI to fix arithmetic (retry policy).**
Checks are now split in two. Missing vendor, missing total or no line items are **extraction
failures**: reading the document again can fix them, so they still trigger a retry. Figures that
do not add up are **never sent back**; they are reported for human review.
*Reasoning:* a mismatch in the printed figures is usually a fact about the invoice, not an
extraction error. "Report, don't fix" is the safer default for money.

**Fix 3 - treat a changed answer as suspicious (escalation).**
Any invoice that needed more than one attempt now goes to `needs_review`, with the reason
explaining that the answer changed after a retry and was not read from the document again.
*Reasoning:* a cheap catch-all. Even if some future check can be gamed, the fact that the AI
changed its mind is itself a reason for a human to look. This single rule would have caught both
silent errors.

### The answer keys now grade 11 fields, not 9

`discount` and `shipping` were added to all 15 answer keys (8,680.00 on invoice_07, 185.00 on
invoice_08, `null` everywhere else) and to the graded field list, so **inventing** a discount is
marked wrong just as firmly as missing one. Graded fields per invoice went from **9 to 11**, so
older reports count out of 9 and only percentages, buckets and silent-error rates compare
directly. Re-grading the saved pre-fix results with the new 11-field grader produced the **same
buckets and the same 20% silent error rate**, which confirms the extra fields did not flatter or
punish the baseline.

### Blocker: the free Gemini quota ran out

The after-fix run could not be completed. The free tier allows **20 requests per day per model**
for `gemini-3-flash`, and one full evaluation needs 15 (more when retries happen). Between the
first evaluation, its retries, the re-run and the diagnostics, the day's allowance was gone.

Improvements made in response, so a quota wall never wastes an hour again:

- **Failed runs are excluded** from accuracy and the buckets, and reported separately. A missing
  measurement is not the same as a wrong answer.
- **The wait the server asks for is honoured** ("Please retry in 11.47s") instead of guessing.
- **The run stops early** after two invoices in a row are rate limited, and the report is marked
  incomplete.
- **`--reuse`** grades invoices that already succeeded from their saved results, so only the
  missing ones cost a fresh call.
- Results are saved per provider and model (`results/gemini_gemini-3-flash-preview/`), so
  different models never overwrite each other.

A separate bug surfaced here too: the fallback model `gemini-2.5-flash` now returns **404
(retired)**, so the default was changed to a model that is still served.

### Status: the after-fix measurement is PENDING

The three fixes are written, commented and checked offline: the discount and freight cases now
reconcile, a genuine mismatch still escalates, and a retry alone escalates. **They have not yet
been measured end to end.** The baseline is saved as
`reports/evaluation_report_BEFORE_FIX.md` (20% silent errors), and the comparison is the first
job once quota is available.

### Lessons learned

1. **Accuracy is not trust.** 97% field accuracy with 20% silent errors is not a good system.
   Report the silent error rate next to accuracy, always.
2. **A self-correcting loop can make things worse.** Feeding a model a complaint it cannot
   honestly satisfy is an invitation to fabricate. Only retry what re-reading can fix.
3. **If the model must lie to pass a check, the schema is wrong.** Add the field.
4. **"The answer changed" is a useful alarm** and costs almost nothing to implement.
5. **Test the escalation, not just the extraction.** The four buckets showed a problem that an
   accuracy score hid completely.
6. **Know the quota before designing the test set.** A 15-invoice suite does not fit comfortably
   in a 20-request daily allowance.
7. **Keep a frozen baseline.** Without the saved before-fix report, there would be nothing
   honest to compare the fixes against.

---

## 7. Local models: Ollama tried and set aside

A local model was tested as a third option alongside OpenAI and Gemini: **Ollama** running
**qwen2.5:7b** on a CPU-only laptop (no graphics card). It worked, but it was set aside as too
slow for everyday use. The support was removed from the code afterwards.

### Speed (CPU only, no GPU)

| Invoice | Time | AI calls |
|---|---|---|
| invoice_01 (1 page, 4 items) | 3 min 21 s | 2 (one retry) |
| invoice_13 (informal bill) | 1 min 35 s | 2 (one retry) |

That is roughly **45 to 100 seconds per AI call**. A full 15-invoice evaluation would take
about 45 to 90 minutes, against a few minutes on Gemini. Every invoice needed two attempts,
which doubles the time.

### Accuracy

| Invoice | Fields correct | What it missed |
|---|---|---|
| invoice_01 | 10/11 | `currency` (null instead of INR) |
| invoice_13 | 8/11 | `currency`, `invoice_date`, and every line-item **amount** came back null |

Two patterns showed up:

- **Currency was missed on both invoices.** The stronger cloud model worked it out from column
  headings such as "Amount (INR)"; the smaller local model did not.
- **It struggled with amounts that are not in a ruled table.** On the informal bill it read the
  item descriptions but not the money, and folded the quantity into the description
  ("MCB replacement (32A) x 2").

### The important result: no silent errors

Both invoices were sent to **needs_review**, never auto approved. The rules that caught them
were the missing-currency rule and the rule that escalates whenever the AI changed its answer
after a retry. So a weaker model produced **more escalations but zero silent errors**, which is
the safe direction to fail in. This is the clearest evidence so far that the escalation rules
do real work: they are what makes a cheaper or weaker model usable at all.

### Why a local model may still be worth revisiting

- **Privacy: the data never leaves the machine.** No invoice is sent to any third party, which
  matters for clients who cannot share financial documents outside their own systems, and it
  avoids the free-tier problem where data may be used to improve the provider's products.
- **No API costs and no rate limits**, so a long evaluation can run overnight.
- Faster hardware (a machine with a suitable GPU) would remove the main objection.

### Lessons learned

1. **A provider-agnostic design pays off.** Adding a local model was a small, self-contained
   change, and removing it again was just as small. Nothing else in the project had to change.
2. **Measure speed, not just accuracy.** A model can be accurate enough and still be unusable
   because a full test run takes over an hour.
3. **A weak model is safe if the safety net is good.** Judge a model by its silent errors, not
   only by its field accuracy.
4. **Re-adding Ollama later is roughly ten lines** in `backend/agent/workflow.py`: a `ChatOllama` branch with
   `temperature=0`, `num_ctx=8192` (the default context window is smaller and would silently cut
   off a long invoice) and a long client timeout, plus the `langchain-ollama` package. The
   per-model result folders are still in place, so a local model's results would stay separate.

## 8. Known limitations

- The test invoices are **computer-generated with a perfect text layer**. The set now covers multi-page, multi-language, discounts, freight, credit notes and informal layouts, but every file was produced by a script, not scanned or photographed.
- Scanned or photographed invoices are **not supported yet**, because OCR isn't included.
- Accuracy has only been measured with **Gemini** so far. A local model was tried briefly (section 7).
- **The three Day 3 fixes have not been measured end to end yet** (see section 6).
- The free Gemini tier allows **20 requests per day per model**, and one full evaluation needs at least 15, so there is room for roughly one run a day.

---

## 9. Open items

- [ ] **Re-run `python -m backend.evaluate` and compare against `reports/evaluation_report_BEFORE_FIX.md`** to see whether the three fixes brought the 20% silent error rate down. Blocked only by the daily Gemini quota.
- [ ] **Run `python -m backend.evaluate` with OpenAI** (`AI_PROVIDER=openai`) once an API key with credits is available, and compare the results with Gemini.
- [ ] **Test scanned or photographed invoices**, which needs OCR. Multi-page, discounts, freight and mixed-language invoices are now covered by invoice_06 to invoice_15.
- [ ] **Agree the convention for invoice_13**: when no subtotal is printed, should `subtotal` be null or a copy of the total? This decides whether that case is a bug or a preference.
- [x] **Add a `.gitignore` file** so Git never saves `.env` (secret keys), `venv/` (large, and can be rebuilt) or `__pycache__/` (Python's temporary files).
