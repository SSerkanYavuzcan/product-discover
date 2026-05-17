# Firebase Hosting + Cloud Run Deployment

## Cloud Run container port

Cloud Run injects a `PORT` environment variable into the container at runtime.
Your container command should make Uvicorn listen on that port so Cloud Run can route traffic correctly.

In this project, the Docker command uses:

- `--host 0.0.0.0`
- `--port ${PORT:-8000}`

This keeps local container runs simple by defaulting to port `8000` when `PORT` is not set.

After deployment, verify the service by calling the `/health` endpoint on the Cloud Run URL.
