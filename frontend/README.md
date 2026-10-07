# Frontend

The Next.js interface accepts one PDF, calls the FastAPI backend, presents the extracted fields
and configured-check outcome, and downloads the complete response as JSON.

From `frontend/`, run:

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev
```

Open <http://localhost:3000>.
