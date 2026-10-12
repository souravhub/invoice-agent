# Invoice Agent — Complete Project Guide

Invoice Agent is a full-stack web application for extracting structured data from invoice and purchase-order PDFs, validating the extraction, and matching invoices against saved purchase orders.

It uses a Next.js frontend, a FastAPI backend, Firebase Authentication for Google sign-in, Firebase Admin/Firestore for private workspace data, and a configurable OpenAI or Gemini extraction provider.

> A result marked `auto_approved` means the configured checks passed. It is not payment authorization, proof of authenticity, or confirmation that goods were received.

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Folder structure](#folder-structure)
- [Requirements](#requirements)
- [Initial setup](#initial-setup)
- [Firebase setup](#firebase-setup)
- [Configuration](#configuration)
- [Run locally](#run-locally)
- [How to use the application](#how-to-use-the-application)
- [API reference](#api-reference)
- [Validation and matching](#validation-and-matching)
- [ZIP upload policy](#zip-upload-policy)
- [Testing and verification](#testing-and-verification)
- [Troubleshooting](#troubleshooting)
- [Security notes](#security-notes)

## Features

- Google sign-in through Firebase Authentication.
- Single invoice PDF extraction and validation.
- Secure ZIP batch processing for up to 10 invoice PDFs.
- Purchase-order PDF extraction and private PO register.
- Deterministic two-way invoice-to-PO matching.
- Dashboard with invoice, PO, review, and match-health metrics.
- Invoice analyzer with CSV and JSON export.
- FastAPI OpenAPI documentation at `/docs`.
- Server-side Firestore access: the browser never reads or writes Firestore directly.

## Architecture

```text
Browser (Next.js on :3000)
  │
  ├─ Firebase Authentication: Google sign-in and Firebase ID token
  │
  └─ HTTP API requests with Bearer ID token
       │
       ▼
FastAPI (on :8000)
  ├─ verifies Firebase ID token with Firebase Admin
  ├─ reads/writes Firestore for the signed-in user
  ├─ extracts invoice/PO data through the configured AI provider
  └─ runs deterministic checks and two-way matching
       │
       ├─ Firebase Admin → Firestore
       └─ OpenAI or Gemini → structured extraction
```

The frontend retains Firebase only for authentication. All saved invoices, analyses, purchase orders, matching lookups, updates, and deletions go through FastAPI.

## Folder structure

```text
invoice-agent/
├── frontend/
│   ├── src/
│   │   ├── app/                    # Next.js App Router pages and styles
│   │   └── lib/                    # Typed API client, Firebase Auth, CSV export
│   ├── .env.example
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── api/                    # Processing and workspace route handlers
│   │   ├── agent/                  # LangGraph workflow and data schema
│   │   ├── core/                   # Configuration and Firebase Admin integration
│   │   ├── models/                 # Pydantic request/response models
│   │   ├── services/               # Invoice, ZIP, and matching services
│   │   └── main.py                 # FastAPI bootstrap
│   ├── scripts/                    # Evaluation and PDF text inspection utilities
│   ├── tests/                      # Automated backend tests
│   ├── firebase.json               # Firebase CLI configuration
│   ├── firestore.rules             # Denies browser-side Firestore access
│   ├── .firebaserc                 # Firebase project alias
│   ├── .env.example
│   └── requirements.txt
├── invoices/                       # Sample/generated invoice PDFs
├── answer_keys/                    # Expected evaluation data
└── README.md                       # Short project reference
```

## Requirements

- Windows PowerShell commands below assume Windows.
- Python 3.11+ is recommended.
- Node.js 20+ and npm.
- A Firebase project with Google Authentication enabled.
- A Firestore database in the Firebase project.
- An OpenAI API key or Gemini API key for extraction.

## Initial setup

Run these commands from the repository root:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm --prefix frontend install
```

Create local configuration files:

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
```

`backend/.env` and `frontend/.env.local` are ignored by Git. Do not commit API keys or the Firebase service-account JSON file.

## Firebase setup

### 1. Enable Google Authentication

In Firebase Console:

1. Open **Authentication**.
2. Open **Sign-in method**.
3. Enable **Google**.
4. Add your local and deployed domains to **Authorized domains** if Firebase requests it.

The frontend uses the existing Firebase web configuration in `frontend/src/lib/firebase.ts` for Google sign-in.

### 2. Create Firestore

In Firebase Console:

1. Open **Firestore Database**.
2. Create the database if it does not exist.

### 3. Create a backend service account key

In Firebase Console:

1. Open **Project settings**.
2. Open **Service accounts**.
3. Under **Firebase Admin SDK**, select **Generate new private key**.
4. Store the downloaded JSON outside this repository, for example:

```text
D:\Trigital\secrets\ai-invoice-service-account.json
```

This key gives administrative access to Firebase. Never share it, add it to Git, or expose it to the frontend.

### 4. Deploy locked-down Firestore rules

The project is designed so only FastAPI uses Firestore. Deploy the supplied rules after installing and authenticating the Firebase CLI:

```powershell
Set-Location backend
firebase deploy --only firestore:rules
```

The rules deny direct browser reads and writes. Firebase Admin requests from FastAPI bypass rules after FastAPI verifies the caller's Firebase ID token.

## Configuration

### Backend: `backend/.env`

Choose one AI provider and add its valid API key.

```dotenv
# AI extraction provider
AI_PROVIDER=openai
AI_MODEL=gpt-4o-mini
OPENAI_API_KEY=your-openai-api-key

# Or use Gemini instead
# AI_PROVIDER=gemini
# AI_MODEL=your-supported-gemini-model
# GEMINI_API_KEY=your-gemini-api-key

# Browser origins allowed to call FastAPI
CORS_ORIGINS=http://localhost:3000

# Firebase Admin — backend only
FIREBASE_SERVICE_ACCOUNT_PATH=D:/Trigital/secrets/ai-invoice-service-account.json
FIREBASE_PROJECT_ID=ai-invoice-d6b8a
```

Use forward slashes in a Windows path inside `.env`, as shown above.

### Frontend: `frontend/.env.local`

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

This value is safe to expose because it only identifies the FastAPI server URL. Restart Next.js after changing it.

## Run locally

Open two PowerShell terminals in the repository root.

### Terminal 1 — FastAPI backend

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Expected output includes:

```text
Uvicorn running on http://127.0.0.1:8000
```

### Terminal 2 — Next.js frontend

```powershell
npm --prefix frontend run dev
```

Open these URLs:

| Purpose | URL |
| --- | --- |
| Web application | http://localhost:3000 |
| Backend health check | http://localhost:8000/api/health |
| Interactive API documentation | http://localhost:8000/docs |

## How to use the application

### Sign in

1. Open `http://localhost:3000`.
2. Select **Sign in with Google**.
3. Authenticate using an account enabled in your Firebase project.

The frontend obtains a Firebase ID token and includes it with authenticated workspace API calls.

### Save a purchase order

1. Go to **Purchase orders**.
2. Select **Upload PO**.
3. Upload one text-based purchase-order PDF, at most 20 MB.
4. Confirm the extracted PO data.

The backend rejects duplicate normalized PO numbers to avoid ambiguous invoice matching.

### Check an invoice

1. Go to **Two way match**.
2. Upload one invoice PDF or a ZIP archive of invoices.
3. Review extraction details, configured checks, review reasons, and PO matching results.
4. Download JSON when needed.

### Analyze invoices separately

The **Invoice analyzer** is a separate extraction history. It can process a PDF or ZIP, display saved results, export CSV, and delete historical analyses.

## API reference

The complete, interactive contract is available at `http://localhost:8000/docs` while the backend is running.

### Public processing endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Backend health check. |
| `POST` | `/api/invoices/check` | Extract and validate one invoice PDF. |
| `POST` | `/api/invoices/check-batch` | Process a ZIP batch of invoices. |
| `POST` | `/api/purchase-orders/extract` | Extract one PO PDF. |
| `POST` | `/api/invoices/two-way-match` | Match supplied invoice and PO data. |
| `POST` | `/api/invoices/recheck` | Re-run deterministic invoice checks. |

### Authenticated workspace endpoints

These require `Authorization: Bearer <Firebase-ID-token>`.

| Method | Path | Purpose |
| --- | --- | --- |
| `PUT` | `/api/users/me` | Synchronize basic signed-in user profile details. |
| `GET`, `POST` | `/api/invoices` | List or save invoice records. |
| `GET`, `PUT`, `DELETE` | `/api/invoices/{invoice_id}` | Read, update, or delete a saved invoice. |
| `GET`, `POST` | `/api/purchase-orders` | List or save POs. |
| `GET`, `PATCH`, `DELETE` | `/api/purchase-orders/{purchase_order_id}` | Read, change PO status, or delete a PO. |
| `POST` | `/api/purchase-orders/match` | Find and match the caller's saved PO. |
| `GET`, `POST` | `/api/invoice-analyses` | List or save a standalone analysis. |
| `POST` | `/api/invoice-analyses/batch` | Save multiple analysis results. |
| `DELETE` | `/api/invoice-analyses/{analysis_id}` | Delete an analysis. |

## Validation and matching

The backend returns transparent configured checks with one of these states:

| Status | Meaning |
| --- | --- |
| `passed` | The extracted values satisfy that rule. |
| `failed` | The rule found a discrepancy and human review is needed. |
| `not_checked` | Required extracted data was unavailable. |

Invoice validation covers required fields, line-item availability, currency, subtotal arithmetic, total arithmetic, and extraction retry behavior.

Two-way matching compares normalized PO number, vendor, currency, line descriptions, quantities, unit prices, individual line limits, and total limits. Its possible results are:

- `matched`
- `needs_review`
- `po_not_found`
- `ambiguous_po`
- `po_unavailable` for closed or cancelled purchase orders

## ZIP upload policy

ZIP files are handled without calling `extract()` or `extractall()`. Each accepted PDF is streamed to a generated temporary file within an isolated request directory.

| Rule | Limit or behavior |
| --- | --- |
| ZIP compressed upload | 20 MB maximum |
| PDFs per archive | 1 to 10 |
| Individual uncompressed PDF | 20 MB maximum |
| Total uncompressed PDF data | 100 MB maximum |
| Compression ratio | 100:1 maximum per PDF |
| Processing | Sequential |

The backend rejects path traversal, absolute or drive-letter paths, symbolic links, encrypted entries, nested archives, non-PDF entries, corrupt archives, and suspicious compression ratios.

OCR is not included. Image-only/scanned PDFs return an `unreadable_pdf` error.

## Testing and verification

Run backend tests:

```powershell
.\venv\Scripts\python.exe -m pytest backend\tests -q
```

Run frontend checks:

```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Run the PDF text-inspection utility without calling an AI provider:

```powershell
.\venv\Scripts\python.exe -m backend.scripts.peek_pdf
```

Run the full evaluation suite only when an AI provider key and quota are available:

```powershell
.\venv\Scripts\python.exe -m backend.scripts.evaluate
.\venv\Scripts\python.exe -m backend.scripts.evaluate --reuse
```

## Troubleshooting

### Browser says it cannot reach the invoice service

The backend is not running, the frontend points to the wrong API URL, or port 8000 is unavailable.

1. Start FastAPI with the command in [Run locally](#run-locally).
2. Open `http://localhost:8000/api/health`.
3. Confirm `frontend/.env.local` has `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.
4. Restart the Next.js development server after changing `.env.local`.

### Workspace API returns 401

Sign in again. FastAPI requires a valid Firebase ID token for saved workspace records.

### Workspace API returns 503 about Firebase Admin

Check both values in `backend/.env`:

```dotenv
FIREBASE_SERVICE_ACCOUNT_PATH=...
FIREBASE_PROJECT_ID=ai-invoice-d6b8a
```

Confirm the JSON file exists at that path and restart FastAPI.

### Google sign-in popup fails

Verify that Google is enabled under Firebase Authentication and that the local/deployed domain is authorized in Firebase.

### Firestore data cannot be loaded or saved

Verify that FastAPI is running with valid Firebase Admin credentials. The browser is intentionally denied direct Firestore access by `firestore.rules`.

### AI extraction returns 503

The selected provider is not fully configured. Check `AI_PROVIDER` and the appropriate API key in `backend/.env`, then restart FastAPI.

### AI extraction returns 502

The configured provider could not process the request. Check provider quota, billing, model availability, and the backend terminal logs. Do not expose provider errors or API keys in frontend logs.

### Upload is rejected

Check file type, size, PDF text availability, and ZIP policy limits. Text-based PDFs are required because OCR is not currently implemented.

## Security notes

- Keep `backend/.env`, `frontend/.env.local`, API keys, and service-account JSON files out of Git.
- Never use a Firebase Admin service-account key in the browser.
- Keep `firestore.rules` deployed so direct client Firestore access remains denied.
- Use HTTPS and a narrow `CORS_ORIGINS` list in production.
- Set `NEXT_PUBLIC_API_BASE_URL` to the production HTTPS API URL when deploying.
- Restrict Firebase Authentication authorized domains to your local and production domains.
- Rotate a service-account key immediately if it may have been exposed.

## Additional project files

- `README.md` — concise overview and common commands.
- `backend/README.md` — backend-specific notes.
- `frontend/README.md` — frontend-specific notes.
- `notes.md` — workflow rationale and evaluation history.
- `reports/` — preserved evaluation reports.
