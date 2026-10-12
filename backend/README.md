# Backend

FastAPI wraps the LangGraph invoice workflow in `app/agent/`. It accepts an invoice PDF, a
purchase-order PDF, or one ZIP containing up to 10 invoice PDFs. It also exposes deterministic
invoice-to-PO matching. Blocking PDF, ZIP, and AI work runs in a worker thread, and each request's
isolated temporary directory is removed after success or failure.

Firebase-backed workspace routes verify the browser's Firebase ID token and perform all Firestore
reads and writes server-side. Configure `FIREBASE_SERVICE_ACCOUNT_PATH` and `FIREBASE_PROJECT_ID`
in `backend/.env`; never expose the service-account JSON to Next.js.

The application code lives in `app/`: `api/` contains route handlers, `core/` owns configuration
and Firebase infrastructure, `models/` contains Pydantic contracts, and `services/` contains domain
logic. Developer utilities live separately in `scripts/`, while tests remain in `tests/`.

From the repository root, run:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000
```

Interactive API documentation is available at <http://localhost:8000/docs>.

Endpoints:

- `GET /api/health`
- `POST /api/invoices/check` for one PDF
- `POST /api/invoices/check-batch` for one ZIP batch
- `POST /api/purchase-orders/extract` for one purchase-order PDF
- `POST /api/invoices/two-way-match` for extracted invoice and saved-PO data
- Authenticated CRUD under `/api/invoices`, `/api/purchase-orders`, and `/api/invoice-analyses`
- `POST /api/purchase-orders/match` to find and match a saved PO without browser Firestore access

Successful invoice results include a `checks` list so clients can show the outcome of each
required-field, line-item, currency, arithmetic, and retry rule. The possible check statuses are
`passed`, `failed`, and `not_checked`.

`app/services/archives.py` validates archive paths, entry types, file counts, individual/total uncompressed
sizes, compression ratios, symbolic links, encryption, and nested archives. It streams entries to
generated temporary filenames instead of extracting archive paths, then calls the existing
`process_invoice()` sequentially for every PDF. See the repository README for complete limits,
response examples, and error behavior.

Evaluation utilities run as modules from the repository root:

```powershell
.\venv\Scripts\python.exe -m backend.scripts.evaluate
.\venv\Scripts\python.exe -m backend.scripts.peek_pdf
```
