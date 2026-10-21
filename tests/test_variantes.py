import csv
import gzip
import sys
from datetime import datetime, timezone

import requests

import pipeline.__main__ as entrypoint
from pipeline.github_api import GitHubAPI
from pipeline.releases import previous_releases
from pipeline.variantes import collect_tags_with_dates, collect_variants

START = datetime(2025, 10, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
BASE = "/repos/octo/app"
REPO = {"full_name": "octo/app", "owner": "octo", "name": "app"}


class FakeAPI(GitHubAPI):
    """REST por rota e GraphQL por cursor, sem rede."""

    def __init__(self, routes, tag_pages):
        self.routes = routes
        self.tag_pages = tag_pages  # cursor -> (nós, próximo cursor)
        self.graphql_calls = []

    def get_json(self, path, params=None, *, slim=None, **_):
        if path not in self.routes:
            raise requests.HTTPError(f"404 {path}")
        payload = self.routes[path]
        if isinstance(payload, list) and params and "page" in params:
            per_page = params.get("per_page", 30)
            payload = payload[(params["page"] - 1) * per_page : params["page"] * per_page]
        elif isinstance(payload, dict) and "commits" in payload and params and params.get("page", 1) > 1:
            payload = {**payload, "commits": []}
        return (slim(payload) if slim else payload), {}

    def graphql(self, query, variables, **_):
        self.graphql_calls.append(variables)
        if self.tag_pages is None:
            raise RuntimeError("GraphQL: Could not resolve to a Repository")
        nodes, cursor = self.tag_pages[variables["after"]]
        return {"repository": {"refs": {"nodes": nodes, "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor}}}}


def release(release_id, tag, published_at, prerelease=False):
    return {"id": release_id, "tag_name": tag, "published_at": published_at, "prerelease": prerelease, "draft": False}


def commit_node(name, date):
    return {"name": name, "target": {"oid": "x", "committedDate": date}}


def compare(*messages):
    commits = [{"sha": f"s{i}", "commit": {"author": {"date": "2025-10-01T00:00:00Z"}, "message": m}} for i, m in enumerate(messages)]
    return {"total_commits": len(commits), "commits": commits}


def test_versoes_iguais_usam_a_mais_recente_como_anterior():
    history = [
        release(1, "v1.9.0", "2025-09-01T00:00:00Z"),
        release(2, "v2.0.0-rc1", "2025-10-01T00:00:00Z", prerelease=True),
        release(3, "v2.0.0-rc2", "2025-10-05T00:00:00Z", prerelease=True),
        release(4, "v1.9.1", "2025-10-06T00:00:00Z"),
        release(5, "v2.0.0", "2025-10-10T00:00:00Z"),
    ]
    tags = lambda result: [p["tag_name"] if p else None for p in result]
    # a final é comparada com a rc2: os commits já entregues nas pré-releases não contam de novo
    assert tags(previous_releases(history, ties_to_latest=True)) == [None, "v1.9.0", "v2.0.0-rc1", "v1.9.0", "v2.0.0-rc2"]
    # na definição principal (C1) nada muda: versões iguais não contam como anteriores
    assert tags(previous_releases(history)) == [None, "v1.9.0", "v1.9.0", "v1.9.0", "v1.9.1"]


def test_tags_datadas_pelo_commit_e_paginadas():
    pages = {
        None: (
            [
                commit_node("v1.1.0", "2025-11-01T00:00:00Z"),
                {"name": "v1.0.0", "target": {"target": {"oid": "y", "committedDate": "2025-10-01T00:00:00Z"}}},  # anotada
                {"name": "docs-tree", "target": {}},  # aponta para uma árvore: fica de fora
            ],
            "c1",
        ),
        "c1": ([commit_node("v0.9.0", "2025-06-01T00:00:00Z")], None),
    }
    api = FakeAPI({}, pages)
    tags = collect_tags_with_dates(api, "octo", "app")
    assert [(t["tag_name"], t["published_at"]) for t in tags] == [
        ("v0.9.0", "2025-06-01T00:00:00Z"),
        ("v1.0.0", "2025-10-01T00:00:00Z"),
        ("v1.1.0", "2025-11-01T00:00:00Z"),
    ]
    assert [c["after"] for c in api.graphql_calls] == [None, "c1"]


def variant_api(tag_pages):
    releases = [
        release(3, "v2.0.0", "2025-10-20T00:00:00Z"),
        release(2, "v2.0.0-rc1", "2025-10-10T00:00:00Z", prerelease=True),
        release(1, "v1.9.0", "2025-09-01T00:00:00Z"),
    ]
    routes = {
        f"{BASE}/releases": releases,
        f"{BASE}/compare/v1.9.0...v2.0.0-rc1": compare("feat: a", "feat: b"),
        f"{BASE}/compare/v2.0.0-rc1...v2.0.0": compare("fix: c"),
        f"{BASE}/compare/v1.9.0...v2.0.0": compare("feat: a", "feat: b", "fix: c"),
    }
    return FakeAPI(routes, tag_pages)


TAG_PAGES = {
    None: (
        [
            commit_node("v2.0.0", "2025-10-19T00:00:00Z"),
            commit_node("v2.0.0-rc1", "2025-10-09T00:00:00Z"),
            commit_node("v1.9.0", "2025-08-31T00:00:00Z"),
        ],
        None,
    )
}


def test_collect_variants_c2_inclui_pre_releases_e_c3_usa_tags():
    data = collect_variants(variant_api(TAG_PAGES), REPO, START, END)

    assert [(u["tag_name"], u["previous_tag"], u["prerelease"]) for u in data["c2_units"]] == [
        ("v2.0.0-rc1", "v1.9.0", True),
        ("v2.0.0", "v2.0.0-rc1", False),
    ]
    assert [(c["release_tag"], c["commit_message"]) for c in data["c2_commits"]] == [
        ("v2.0.0-rc1", "feat: a"),
        ("v2.0.0-rc1", "feat: b"),
        ("v2.0.0", "fix: c"),
    ]
    # C3: tags datadas pelo commit; mesma regra de anterior
    assert [(u["tag_name"], u["published_at"], u["previous_tag"]) for u in data["c3_units"]] == [
        ("v2.0.0-rc1", "2025-10-09T00:00:00Z", "v1.9.0"),
        ("v2.0.0", "2025-10-19T00:00:00Z", "v2.0.0-rc1"),
    ]
    assert len(data["c3_commits"]) == 3


def read(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as fp:
        return list(csv.DictReader(fp))


def test_comando_variants_grava_por_repositorio_e_registra_erros(tmp_path, monkeypatch):
    out = tmp_path / "processed"
    out.mkdir()
    with (out / "repositories.csv").open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["full_name", "owner", "name"])
        writer.writeheader()
        writer.writerows([REPO, {"full_name": "octo/gone", "owner": "octo", "name": "gone"}])

    api = variant_api(TAG_PAGES)
    original = api.graphql

    def graphql(query, variables, **kw):
        if variables["name"] == "gone":
            raise RuntimeError("GraphQL: Could not resolve to a Repository")
        return original(query, variables, **kw)

    api.graphql = graphql
    api.routes["/repos/octo/gone/releases"] = []
    monkeypatch.setattr(entrypoint, "GitHubAPI", lambda cache_dir: api)
    config = tmp_path / "config.yaml"
    config.write_text(
        "window: {start: '2025-10-01', end: '2026-09-30'}\n"
        f"sample_size: 2\nmin_releases: 1\nmin_runs: 1\ncache_dir: x\noutput_dir: {out.as_posix()}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["python -m pipeline", "--config", str(config), "--variants"])
    entrypoint.main()

    variantes = out / "variantes"
    assert [u["tag_name"] for u in read(variantes / "c2_units.csv")] == ["v2.0.0-rc1", "v2.0.0"]
    assert len(read(variantes / "c3_commits" / "octo__app.csv.gz")) == 3
    assert [e["full_name"] for e in read(variantes / "errors.csv")] == ["octo/gone"]
    assert not (variantes / "c2_commits" / "octo__gone.csv.gz").exists()
