import pytest

from datetime import datetime, timezone

from metricas import (
    censored_recovery_ratio,
    cfr_ci,
    cfr_delivery,
    classify_cfr,
    classify_deployment_frequency,
    classify_lead_time,
    classify_recovery,
    deployment_frequency,
    is_corrective_release,
    is_patch_bump,
    lead_time_release,
    lead_times_commits,
    median_lead_time_commits,
    median_lead_time_release,
    median_recovery_hours,
    overall_classification,
    parse_version,
    recovery_episodes,
)

WINDOW_END = "2026-09-30T23:59:59Z"


def test_deployment_frequency_divide_releases_pelas_semanas():
    assert deployment_frequency(3, "2026-01-01T00:00:00Z", "2026-01-15T00:00:00Z") == 1.5


def test_deployment_frequency_janela_de_12_meses():
    start = datetime(2025, 10, 1, tzinfo=timezone.utc)
    end = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
    assert deployment_frequency(52, start, end) == pytest.approx(52 / 52.14, rel=1e-3)


def test_deployment_frequency_rejeita_janela_vazia():
    with pytest.raises(ValueError):
        deployment_frequency(1, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")


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


def test_mediana_lead_time_por_release(lead_time_commits):
    # releases com 312 h (v1.1) e 24 h (v1.2)
    assert median_lead_time_release(lead_time_commits) == (312 + 24) / 2


def test_mediana_lead_time_por_commit(lead_time_commits):
    # commits com 312, 120, 24 e 24 h: o commit antigo pesa menos que na variante (a)
    assert median_lead_time_commits(lead_time_commits) == (24 + 120) / 2


def test_lead_time_repositorio_com_uma_unica_release():
    # a primeira release da história não tem anterior, então não gera commits
    assert median_lead_time_release([]) is None
    assert median_lead_time_commits([]) is None


def test_lead_time_ignora_commit_sem_data():
    commits = [
        {"release_id": 1, "release_published_at": "2026-03-15T00:00:00Z", "commit_author_date": None},
    ]
    assert median_lead_time_release(commits) is None
    assert median_lead_time_commits(commits) is None


def test_cfr_ignora_cancelled():
    runs = [
        {"conclusion": "success"},
        {"conclusion": "failure"},
        {"conclusion": "cancelled"},
    ]
    assert cfr_ci(runs) == 0.5


def test_cfr_sem_runs_validos():
    assert cfr_ci([{"conclusion": "cancelled"}]) is None


def test_cfr_ci_conta_timed_out_e_startup_failure_como_falha():
    runs = [
        {"conclusion": "success"},
        {"conclusion": "timed_out"},
        {"conclusion": "startup_failure"},
        {"conclusion": None},
    ]
    assert cfr_ci(runs) == pytest.approx(2 / 3)


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("v2.3.1", (2, 3, 1)),
        ("release-1.2", (1, 2, 0)),
        ("@scope/pkg@10.0.3", (10, 0, 3)),
        ("nightly", None),
    ],
)
def test_parse_version(tag, expected):
    assert parse_version(tag) == expected


@pytest.mark.parametrize(
    "previous,current,expected",
    [
        ("v2.3.0", "v2.3.1", True),
        ("v2.3", "v2.3.1", True),
        ("v2.3.1", "v2.4.0", False),
        ("v2.3.1", "v3.0.0", False),
        ("v2.3.1", "v2.3.1", False),
        ("nightly", "v2.3.1", False),
    ],
)
def test_is_patch_bump(previous, current, expected):
    assert is_patch_bump(previous, current) is expected


@pytest.mark.parametrize(
    "message,expected",
    [
        ("fix: crash ao abrir arquivo", True),
        ('Revert "feat: novo parser"', True),
        ("hotfix: token expirado", True),
        ("Fixes #123", True),
        ("Merge pull request #9 from user/bugfix-login", True),
        ("chore: prefix dos logs", False),
        ("test: nova fixture", False),
    ],
)
def test_release_corretiva_exige_commit_de_correcao(message, expected):
    assert is_corrective_release("v1.0.0", "v1.0.1", [message]) is expected


def test_release_corretiva_exige_mudanca_so_no_patch():
    assert not is_corrective_release("v1.0.0", "v1.1.0", ["fix: bug"])


