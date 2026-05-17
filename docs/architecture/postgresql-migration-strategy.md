# PostgreSQL Migration Strategy (Future Plan)

## Purpose

This document describes a **future** migration path from local SQLite to production-ready Cloud SQL PostgreSQL.

## Why SQLite stays for local development

SQLite is currently a good fit for local development because it is simple, file-based, and easy to run without extra infrastructure.

However, SQLite is **not recommended for production persistence** in this project because production workloads typically need stronger concurrency handling, managed backups, operational controls, and multi-instance reliability.

## Target production database architecture

```text
Cloud Run FastAPI API
        |
        v
Cloud SQL PostgreSQL
        |
        v
SQLAlchemy repository layer
        |
        v
Alembic migrations
```

This target design supports managed production operations while preserving clear schema evolution.

## Phased migration plan

### Phase 1 — Keep SQLite for local development

- Preserve current SQLite behavior.
- Keep current tests working.
- Avoid breaking existing repository functions.

### Phase 2 — Introduce database backend configuration

- Add `DATABASE_BACKEND=sqlite` or `postgres`.
- Add `DATABASE_URL` for PostgreSQL.
- Keep `DATABASE_PATH` for SQLite.
- Keep defaults local-friendly.

### Phase 3 — Add SQLAlchemy foundation

- Add engine/session management.
- Add SQLAlchemy models/tables for:
  - `products`
  - `product_evidence`
  - `discovery_jobs`
  - `batch_jobs`
- Keep repository interface stable so API behavior does not change.

### Phase 4 — Add Alembic migrations

- Create an initial migration reflecting the existing schema.
- Add future migrations for:
  - `source_registry`
  - `discovered_urls`
  - `extraction_runs`
  - `change_events`

### Phase 5 — Refactor repositories gradually

- Migrate product repository first.
- Migrate job repository second.
- Avoid a big-bang rewrite.
- Validate behavior parity at each step.

### Phase 6 — Cloud SQL production deployment

- Store DB credentials in Secret Manager.
- Configure Cloud SQL connectivity for Cloud Run.
- Run migrations during deployment or in a controlled release step.

## Initial PostgreSQL table groups

Planned initial table groups:

- `products`
- `product_evidence`
- `discovery_jobs`
- `batch_jobs`
- `source_registry`
- `discovered_urls`
- `extraction_runs`
- `change_events`

## Risks and mitigations

- **Data migration risk**  
  Mitigation: run staged migration rehearsals with backups and row-count verification.

- **Repository rewrite risk**  
  Mitigation: migrate repositories incrementally behind stable interfaces.

- **Connection pooling risk**  
  Mitigation: size SQLAlchemy pool settings for Cloud Run concurrency and validate under load.

- **Local/prod behavior drift**  
  Mitigation: keep cross-backend contract tests and consistent repository-level assertions.

- **Migration rollback risk**  
  Mitigation: define rollback procedures per migration and test them before production rollout.

## Explicit non-goals for this step

- No code changes in this step.
- No database migration in this step.
- No production credential handling in this step.

---

This is a planning document only. No application behavior changes are included here.
