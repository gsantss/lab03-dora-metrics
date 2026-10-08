import csv
import sys
from datetime import date, datetime, timedelta, timezone

import pytest
import requests

import pipeline.__main__ as entrypoint
from metricas import cfr_delivery, median_lead_time_release
from pipeline import workflows
from pipeline.collect import collect_repository
from pipeline.github_api import GitHubAPI
from pipeline.releases import commits_between_releases, compare_commits
from pipeline.selection import STAGES, Funnel
from pipeline.workflows import month_windows, runs_in_range

START = datetime(2025, 10, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
BASE = "/repos/octo/app"


class FakeAPI(GitHubAPI):
    """Serve respostas montadas à mão e reaproveita a paginação real do cliente."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get_json(self, path, params=None, *, slim=None, **_):
        params = dict(params or {})
        self.calls.append((path, params))
        if path not in self.routes:
            raise requests.HTTPError(f"404 {path}")
        route = self.routes[path]
        payload = _page(route(params) if callable(route) else route, params)
        return (slim(payload) if slim else payload), {}


def _page(payload, params):
    if "page" not in params:
        return payload
    per_page = params.get("per_page", 30)
    lo, hi = (params["page"] - 1) * per_page, params["page"] * per_page
    if isinstance(payload, list):
        return payload[lo:hi]
    for key in ("items", "workflow_runs", "commits"):
        if key in payload:
            return {**payload, key: payload[key][lo:hi]}
    return payload


def runs_route(runs):
    def route(params):
        first, last = params["created"].split("..")
        selected = [r for r in runs if first <= r["created_at"][:10] <= last]
        return {"total_count": len(selected), "workflow_runs": selected}

    return route


def make_run(run_id, day, conclusion="success"):
    return {
        "id": run_id,
        "workflow_id": 1,
        "name": "CI",
        "conclusion": conclusion,
        "event": "push",
        "head_branch": "main",
        "created_at": f"{day}T10:00:00Z",
        "run_started_at": f"{day}T10:00:00Z",
        "updated_at": f"{day}T10:05:00Z",
        "html_url": f"https://github.com/octo/app/actions/runs/{run_id}",
    }


def make_release(release_id, tag, published_at, prerelease=False, draft=False):
    return {
        "id": release_id,
        "tag_name": tag,
        "published_at": published_at,
        "prerelease": prerelease,
        "draft": draft,
    }


def make_commit(sha, day, message):
    return {"sha": sha, "commit": {"author": {"date": f"{day}T08:00:00Z"}, "message": message}}


def compare(commits):
    return {"total_commits": len(commits), "commits": commits}


REPO = {
    "full_name": "octo/app",
    "name": "app",
    "owner": {"login": "octo"},
    "html_url": "https://github.com/octo/app",
    "default_branch": "main",
    "stargazers_count": 1500,
    "language": "Python",
    "created_at": "2015-01-01T00:00:00Z",
}

RELEASES = [
    make_release(7, "v2.0.0", "2026-10-15T00:00:00Z"),  # depois da janela
    make_release(6, "v1.2.0", None, draft=True),
    make_release(5, "v1.1.0", "2025-11-01T00:00:00Z"),
    make_release(4, "v1.0.1", "2025-10-12T00:00:00Z"),
    make_release(3, "v1.0.0", "2025-10-10T00:00:00Z"),
    make_release(2, "v1.0.0-rc1", "2025-10-05T00:00:00Z", prerelease=True),
    make_release(1, "v0.9.0", "2025-06-01T00:00:00Z"),  # antes da janela
]

RUNS = [
    make_run(101, "2025-10-02"),
    make_run(102, "2025-10-03", "failure"),
    make_run(103, "2025-10-04", "cancelled"),
    make_run(104, "2025-10-05", None),
    make_run(105, "2025-11-02"),
    make_run(106, "2025-12-02", "timed_out"),
]


def eligible_routes():
    return {
        f"{BASE}/actions/workflows": {"total_count": 2},
        f"{BASE}/releases": RELEASES,
        f"{BASE}/actions/runs": runs_route(RUNS),
        f"{BASE}/contributors": [{"login": "a"}, {"login": "b"}],
        f"{BASE}/compare/v0.9.0...v1.0.0": compare(
            [make_commit("a1", "2025-09-20", "feat: api"), make_commit("a2", "2025-10-08", "docs: guia")]
        ),
        f"{BASE}/compare/v1.0.0...v1.0.1": compare(
            [make_commit("b1", "2025-10-11", "fix: crash ao iniciar\n\ncorpo longo do commit")]
        ),
        f"{BASE}/compare/v1.0.1...v1.1.0": compare([]),
    }


def collect(routes, **limits):
    funnel = Funnel()
    limits = {"min_releases": 3, "min_runs": 4, **limits}
    data = collect_repository(FakeAPI(routes), REPO, START, END, funnel, **limits)
    return data, funnel


def test_month_windows_cobre_a_janela_sem_sobreposicao():
    chunks = list(month_windows(START, END))
    assert len(chunks) == 12
    assert chunks[0][0] == START
    assert chunks[-1][1] == END
    for (_, previous_end), (next_start, _) in zip(chunks, chunks[1:]):
        assert next_start - previous_end == timedelta(seconds=1)


def test_runs_in_range_subdivide_quando_atinge_o_teto(monkeypatch):
    monkeypatch.setattr(workflows, "RUNS_CAP", 3)
    runs = [make_run(i, f"2025-10-{i:02d}") for i in range(1, 8)]
    api = FakeAPI({f"{BASE}/actions/runs": runs_route(runs)})
    collected = runs_in_range(api, f"{BASE}/actions/runs", "main", date(2025, 10, 1), date(2025, 10, 31))
    assert sorted(r["id"] for r in collected) == list(range(1, 8))


def test_runs_in_range_falha_se_um_dia_atinge_o_teto(monkeypatch):
    monkeypatch.setattr(workflows, "RUNS_CAP", 2)
    runs = [make_run(1, "2025-10-01"), make_run(2, "2025-10-01")]
    api = FakeAPI({f"{BASE}/actions/runs": runs_route(runs)})
    with pytest.raises(RuntimeError):
        runs_in_range(api, f"{BASE}/actions/runs", "main", date(2025, 10, 1), date(2025, 10, 1))


def test_compare_commits_pagina_alem_de_100():
    commits = [make_commit(f"c{i}", "2025-10-01", "feat: x") for i in range(150)]
    api = FakeAPI({f"{BASE}/compare/a...b": compare(commits)})
    assert len(compare_commits(api, f"{BASE}/compare/a...b")) == 150
    assert [p["page"] for _, p in api.calls] == [1, 2]


def test_commits_between_releases_registra_releases_ignoradas():
    first = make_release(1, "v1.0.0", "2025-10-01T00:00:00Z")
    second = make_release(2, "v1.1.0", "2025-11-01T00:00:00Z")
    records, ignored = commits_between_releases(FakeAPI({}), "octo", "app", [first, second], [first, second])
    assert records == []
    assert [(i["tag_name"], i["reason"]) for i in ignored] == [
        ("v1.0.0", "no_previous_release"),
        ("v1.1.0", "compare_error:HTTPError"),
    ]


def test_collect_repository_elegivel():
    routes = eligible_routes()
    api = FakeAPI(routes)
    funnel = Funnel()
    data = collect_repository(api, REPO, START, END, funnel, min_releases=3, min_runs=4)

    repo = data["repositories"][0]
    assert repo["full_name"] == "octo/app"
    assert repo["contributors"] == 2
    assert repo["releases_valid"] == 3  # sem draft, pré-release e fora da janela
    assert repo["workflow_runs_valid"] == 4  # sem cancelled e em andamento

    assert [r["tag_name"] for r in data["releases"]] == ["v1.0.0", "v1.0.1", "v1.1.0"]
    assert [c["commit_sha"] for c in data["commits"]] == ["a1", "a2", "b1"]
    assert data["commits"][2]["commit_message"] == "fix: crash ao iniciar"
    assert [(i["tag_name"], i["reason"]) for i in data["ignored_releases"]] == [("v1.1.0", "no_new_commits")]
    assert {r["conclusion"] for r in data["workflow_runs"]} == {"success", "failure", "timed_out"}

    # a release anterior à v1.0.0 é a v0.9.0: a pré-release v1.0.0-rc1 não entra na definição principal
    assert any(path.endswith("/compare/v0.9.0...v1.0.0") for path, _ in api.calls)
    assert all(funnel.counts[stage] == 1 for stage in STAGES[1:])


def test_dados_coletados_alimentam_as_metricas():
    data, _ = collect(eligible_routes())
    # v1.0.0: 20 dias desde o commit mais antigo; v1.0.1: 16 h
    assert median_lead_time_release(data["commits"]) == (20 * 24 - 8 + 16) / 2
    # v1.0.0 é seguida em 2 dias pela v1.0.1 (só patch, com "fix:")
    assert cfr_delivery(data["releases"], data["commits"], END) == (pytest.approx(1 / 3), 0)


def test_contribuidores_indisponiveis_nao_descartam_o_repositorio():
    routes = eligible_routes()
    del routes[f"{BASE}/contributors"]
    data, funnel = collect(routes)
    assert data["repositories"][0]["contributors"] is None
    assert funnel.counts["included"] == 1


@pytest.mark.parametrize(
    "change,limits,stage,reason",
    [
        ({f"{BASE}/actions/workflows": {"total_count": 0}}, {}, "with_actions", "no_actions"),
        ({}, {"min_releases": 4}, "with_min_releases", "few_releases"),
        ({}, {"min_runs": 5}, "with_min_runs", "few_runs"),
        ({f"{BASE}/releases": None}, {}, "with_min_releases", "api_error"),
    ],
)
def test_collect_repository_descartes(change, limits, stage, reason):
    routes = eligible_routes()
    for path, payload in change.items():
        if payload is None:
            del routes[path]
        else:
            routes[path] = payload
    data, funnel = collect(routes, **limits)
    assert data is None
    assert funnel.discards[stage] == {reason: 1}
    assert funnel.counts["included"] == 0


def test_funil_registra_motivos_de_descarte():
    funnel = Funnel()
    for _ in range(3):
        funnel.reached("candidates")
    funnel.discard("with_actions", "no_actions")
    funnel.reached("with_actions")
    funnel.reached("with_actions")
    funnel.discard("with_min_releases", "few_releases")
    funnel.discard("with_min_releases", "api_error")

    rows = {row["stage"]: row for row in funnel.to_rows()}
    assert list(rows) == list(STAGES)
    assert rows["with_actions"] == {"stage": "with_actions", "count": 2, "discarded": 1, "reasons": "no_actions=1"}
    assert rows["with_min_releases"]["reasons"] == "api_error=1; few_releases=1"
    assert rows["included"]["discarded"] == 0


def read_csv(path):
    with path.open(encoding="utf-8") as fp:
        return list(csv.DictReader(fp))


def test_pipeline_com_um_unico_comando(tmp_path, monkeypatch):
    without_actions = {**REPO, "full_name": "octo/lib", "name": "lib", "html_url": "https://github.com/octo/lib"}
    never_reached = {**REPO, "full_name": "octo/extra", "name": "extra"}
    routes = eligible_routes()
    routes["/repos/octo/lib/actions/workflows"] = {"total_count": 0}
    routes["/search/repositories"] = {"items": [without_actions, REPO, never_reached]}
    monkeypatch.setattr(entrypoint, "GitHubAPI", lambda cache_dir: FakeAPI(routes))

    out = tmp_path / "processed"
    config = tmp_path / "config.yaml"
    config.write_text(
        "window: {start: '2025-10-01', end: '2026-09-30'}\n"
        "sample_size: 1\nmin_releases: 3\nmin_runs: 4\n"
        f"cache_dir: {(tmp_path / 'cache').as_posix()}\noutput_dir: {out.as_posix()}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["python -m pipeline", "--config", str(config)])
    entrypoint.main()

    funnel = {row["stage"]: row for row in read_csv(out / "funnel.csv")}
    assert funnel["candidates"]["count"] == "2"  # octo/extra não chega a ser avaliado
    assert funnel["with_actions"]["reasons"] == "no_actions=1"
    assert funnel["included"]["count"] == "1"

    assert [r["full_name"] for r in read_csv(out / "repositories.csv")] == ["octo/app"]
    assert len(read_csv(out / "releases.csv")) == 3
    assert len(read_csv(out / "commits.csv")) == 3
    assert len(read_csv(out / "ignored_releases.csv")) == 1
    assert len(read_csv(out / "workflow_runs.csv")) == 4
