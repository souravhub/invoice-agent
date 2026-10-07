# Invoice Agent Web App

A small local web app that extracts structured data from a text-based invoice PDF, applies the
existing completeness and arithmetic checks, and explains whether the result needs human review.
The original LangGraph extraction, validation, retry, and escalation behavior is preserved in
`backend/agent/` and used by the API and evaluation utilities.

> **Important:** “Passed configured checks” only means that the extracted fields passed this
> project's configured rules. It is not payment authorization and is not proof that an invoice or
> vendor is authentic.

## Project structure

```text
invoice-agent/
├── frontend/                 Next.js, TypeScript, and Tailwind CSS interface
│   ├── app/
│   ├── lib/
│   └── .env.example          Public backend URL only
├── backend/                  FastAPI application
│   ├── main.py               HTTP endpoints, upload limits, CORS, temp-file lifecycle
│   ├── evaluate.py           Evaluation harness
│   ├── peek_pdf.py           Inspect extracted PDF text without calling AI
│   ├── service.py            PDF/config validation and synchronous graph adapter
│   ├── schemas.py            Documented request/response contracts
│   ├── agent/
│   │   ├── workflow.py       Preserved LangGraph pipeline and escalation rules
│   │   └── schema.py         Structured invoice and line-item models
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example          AI provider/model/key settings
├── invoices/                 Preserved generated test PDFs
├── answer_keys/              Preserved expected results
├── reports/                  Preserved evaluation reports
└── notes.md                  Preserved project history and rule rationale
```

## Prerequisites

- Python 3.12 or newer
- Node.js 20.9 or newer (Node.js 22 LTS is recommended)
- An OpenAI or Google Gemini API key

OCR is intentionally not included in this version. Image-only/scanned PDFs receive a useful error
and must be converted to text-searchable PDFs before upload.

## Install on Windows PowerShell

Run these commands from the repository root:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
npm --prefix frontend install
Copy-Item frontend\.env.example frontend\.env.local
```

Open `backend\.env` and select one provider. Keep real keys only in this file:

```dotenv
AI_PROVIDER=openai
AI_MODEL=gpt-4o-mini
OPENAI_API_KEY=replace-with-your-openai-api-key
GEMINI_API_KEY=replace-with-your-gemini-api-key
CORS_ORIGINS=http://localhost:3000
```

For Gemini, set `AI_PROVIDER=gemini`, choose a supported Gemini model, and set
`GEMINI_API_KEY`. Actual `.env` files are ignored by Git. The frontend environment contains only
`NEXT_PUBLIC_API_BASE_URL`, which is intentionally public browser configuration.

## Run both servers

Open two PowerShell windows in the repository root.

Backend terminal:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend terminal:

```powershell
npm --prefix frontend run dev
```

Open:

- Web app: <http://localhost:3000>
- Backend health check: <http://localhost:8000/api/health>
- Interactive API documentation: <http://localhost:8000/docs>

The frontend defaults to `http://localhost:8000`. To use another backend address, edit
`frontend\.env.local`, then restart the frontend:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## API

### `POST /api/invoices/check`

Send one multipart form field named `file`. It must be a PDF no larger than 20 MB. The endpoint
checks both the declared type and PDF content, rejects textless scans, runs the blocking LangGraph
workflow in FastAPI's worker thread pool, and removes the request's isolated temporary directory on
success or failure.

Successful responses contain:

```json
{
  "invoice": {
    "vendor_name": "Example Vendor",
    "invoice_number": "INV-001",
    "invoice_date": "2026-10-07",
    "po_number": "PO-100",
    "currency": "USD",
    "line_items": [],
    "subtotal": 100,
    "discount": null,
    "shipping": null,
    "tax": 10,
    "total": 110
  },
  "status": "auto_approved",
  "reasons": [],
  "attempts": 1
}
```

The internal status remains `auto_approved` to preserve evaluation compatibility. The browser
deliberately presents it as **Passed configured checks**. Errors use a stable safe shape such as
`{"error":{"code":"unreadable_pdf","message":"..."}}`; provider details, secrets, and stack
traces are never returned to the browser.

### `GET /api/health`

Returns `{"status":"ok"}` without calling an AI provider.

## Evaluation utilities

Run these as backend modules from the repository root. They load `backend\.env`:

```powershell
.\venv\Scripts\python.exe -m backend.evaluate
.\venv\Scripts\python.exe -m backend.evaluate --reuse
.\venv\Scripts\python.exe -m backend.peek_pdf
```

CLI output remains under `results\<provider>_<model>\`. Evaluation reports remain under
`results\`; committed reference reports, test invoices, answer keys, generator scripts, and
`notes.md` are unchanged.

## Verification

Backend tests use a mocked workflow result, so they require no AI key and spend no provider quota:

```powershell
.\venv\Scripts\python.exe -m pytest backend\tests -q
```

The tests cover health, safe API response shape, content-type and PDF-signature validation, the
upload limit, cleanup after provider failure, and the preserved arithmetic/retry escalation rules.

Build and type-check the frontend:

```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

## Preserved workflow behavior

```text
PDF → load PDF text → AI extraction → deterministic validation → decision
                         ↑                 │
                         └─ retry only missing extraction data (maximum two retries)
```

- Missing vendor, total, or line items can trigger a retry.
- Printed arithmetic mismatches never trigger an AI retry; they require review instead.
- Discounts and shipping remain part of the existing arithmetic rules.
- An answer changed after a retry always requires human review.
- Missing required fields, currency, line items, exhausted retries, or inconsistent totals require
  review.

See [notes.md](notes.md) for the original reasoning, evaluation history, and known limitations.
