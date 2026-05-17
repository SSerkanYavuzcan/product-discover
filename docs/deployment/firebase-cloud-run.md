# Firebase Hosting + Cloud Run Deployment (Recommended Architecture)

This document describes a recommended production architecture for the Product Discover Agent.

## 1) Recommended architecture

```text
Frontend (Firebase Hosting)
        |
        | same-domain request to /api/**
        v
Firebase Hosting rewrite
        |
        v
Cloud Run service (FastAPI: Product Discover Agent API)
        |
        v
Database layer
```

In this pattern, your frontend is hosted on Firebase Hosting, while API traffic under `/api/**` is routed to your Cloud Run FastAPI service.

## 2) Why this architecture

- **Firebase Hosting** is a strong option for static/frontend hosting with global CDN support.
- **Cloud Run** is well-suited for running a containerized FastAPI backend.
- **Same-domain `/api/**` routing** helps simplify frontend integration and reduce cross-origin complexity.
- **SQLite** is fine for local development and demos, but is not recommended for production persistence.
- **Cloud SQL PostgreSQL** is the recommended future production database for durable, multi-instance relational storage.

## 3) Cloud Run container port

Cloud Run injects a `PORT` environment variable into the container at runtime.
Your container command should make Uvicorn listen on that port so Cloud Run can route traffic correctly.

In this project, the Docker command uses:

- `--host 0.0.0.0`
- `--port ${PORT:-8000}`

This keeps local container runs simple by defaulting to port `8000` when `PORT` is not set.

After deployment, verify the service by calling the `/health` endpoint on the Cloud Run URL.

## 4) Environment variables

Use environment variables in Cloud Run for API runtime configuration:

```env
APP_NAME=product-discover-agent
ENVIRONMENT=production
LOG_LEVEL=INFO
ALLOWED_ORIGINS=https://your-domain.com
DATABASE_PATH=data/product_discover_agent.db
```

> **Important:** `DATABASE_PATH` is suitable only for local/demo SQLite usage.
> A future production setup should use a PostgreSQL connection configuration.

## 5) Example frontend request

Your frontend can call the API through the Firebase rewrite path:

```javascript
fetch("/api/ingest/barcode", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ barcode: "3017620422003" })
});
```

## 6) Deployment sequence (checklist)

1. Build and deploy the FastAPI container to Cloud Run.
2. Configure Cloud Run environment variables.
3. Verify `GET /health` on the Cloud Run service URL.
4. Configure Firebase Hosting rewrites for `/api/**`.
5. Deploy Firebase Hosting.
6. Test the frontend calling `/api/health` or `/api/ingest/barcode`.
7. Move from SQLite to Cloud SQL PostgreSQL before production data usage.

## 7) Production notes (future improvements)

For a production-grade platform, plan the following next steps:

- **Cloud SQL PostgreSQL** for persistent relational storage.
- **Cloud Tasks** for asynchronous job processing.
- **Cloud Scheduler** for autonomous discovery orchestration.
- **Secret Manager** for credentials and sensitive configuration.
- **Cloud Logging and Cloud Monitoring** for observability.
- **Authentication / App Check** to protect public API usage.

---

This task documents architecture and examples only. It does **not** change current application runtime behavior.