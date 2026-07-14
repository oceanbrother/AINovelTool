# Frontend (thin)

The project is backend + AI-engineering first; the frontend is intentionally
thin and can be added later (React + Vite). It only needs to:

1. Manage settings (projects / characters / world / chapters) via the CRUD API.
2. Call `POST /projects/{id}/generate/continue` and render the **SSE** token
   stream live (续写模式).
3. Call `POST /projects/{id}/generate/breakthrough` and show the branch cards
   (破壁模式).
4. (v1.1) Surface literary citations and idiom suggestions in the editor margin.

Until then, the FastAPI Swagger UI at `http://localhost:8000/docs` is a fully
usable interface for every endpoint.
