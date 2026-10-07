# Backend

FastAPI wraps the preserved LangGraph invoice workflow in `agent/`. It accepts one
text-based PDF of at most 20 MB, processes it in a worker thread, and removes its isolated
temporary directory after either success or failure.

From the repository root, run:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```

Interactive API documentation is available at <http://localhost:8000/docs>.

Evaluation utilities run as modules from the repository root:

```powershell
.\venv\Scripts\python.exe -m backend.evaluate
.\venv\Scripts\python.exe -m backend.peek_pdf
```
