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


def _commit(release_id, published_at, author_date, message="chore: ajuste"):
    return {
        "release_id": release_id,
        "release_published_at": published_at,
        "commit_author_date": author_date,
        "commit_message": message,
    }


@pytest.fixture
def lead_time_commits():
    # v1.1 é o exemplo da RQ 02 (13, 5 e 1 dias); v1.2 tem um único commit de 1 dia.
    return [
        _commit(11, "2026-03-15T00:00:00Z", "2026-03-02T00:00:00Z"),
        _commit(11, "2026-03-15T00:00:00Z", "2026-03-10T00:00:00Z"),
        _commit(11, "2026-03-15T00:00:00Z", "2026-03-14T00:00:00Z"),
        _commit(12, "2026-03-20T00:00:00Z", "2026-03-19T00:00:00Z"),
    ]


@pytest.fixture
def cfr_releases():
    # Exemplo da RQ 03 (b): v2.3.0 é corrigida pela v2.3.1 dois dias depois.
    return [
        {"release_id": 230, "tag_name": "v2.3.0", "published_at": "2026-05-10T12:00:00Z"},
        {"release_id": 231, "tag_name": "v2.3.1", "published_at": "2026-05-12T12:00:00Z"},
        {"release_id": 240, "tag_name": "v2.4.0", "published_at": "2026-06-01T12:00:00Z"},
        {"release_id": 250, "tag_name": "v2.5.0", "published_at": "2026-06-20T12:00:00Z"},
    ]


@pytest.fixture
def cfr_commits():
    return [
        _commit(231, "2026-05-12T12:00:00Z", "2026-05-11T09:00:00Z", "fix: crash ao abrir arquivo"),
        _commit(240, "2026-06-01T12:00:00Z", "2026-05-25T09:00:00Z", "feat: novo menu"),
        _commit(250, "2026-06-20T12:00:00Z", "2026-06-15T09:00:00Z", "feat: exportar PDF"),
    ]
