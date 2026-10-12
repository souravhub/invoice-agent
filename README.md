# Invoice Agent Web App

A local Next.js and FastAPI application that extracts structured data from invoice and purchase-order
PDFs, applies deterministic validation and two-way matching checks, and explains whether each result
needs human review. Upload one invoice PDF, one ZIP batch containing up to 10 invoices, or save a PO
in the dedicated purchase-order register.

> "Passed configured checks" is not payment authorization and does not prove that an invoice or
> vendor is authentic.

## Structure

```text
invoice-agent/
|-- frontend/                 Next.js, TypeScript, Tailwind CSS
|   |-- src/
|   |   |-- app/              App Router pages and global styles
|   |   `-- lib/              API, Firebase Auth, and CSV utilities
|   |-- .env.example          Public backend URL
|   `-- package.json
|-- backend/                  FastAPI application
|   |-- app/
|   |   |-- api/              Processing/workspace routes and router composition
|   |   |-- core/             Configuration and Firebase infrastructure
|   |   |-- models/           Pydantic API contracts
|   |   |-- services/         Invoice, matching, and archive services
|   |   |-- agent/            LangGraph workflow and domain schema
|   |   `-- main.py           FastAPI bootstrap and middleware
|   |-- scripts/              Evaluation and PDF inspection utilities
|   |-- tests/                API, security, and business-rule tests
|   |-- requirements.txt
|   `-- .env.example          Private provider configuration
|-- invoices/                 Generated test PDFs
|-- answer_keys/              Expected evaluation results
|-- reports/                  Preserved evaluation reports
`-- notes.md                  Project history and rule rationale
```

## Install on Windows PowerShell

From the repository root:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm --prefix frontend install
```

