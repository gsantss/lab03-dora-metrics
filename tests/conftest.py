import pytest


@pytest.fixture
def workflow_runs():
    return [
        {
            "workflow_id": 10,
            "conclusion": "success",
            "run_started_at": "2026-01-01T09:00:00Z",
            "updated_at": "2026-01-01T09:05:00Z",
        },
        {
            "workflow_id": 10,
            "conclusion": "failure",
            "run_started_at": "2026-01-01T10:00:00Z",
            "updated_at": "2026-01-01T10:05:00Z",
        },
        {
            "workflow_id": 10,
            "conclusion": "failure",
            "run_started_at": "2026-01-01T10:30:00Z",
            "updated_at": "2026-01-01T10:35:00Z",
        },
        {
            "workflow_id": 10,
            "conclusion": "success",
            "run_started_at": "2026-01-01T11:15:00Z",
            "updated_at": "2026-01-01T11:20:00Z",
        },
    ]
