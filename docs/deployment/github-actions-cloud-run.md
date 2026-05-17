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

## Required GitHub repository secrets

Configure these repository secrets in GitHub:

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`

## Required Google Cloud setup (outside this repository)

Before running the workflow, make sure Google Cloud is prepared:

- Artifact Registry repository exists in your target region.
- Cloud Run is enabled in the target project.
- Workload Identity Federation is configured for GitHub Actions.
- The service account exists and has required permissions for:
  - pushing images to Artifact Registry,
  - deploying/updating Cloud Run services.

## Demo database warning

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
- `DATABASE_BACKEND=sqlite`
- `DATABASE_PATH=/tmp/product_discover_agent.db`

## After deployment: quick test checklist

1. Open the deployed Cloud Run service URL.
2. Test `GET /health`.
3. Test `POST /ingest/barcode`.
4. Test `POST /jobs/{job_id}/process`.
5. Test `GET /products/{product_id}`.

If these checks pass, the service is reachable and the core API flow is working in the deployed environment.