Create configuration files if they do not already exist:

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
```

Add the selected provider key to `backend\.env`:

```dotenv
AI_PROVIDER=openai
AI_MODEL=gpt-4o-mini
OPENAI_API_KEY=replace-with-your-openai-api-key
GEMINI_API_KEY=replace-with-your-gemini-api-key
CORS_ORIGINS=http://localhost:3000
FIREBASE_SERVICE_ACCOUNT_PATH=C:/path/to/firebase-service-account.json
FIREBASE_PROJECT_ID=ai-invoice-d6b8a
```

For Gemini, use `AI_PROVIDER=gemini`, select a supported Gemini model, and configure
`GEMINI_API_KEY`. Actual `.env` files are ignored by Git.

Download a Firebase service-account JSON from Firebase Console and keep it outside the repository.
Only the FastAPI process receives this credential. The browser uses Firebase Authentication for
Google sign-in, sends the resulting ID token to FastAPI, and never accesses Firestore directly.

## Run

Open two PowerShell terminals in the repository root.

Terminal 1 - backend:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 - frontend:

```powershell
npm --prefix frontend run dev
```

Open:

- Web app: <http://localhost:3000>
- Health check: <http://localhost:8000/api/health>
- Interactive OpenAPI documentation: <http://localhost:8000/docs>

## Browser usage

### Purchase-order register

1. Open **Purchase orders** from the sidebar.
2. Upload a text-based purchase-order PDF no larger than 20 MB.
3. The app extracts the PO number, vendor, currency, line items, and totals and asks FastAPI to save
   them under the signed-in user's private workspace.
4. Duplicate normalized PO numbers are rejected so invoice lookup stays unambiguous.

Firestore access is performed by Firebase Admin in FastAPI. Keep client Firestore rules locked down;
the included rules remain useful for denying accidental browser-side database access.

### One PDF

1. Select a text-based `.pdf` no larger than 20 MB.
2. Click **Check invoice**.
3. Review the overall status and each field, line-item, calculation, and extraction check.
4. When the invoice contains a PO number, the app looks for the corresponding saved PO and performs
   a two-way match. A missing, ambiguous, closed, or cancelled PO requires review.
5. Download the complete JSON result if needed.

### ZIP batch

1. Select a `.zip` no larger than 20 MB compressed.
2. The archive must contain 1 to 10 PDF files and no other file types.
3. Click **Check batch**.
4. Review the summary and expand each invoice result.
5. Download the complete batch response as JSON.

PDFs are processed sequentially to avoid bursts of AI-provider requests. One invalid or scanned PDF
produces an error for that file without removing successful results from the same accepted batch.
Selecting another upload clears all previous results and errors.

OCR is not included. Image-only/scanned PDFs return an `unreadable_pdf` result.

## API

### `GET /api/health`

Returns `{"status":"ok"}` without calling an AI provider.

### `POST /api/invoices/check`

Multipart field: `file`

- Accepts one `application/pdf` file.
- Maximum upload size: 20 MB.
- Validates PDF signature, parsing, and extractable text.
- Returns `InvoiceCheckResponse` with `invoice`, `status`, `reasons`, `attempts`, and `checks`.

Each `checks` entry has a stable `id`, display `label`, explanatory `detail`, and one of these
statuses: `passed`, `failed`, or `not_checked`. The frontend displays the required-field,
line-item, currency, subtotal arithmetic, total arithmetic, and extraction-retry outcomes. A
calculation is `not_checked` when the required extracted values are unavailable.

### `POST /api/invoices/check-batch`

Multipart field: `file`

- Accepts `application/zip` or `application/x-zip-compressed`.
- Also accepts `.zip` with `application/octet-stream` for browser compatibility.
- Maximum compressed upload: 20 MB.
- Maximum PDFs: 10.
- Maximum individual uncompressed PDF: 20 MB.
- Maximum total uncompressed PDF content: 100 MB.
- Maximum permitted compression ratio per PDF: 100:1.
- Processing order: sequential.

Example response:

```json
{
  "summary": {
    "total": 2,
    "succeeded": 1,
    "failed": 1
  },
  "files": [
    {
      "filename": "invoice_01.pdf",
      "result": {
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
      },
      "error": null
    },
    {
      "filename": "scan.pdf",
      "result": null,
      "error": {
        "code": "unreadable_pdf",
        "message": "No readable text was found. Scanned PDFs need OCR, which is not supported yet."
      }
    }
  ]
}
```

An accepted archive returns HTTP 200 even when individual PDFs fail. Whole-archive validation
failures return `400 invalid_zip`; incomplete provider configuration returns 503.

### `POST /api/purchase-orders/extract`

Multipart field: `file`

- Accepts one text-based `application/pdf` purchase order, at most 20 MB.
- Returns the extracted `purchase_order`, extraction checks, and attempt count.

### `POST /api/invoices/two-way-match`

Accepts extracted invoice and purchase-order JSON. Matching is deterministic: it compares normalized
PO numbers, vendors, currencies, line descriptions, quantities, unit prices, line limits, and the PO
total limit. Closed and cancelled POs return `po_unavailable`; failed or incomplete comparisons return
`needs_review`. This is a two-way match and does not verify receipt of goods.

## ZIP security policy

The backend uses Python's standard `zipfile` module but never calls `extract()` or `extractall()`.
Every PDF is streamed to a generated UUID filename inside the request's isolated temporary
directory. The complete directory is deleted after success or failure.

The backend rejects:

- Empty archives and archives with more than 10 PDFs.
- Non-PDF entries and nested ZIP files.
- Absolute paths, Windows drive paths, and any `..` traversal component.
- Symbolic links and encrypted entries.
- Oversized individual or total uncompressed content.
- Suspicious compression ratios that may indicate a ZIP bomb.
- Corrupt or unreadable archives.

Both declared ZIP sizes and actual bytes produced during decompression are enforced.

## Error behavior

Whole-request errors use:

```json
{"error":{"code":"invalid_zip","message":"The ZIP contains an unsafe file path."}}
```

Provider details, API keys, and stack traces are not returned to the browser. Within an accepted
batch, invalid PDFs, scanned PDFs, and provider failures use the same safe error structure on the
corresponding file result.

## Verification

Backend tests use mocked AI results and do not spend provider quota:

```powershell
.\venv\Scripts\python.exe -m pytest backend\tests -q
```

Frontend verification:

```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Tests cover the single-PDF API, batch response contract, upload limits, archive cleanup, partial
success, path traversal, Windows paths, symbolic links, nested archives, non-PDF entries, excessive
file counts, suspicious compression ratios, and the preserved workflow rules.

## Evaluation utilities

These development-only commands are not required to use the web app and may call the configured AI
provider many times:

```powershell
.\venv\Scripts\python.exe -m backend.scripts.evaluate
.\venv\Scripts\python.exe -m backend.scripts.evaluate --reuse
.\venv\Scripts\python.exe -m backend.scripts.peek_pdf
```

See [notes.md](notes.md) for the original workflow reasoning and evaluation history.
