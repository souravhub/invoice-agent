# Frontend

The Next.js interface accepts one PDF or one ZIP containing up to 10 PDFs. It calls the matching
FastAPI endpoint, presents individual or expandable batch results, and downloads the complete
response as JSON. The browser applies the 20 MB compressed upload limit before sending the file;
the backend independently enforces all security limits.

Firebase in the frontend is limited to Google authentication. `src/lib/api.ts` attaches the user's ID
token to workspace API requests; invoice, purchase-order, and analysis data is read and written only
through FastAPI, which owns the Firebase Admin/Firestore integration.

Each successful invoice displays the backend-provided configured checks, including required
fields, line items, currency, subtotal arithmetic, total arithmetic, and retry changes. It labels
each item as **Passed**, **Needs review**, or **Not checked** and does not calculate these results in
the browser.

From `frontend/`, run:

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev
```

Open <http://localhost:3000>.
