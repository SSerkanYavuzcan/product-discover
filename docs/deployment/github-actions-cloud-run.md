# GitHub Actions Manual Deployment to Cloud Run

This guide explains the manual deployment workflow in:

- `.github/workflows/deploy-cloud-run.yml`

## What this workflow does

When you run the workflow manually from GitHub Actions, it will:

1. Build the Docker image from this repository.
2. Push the image to Artifact Registry.
3. Deploy that image to Cloud Run.

The workflow is manual-only (`workflow_dispatch`) and does not run on `push` or `pull_request`.

## Required GitHub repository variables

Configure these repository variables in GitHub:

- `GCP_PROJECT_ID`
- `GCP_REGION`
- `CLOUD_RUN_SERVICE`
- `ARTIFACT_REGISTRY_REPOSITORY`

## Additional GitHub repository variables (optional)

These variables are optional and only required for PostgreSQL mode:

- `DATABASE_BACKEND` (`sqlite` or `postgres`; defaults to `sqlite` when missing/blank)
- `CLOUD_SQL_CONNECTION_NAME` (required when `DATABASE_BACKEND=postgres`)
- `DATABASE_SECRET_NAME` (required when `DATABASE_BACKEND=postgres`)

## Required Google Cloud setup (outside this repository)

Before running the workflow, make sure Google Cloud is prepared:

- Artifact Registry repository exists in your target region.
- Cloud Run is enabled in the target project.
- Workload Identity Federation is configured for GitHub Actions.
- The service account exists and has required permissions for:
  - pushing images to Artifact Registry,
  - deploying/updating Cloud Run services.

## Database modes

### SQLite demo mode (default)

If `DATABASE_BACKEND` is missing, blank, or set to `sqlite`, the workflow deploys Cloud Run with:

- `DATABASE_BACKEND=sqlite`
- `DATABASE_PATH=/tmp/product_discover_agent.db`

Important notes:

- `/tmp` storage is ephemeral in Cloud Run.
- SQLite data is not persistent across deploys or restarts.
- This mode is suitable only for quick demos and lightweight testing.

### PostgreSQL Cloud SQL mode

If `DATABASE_BACKEND=postgres`, the workflow expects:

- `CLOUD_SQL_CONNECTION_NAME` repository variable (format: `project-id:region:instance-name`)
- `DATABASE_SECRET_NAME` repository variable (Secret Manager secret name that stores `DATABASE_URL`)

It then deploys with:

- `DATABASE_BACKEND=postgres`
- Cloud SQL instance attachment via `--add-cloudsql-instances`
- `DATABASE_URL` injection via `--set-secrets` from Google Secret Manager

The Cloud Run runtime service account must have:

- **Cloud SQL Client** role
- **Secret Manager Secret Accessor** role for the `DATABASE_URL` secret

Example `DATABASE_URL` (Cloud SQL Unix socket):

`postgresql://DB_USER:DB_PASSWORD@/DB_NAME?host=/cloudsql/PROJECT_ID:REGION:INSTANCE_NAME`

> ⚠️ Do not store `DATABASE_URL` as a plain GitHub variable. Use Google Secret Manager and `--set-secrets`.

## Quick PostgreSQL readiness checklist

1. Create a Cloud SQL PostgreSQL instance.
2. Create the target database.
3. Create a database user and password.
4. Store `DATABASE_URL` in Google Secret Manager.
5. Grant the Cloud Run runtime service account **Cloud SQL Client**.
6. Grant the Cloud Run runtime service account **Secret Manager Secret Accessor** for your database URL secret.
7. Set GitHub repository variables:
   - `DATABASE_BACKEND=postgres`
   - `CLOUD_SQL_CONNECTION_NAME=...`
   - `DATABASE_SECRET_NAME=...`
8. Run the **Deploy to Cloud Run** workflow manually.
9. Validate `GET /health` and `GET /dashboard/summary`.

## SQLite demo mode warning

This workflow deploys Cloud Run with temporary demo database settings:

- `DATABASE_BACKEND=sqlite`
- `DATABASE_PATH=/tmp/product_discover_agent.db`

Important notes:

- `/tmp` storage is ephemeral in Cloud Run.
- SQLite data is not persistent across instance restarts/replacements.
- You should move to Cloud SQL PostgreSQL before real production usage.

## Cloud Run environment variables set by the workflow

- `APP_NAME=product-discover-agent`
- `ENVIRONMENT=production`
- `LOG_LEVEL=INFO`
- `DATABASE_BACKEND=sqlite` (default mode) or `DATABASE_BACKEND=postgres`
- `DATABASE_PATH=/tmp/product_discover_agent.db` (sqlite mode only)
- `DATABASE_URL` (postgres mode only, from Secret Manager)


## Frontend CORS configuration

To allow the browser-based frontend to call this API, set the GitHub repository variable `ALLOWED_ORIGINS` and redeploy.

- Multiple origins are supported using commas.
- Use origins only (scheme + host [+ optional port]); do not include paths.

Examples:

- Production frontend:
  - `ALLOWED_ORIGINS=https://teknoify.com,https://www.teknoify.com`
- Local frontend development:
  - `ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`

Origin format:

- ✅ Correct: `https://teknoify.com`
- ❌ Incorrect: `https://teknoify.com/dashboard/agents/product-discover`

After updating `ALLOWED_ORIGINS`, rerun the **Deploy to Cloud Run** workflow manually.

## After deployment: quick test checklist

1. Open the deployed Cloud Run service URL.
2. Test `GET /health`.
3. Test `POST /ingest/barcode`.
4. Test `POST /jobs/{job_id}/process`.
5. Test `GET /products/{product_id}`.

If these checks pass, the service is reachable and the core API flow is working in the deployed environment.
