# Invoice Extraction Agent

Reads an invoice PDF and turns it into clean, structured data: vendor, invoice number, date, PO number, currency, line items, subtotal, discount, shipping, tax and total. It then checks that the numbers add up and gives every invoice a verdict:

- **auto_approved**: safe to process without a person looking at it
- **needs_review**: a person must check it, with the reasons written in plain sentences

Built with Python, LangChain and LangGraph. The AI provider can be switched between **OpenAI** and **Google Gemini** in the `.env` file, with no code changes.

The full history, design reasoning and lessons learned are in **[notes.md](notes.md)**. Read it before changing the validation or escalation rules.

---

## How it works (short version)

```
PDF -> load_pdf -> extract (AI) -> validate (plain code) -> decide -> verdict
```

1. **load_pdf** pulls the text out of the PDF (no AI).
2. **extract** asks the AI to fill in the fixed form defined in `schema.py`.
3. **validate** checks the result with plain code rules. Missing information triggers a retry (up to 2 more). Figures that do not add up are **never** sent back to the AI; they are reported for human review. (notes.md, section 6, explains why.)
4. **decide** gives the verdict. The escalation rules are in one clearly marked block near the top of `workflow.py`.

| File / folder | Purpose |
|---|---|
| `main.py` | Runs the agent on one PDF and prints and saves the result |
| `evaluate.py` | Runs all test invoices and scores accuracy and escalation quality |
| `workflow.py` | The pipeline steps, escalation rules, and AI provider choice |
| `schema.py` | The form the AI must fill in |
| `peek_pdf.py` | Shows the text the AI receives (no AI call) |
| `make_test_invoices.py` | Creates the test invoices and their answer keys from the same data |
| `make_sample_invoice.py` | Creates `sample_invoice.pdf` |
| `invoices/` | 15 test invoice PDFs (all fake, script-generated) |
| `answer_keys/` | The correct answer for each test invoice |
| `reports/` | Saved evaluation reports, kept in Git (see below) |
| `results/` | Output of each run. **Not in Git**; recreated on every run |
| `notes.md` | Full project history and reasoning |

---

## Quick setup on Windows

1. **Install Python** (3.14 was used) from python.org. During install, tick **"Add python.exe to PATH"**.
2. **Open PowerShell in the project folder** and create a virtual environment:

   ```powershell
   python -m venv venv
   ```

