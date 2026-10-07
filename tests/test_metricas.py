import pytest

from metricas import (
    cfr_ci,
    classify_cfr,
    classify_deployment_frequency,
    classify_lead_time,
    classify_recovery,
    lead_time_release,
    lead_times_commits,
    median_recovery_hours,
    overall_classification,
    recovery_episodes,
)


def test_lead_time_release_exemplo():
    result = lead_time_release(
        "2026-03-15T00:00:00Z",
        [
            "2026-03-02T00:00:00Z",
            "2026-03-10T00:00:00Z",
            "2026-03-14T00:00:00Z",
        ],
    )
    assert result == 13 * 24


def test_lead_time_release_sem_commits():
    assert lead_time_release("2026-03-15T00:00:00Z", []) is None


def test_lead_time_por_commit():
    values = lead_times_commits(
        "2026-03-15T00:00:00Z",
        ["2026-03-02T00:00:00Z", "2026-03-10T00:00:00Z", "2026-03-14T00:00:00Z"],
    )
    assert values == [13 * 24, 5 * 24, 24]


def test_cfr_ignora_cancelled():
    runs = [
        {"conclusion": "success"},
        {"conclusion": "failure"},
        {"conclusion": "cancelled"},
    ]
    assert cfr_ci(runs) == 0.5


def test_cfr_sem_runs_validos():
    assert cfr_ci([{"conclusion": "cancelled"}]) is None


def test_recovery_exemplo(workflow_runs):
    values, censored = recovery_episodes(workflow_runs)
    assert values == pytest.approx([4 / 3])
    assert censored == 0
    assert median_recovery_hours(workflow_runs) == pytest.approx(4 / 3)


def test_failure_never_recovered_is_censored():
    runs = [
        {
            "workflow_id": 1,
            "conclusion": "success",
            "run_started_at": "2026-01-01T09:00:00Z",
            "updated_at": "2026-01-01T09:05:00Z",
        },
        {
            "workflow_id": 1,
            "conclusion": "failure",
            "run_started_at": "2026-01-01T10:00:00Z",
            "updated_at": "2026-01-01T10:02:00Z",
        },
    ]
    values, censored = recovery_episodes(runs)
    assert values == []
    assert censored == 1


@pytest.mark.parametrize(
    "value,expected",
    [(7, "Elite"), (1, "High"), (0.25, "Medium"), (0.01, "Low")],
)
def test_classify_deployment_frequency(value, expected):
    assert classify_deployment_frequency(value) == expected


@pytest.mark.parametrize(
    "hours,expected",
    [(1, "Elite"), (24, "High"), (24 * 7, "Medium"), (24 * 30, "Low")],
)
def test_classify_lead_time(hours, expected):
    assert classify_lead_time(hours) == expected


@pytest.mark.parametrize(
    "value,expected",
    [(0.10, "Elite"), (0.20, "High"), (0.40, "Medium"), (0.50, "Low")],
)
def test_classify_cfr(value, expected):
    assert classify_cfr(value) == expected


@pytest.mark.parametrize(
    "hours,expected",
    [(0.5, "Elite"), (2, "High"), (48, "Medium"), (24 * 8, "Low")],
)
def test_classify_recovery(hours, expected):
    assert classify_recovery(hours) == expected


def test_overall_classification_rounds_median_down():
    assert overall_classification(["Elite", "High", "High", "Low"]) == "High"


def test_overall_requires_four_metrics():
    with pytest.raises(ValueError):
        overall_classification(["Elite"])
