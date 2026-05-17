# Product Discover Agent

Product Discover Agent is an open-source product intelligence system designed to discover, enrich, validate, and store product information from multiple input sources.

## Status

This project is in **early development**. The current repository contains the initial service foundation only.

## Planned discovery modes

- Reactive Discovery
- Batch Discovery
- Autonomous Discovery

## Run locally

### Prerequisites

- Python 3.11+

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

## Run tests

```bash
pytest
```

## Lint

```bash
ruff check .
```