def test_cfr_entrega_exemplo(cfr_releases, cfr_commits):
    # v2.3.0 falhou (v2.3.1 dois dias depois); v2.3.1, v2.4.0 e v2.5.0 não
    assert cfr_delivery(cfr_releases, cfr_commits, WINDOW_END) == (0.25, 0)


def test_cfr_entrega_censura_ultimos_7_dias(cfr_releases, cfr_commits):
    # janela termina 4 dias após a v2.4.0: ela é censurada e sai do denominador
    cfr, censored = cfr_delivery(cfr_releases[:3], cfr_commits, "2026-06-05T23:59:59Z")
    assert cfr == 0.5
    assert censored == 1


def test_cfr_entrega_ignora_correcao_apos_7_dias():
    releases = [
        {"release_id": 1, "tag_name": "v1.0.0", "published_at": "2026-01-01T00:00:00Z"},
        {"release_id": 2, "tag_name": "v1.0.1", "published_at": "2026-01-09T00:00:00Z"},
    ]
    commits = [{"release_id": 2, "commit_message": "fix: bug"}]
    assert cfr_delivery(releases, commits, WINDOW_END) == (0.0, 0)


def test_cfr_entrega_aceita_releases_fora_de_ordem(cfr_releases, cfr_commits):
    assert cfr_delivery(list(reversed(cfr_releases)), cfr_commits, WINDOW_END) == (0.25, 0)


def test_cfr_entrega_repositorio_com_uma_unica_release(cfr_releases):
    assert cfr_delivery(cfr_releases[:1], [], WINDOW_END) == (0.0, 0)


def test_cfr_entrega_tudo_censurado(cfr_releases):
    assert cfr_delivery(cfr_releases, [], "2026-06-21T00:00:00Z")[1] == 1
    assert cfr_delivery(cfr_releases[:1], [], "2026-05-11T00:00:00Z") == (None, 1)


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
    assert censored_recovery_ratio(runs) == 1.0


def test_recovery_ignora_cancelled_dentro_do_episodio(workflow_runs):
    cancelled = {
        "workflow_id": 10,
        "conclusion": "cancelled",
        "run_started_at": "2026-01-01T10:45:00Z",
        "updated_at": "2026-01-01T10:46:00Z",
    }
    values, censored = recovery_episodes(workflow_runs + [cancelled])
    assert values == pytest.approx([4 / 3])
    assert censored == 0


def test_recovery_separa_episodios_por_workflow(workflow_runs):
    # o workflow 20 falha no meio do episódio do workflow 10 e nunca se recupera
    other = {
        "workflow_id": 20,
        "conclusion": "failure",
        "run_started_at": "2026-01-01T10:10:00Z",
        "updated_at": "2026-01-01T10:12:00Z",
    }
    runs = workflow_runs + [other]
    values, censored = recovery_episodes(runs)
    assert values == pytest.approx([4 / 3])
    assert censored == 1
    assert censored_recovery_ratio(runs) == 0.5


def test_recovery_sem_falhas(workflow_runs):
    only_success = [r for r in workflow_runs if r["conclusion"] == "success"]
    assert median_recovery_hours(only_success) is None
    assert censored_recovery_ratio(only_success) is None


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
    [
        (0.10, "Elite"),
        (0.15, "Elite"),
        (0.20, "High"),
        (0.30, "High"),
        (0.40, "Medium"),
        (0.45, "Medium"),
        (0.50, "Low"),
    ],
)
def test_classify_cfr(value, expected):
    assert classify_cfr(value) == expected


@pytest.mark.parametrize(
    "hours,expected",
    [(0.5, "Elite"), (1, "High"), (2, "High"), (24, "Medium"), (48, "Medium"), (24 * 7, "Low"), (24 * 8, "Low")],
)
def test_classify_recovery(hours, expected):
    assert classify_recovery(hours) == expected


def test_overall_classification_rounds_median_down():
    assert overall_classification(["Elite", "High", "High", "Low"]) == "High"


@pytest.mark.parametrize(
    "categories,expected",
    [
        (["Elite", "Elite", "High", "Low"], "High"),  # mediana 3,5
        (["Elite", "High", "Medium", "Low"], "Medium"),  # mediana 2,5
        (["Low", "Low", "Low", "Low"], "Low"),
    ],
)
def test_overall_classification_arredonda_para_baixo(categories, expected):
    assert overall_classification(categories) == expected


def test_overall_requires_four_metrics():
    with pytest.raises(ValueError):
        overall_classification(["Elite"])