3. **Install the packages:**

   ```powershell
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. **Create your `.env` file** from the example, then open it and put in your own API key:

   ```powershell
   Copy-Item .env.example .env
   ```

   | Setting | Meaning |
   |---|---|
   | `AI_PROVIDER` | `openai` or `gemini` (OpenAI if left out) |
   | `AI_MODEL` | Model name. If left out: `gpt-4o-mini` for OpenAI, `gemini-2.5-flash-lite` for Gemini |
   | `OPENAI_API_KEY` | Needed only when the provider is `openai` |
   | `GEMINI_API_KEY` | Needed only when the provider is `gemini` |

   `.env` holds secret keys. It is listed in `.gitignore` and must never be committed or shared.

**Optional:** run `.\venv\Scripts\Activate.ps1` once per terminal, then plain `python` works. If PowerShell says running scripts is disabled, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

More setup problems and fixes are in notes.md, section 2.

---

## How to run

**Extract one invoice** (1 to 3 AI calls):

```powershell
.\venv\Scripts\python.exe main.py invoices\invoice_03.pdf
```

It prints the extracted data and the verdict, and saves the JSON to `results\<provider>_<model>\`.

**Evaluate all test invoices** (at least 15 AI calls, one per invoice, more if retries happen):

```powershell
.\venv\Scripts\python.exe evaluate.py
```

The report is saved to `results\evaluation_report_<provider>_<model>.md`. If a run is cut short by rate limits, run it again with `--reuse`: invoices that already succeeded with the same provider and model are graded from their saved results, and only the missing ones call the AI.

```powershell
.\venv\Scripts\python.exe evaluate.py --reuse
```

**See what the AI receives** (no AI call): `.\venv\Scripts\python.exe peek_pdf.py`

### How to read an evaluation report

The most important number is the **silent error rate**: invoices the agent auto approved that were actually wrong, so nobody was asked to check them. Field accuracy can look excellent while silent errors make the system unusable. Each report explains the four outcome buckets (clean_pass, silent_error, caught, over_cautious).

---

## Warning: Gemini free tier (quota and privacy)

- **Quota:** the free tier allows about **20 requests per day per model**. One full evaluation needs at least 15. That is roughly **one full run per day**, so do not spend requests on single-invoice experiments on the day you need a full evaluation. The quota resets daily.
- **Privacy:** on the free tier, Google may use the data you send to improve its products. **Only use the fake, script-generated invoices in this project. Never send real company or client invoices** with a free key. Real data needs a paid account with proper data terms.

---

## Saved reports (`reports/`)

`results/` is ignored by Git, so the reports worth keeping are copied into `reports/`, which **is** committed:

| File | What it is |
|---|---|
| `reports/evaluation_report_BEFORE_FIX.md` | **The baseline.** Gemini `gemini-3-flash-preview`, 15 invoices, before the three Day 3 fixes. 97.0% field accuracy but **20% silent errors** (invoices 07, 08 and 13). |

**The after-fix report is still pending.** The three fixes have not yet been measured end to end (see Next steps, item 1). When that run is done, copy its report from `results\` into `reports\` as `evaluation_report_AFTER_FIX.md` so it is kept in Git. Do the same for any later run worth keeping.

---

## Current status

| Task | What it asks for | Where it lives in the project | Status |
|---|---|---|---|
| **S1** | Build the extraction agent and test it on 5 invoices | `workflow.py`, `schema.py`, `main.py`; invoices 01–05 | **Done.** 45/45 fields correct (100%) on Gemini |
| **S2** | Template with shadow mode, evaluation harness, escalation logic, deployment configs | Evaluation: `evaluate.py`. Escalation: the rules block near the top of `workflow.py` | **Evaluation and escalation done.** Shadow mode and deployment configs **not started** |
| **S3** | Test on 20 diverse invoices, with per-field accuracy and the top 3 failure causes | `invoices/`, `answer_keys/`, `make_test_invoices.py`, `reports/` | **15 of 20 done.** Root cause of the silent errors found and three fixes applied; **after-fix run pending** |
| **S4** | Internal playbook of 1500+ words | [notes.md](notes.md) holds the raw material | **Notes collected; playbook not yet written** |

**More on S3:** the 15-invoice run found 20% silent errors. The cause was the retry loop pushing the AI to invent data so the sums would close. The three fixes are new discount and shipping fields, never sending sums back to the AI, and sending any retried invoice to review. So far they have only been checked offline.

---

## Next steps for whoever picks this up

In priority order:

1. **Run the after-fix evaluation and compare it to the baseline.**
   - In `.env`, set `AI_PROVIDER=gemini` and `AI_MODEL=gemini-3-flash-preview`. Set the model explicitly: the code's default Gemini model is different, and the comparison is only fair on the same model as the baseline.
   - Run `evaluate.py` on a day with unused quota. Run it **without** `--reuse` the first time, so every invoice is extracted with the fixed code.
   - Compare the new report with `reports/evaluation_report_BEFORE_FIX.md`. Look first at the **silent error rate** (baseline 20%, goal 0%), then the buckets, then field accuracy. Compare **percentages, not raw counts**: the baseline graded 9 fields per invoice, and the current grader uses 11.
   - Expect more **over_cautious** results than before, because retried invoices now always go to review. That is acceptable; silent errors are not.
   - Copy the new report into `reports/` (for example `evaluation_report_AFTER_FIX.md`) and record the result in notes.md.
2. **If any silent errors remain**, look at those invoices' saved output in `results\` and find the cause before adding new tests.
3. **Decide the invoice_13 convention**: when an invoice prints no subtotal, should `subtotal` be empty (null) or a copy of the total? Update the answer key to match the decision.
4. **Finish S3: build the remaining 5 test invoices** in `make_test_invoices.py` (each with a deliberate trap and an answer key made from the same data). Then evaluate all 20 and write up per-field accuracy and the top 3 failure causes.
5. **S2: shadow mode.** Not started.
6. **S2: template / deployment configs.** Not started.
7. **S4: write the internal playbook** (1500+ words) from notes.md.
8. **Later:** evaluate with OpenAI and compare; add support for scanned or photographed invoices (needs OCR). See notes.md, sections 8 and 9.

---

## More detail

[notes.md](notes.md) has the full day-by-day history: how the pipeline works, the test set and its traps, the scoring rules, the root cause of the silent errors, the three fixes and why each was chosen, the local model (Ollama) trial, known limitations and open items.
