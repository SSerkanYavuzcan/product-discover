import sqlite3
from uuid import uuid4

import pytest

from app.jobs.models import DiscoveryJob, JobPriority, JobStatus, JobType
from app.jobs.repository import create_discovery_job
from app.processing import dispatcher
from app.storage.database import get_connection, initialize_database


def _make_job(job_type: JobType) -> DiscoveryJob:
    input_type = "barcode" if job_type == JobType.barcode_lookup else "url"
    input_value = "3017620422003" if job_type == JobType.barcode_lookup else "https://example.com/p"
    return DiscoveryJob(
        job_id=str(uuid4()),
        job_type=job_type,
        status=JobStatus.pending,
        priority=JobPriority.normal,
        input_type=input_type,
        input_value=input_value,
    )


def test_process_discovery_job_returns_none_for_missing_job(tmp_path) -> None:
    db_path = tmp_path / "dispatcher.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        assert dispatcher.process_discovery_job(connection, "missing") is None


def test_dispatches_barcode_job_to_barcode_processor(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "dispatcher.db"
    initialize_database(str(db_path))
    called = {"barcode": 0, "url": 0}

    def fake_barcode_processor(connection: sqlite3.Connection, job_id: str):
        called["barcode"] += 1
        return dispatcher.get_discovery_job(connection, job_id)

    def fake_url_processor(connection: sqlite3.Connection, job_id: str):
        called["url"] += 1
        return dispatcher.get_discovery_job(connection, job_id)

    monkeypatch.setattr(dispatcher, "process_barcode_lookup_job", fake_barcode_processor)
    monkeypatch.setattr(dispatcher, "process_url_extraction_job", fake_url_processor)

    with get_connection(str(db_path)) as connection:
        job = create_discovery_job(connection, _make_job(JobType.barcode_lookup))
        result = dispatcher.process_discovery_job(connection, job.job_id)

    assert result is not None
    assert called["barcode"] == 1
    assert called["url"] == 0


def test_dispatches_url_job_to_url_processor(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "dispatcher.db"
    initialize_database(str(db_path))
    called = {"barcode": 0, "url": 0}

    def fake_barcode_processor(connection: sqlite3.Connection, job_id: str):
        called["barcode"] += 1
        return dispatcher.get_discovery_job(connection, job_id)

    def fake_url_processor(connection: sqlite3.Connection, job_id: str):
        called["url"] += 1
        return dispatcher.get_discovery_job(connection, job_id)

    monkeypatch.setattr(dispatcher, "process_barcode_lookup_job", fake_barcode_processor)
    monkeypatch.setattr(dispatcher, "process_url_extraction_job", fake_url_processor)

    with get_connection(str(db_path)) as connection:
        job = create_discovery_job(connection, _make_job(JobType.url_extraction))
        result = dispatcher.process_discovery_job(connection, job.job_id)

    assert result is not None
    assert called["url"] == 1
    assert called["barcode"] == 0


def test_dispatcher_raises_for_unsupported_job_type(tmp_path) -> None:
    db_path = tmp_path / "dispatcher.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        job = create_discovery_job(connection, _make_job(JobType.image_extraction))
        with pytest.raises(ValueError, match="Unsupported discovery job type"):
            dispatcher.process_discovery_job(connection, job.job_id)
