"""Unidades de deploy alternativas da RQ 07: C2 (releases + pré-releases) e C3 (tags)."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import requests

from .collect import SampleWriter
from .github_api import GitHubAPI
from .releases import collect_releases, commits_between_releases, parse_dt, previous_releases


TAGS_QUERY = """
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    refs(refPrefix: "refs/tags/", first: 100, after: $after,
         orderBy: {field: TAG_COMMIT_DATE, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        target {
          ... on Commit { oid committedDate }
          ... on Tag { target { ... on Commit { oid committedDate } } }
        }
      }
    }
  }
}
"""

UNIT_FIELDS = ["full_name", "release_id", "tag_name", "published_at", "previous_tag", "prerelease"]
# Só o que a RQ 07 usa: a data de publicação vem de *_units; a mensagem só entra no CFR (b),
# que é o da C2. Com as 7 colunas de commits/, as variantes passavam de 270 MB.
VARIANT_OUTPUTS = {
    "c2_units": UNIT_FIELDS,
    "c2_commits": ["release_id", "commit_author_date", "commit_message"],
    "c3_units": UNIT_FIELDS,
    "c3_commits": ["release_id", "commit_author_date"],
    "errors": ["full_name", "error"],
}
VARIANT_PER_REPOSITORY = {"c2_commits", "c3_commits"}


def collect_tags_with_dates(api: GitHubAPI, owner: str, name: str) -> list[dict]:
    """Tags do repositório em ordem cronológica, datadas pelo commit apontado (enunciado, seção 4).

    Tags anotadas apontam para um objeto Tag; vale o commit de destino. Tags que apontam
    para outra coisa (árvore, blob) ficam de fora.
    """
    tags: list[dict] = []
    after = None
    while True:
        data = api.graphql(TAGS_QUERY, {"owner": owner, "name": name, "after": after})
        refs = data["repository"]["refs"]
        for node in refs["nodes"]:
            commit = node["target"] or {}
            commit = commit.get("target", commit) or {}
            if commit.get("committedDate"):
                tags.append(
                    {"id": node["name"], "tag_name": node["name"], "published_at": commit["committedDate"], "prerelease": False}
                )
        if not refs["pageInfo"]["hasNextPage"]:
            break
        after = refs["pageInfo"]["endCursor"]

    tags.sort(key=lambda t: (parse_dt(t["published_at"]), t["tag_name"]))
    return tags


def _variant(
    api: GitHubAPI,
    owner: str,
    name: str,
    full_name: str,
    history: list[dict],
    start: datetime,
    end: datetime,
) -> tuple[list[dict], list[dict]]:
    in_window = [r for r in history if start <= parse_dt(r["published_at"]) <= end]
    commits, _ = commits_between_releases(api, owner, name, history, in_window, ties_to_latest=True)
    previous = {r["id"]: p for r, p in zip(history, previous_releases(history, ties_to_latest=True))}
    units = [
        {
            "full_name": full_name,
            "release_id": r["id"],
            "tag_name": r["tag_name"],
            "published_at": r["published_at"],
            "previous_tag": previous[r["id"]]["tag_name"] if previous[r["id"]] else "",
            "prerelease": bool(r.get("prerelease")),
        }
        for r in in_window
    ]
    return units, [{"full_name": full_name, **c} for c in commits]


def collect_variants(api: GitHubAPI, repo: dict, start: datetime, end: datetime) -> dict[str, list[dict]]:
    owner, name, full_name = repo["owner"], repo["name"], repo["full_name"]
    published, _ = collect_releases(api, owner, name, start, end)  # inclui pré-releases
    c2_units, c2_commits = _variant(api, owner, name, full_name, published, start, end)
    tags = collect_tags_with_dates(api, owner, name)
    c3_units, c3_commits = _variant(api, owner, name, full_name, tags, start, end)
    return {"c2_units": c2_units, "c2_commits": c2_commits, "c3_units": c3_units, "c3_commits": c3_commits}


def collect_all_variants(api: GitHubAPI, out_dir: Path, start: datetime, end: datetime) -> int:
    """Coleta C2 e C3 para cada repositório de `repositories.csv`; grava em `out_dir/variantes/`."""
    with (out_dir / "repositories.csv").open(newline="", encoding="utf-8") as fp:
        repositories = list(csv.DictReader(fp))

    failures = 0
    with SampleWriter(out_dir / "variantes", VARIANT_OUTPUTS, VARIANT_PER_REPOSITORY) as writer:
        for position, repo in enumerate(repositories, start=1):
            try:
                data = collect_variants(api, repo, start, end)
            except (requests.RequestException, RuntimeError) as exc:
                failures += 1
                writer.write({"errors": [{"full_name": repo["full_name"], "error": f"{type(exc).__name__}: {exc}"[:300]}]}, repo["full_name"])
                print(f"[erro] {repo['full_name']}: {exc}")
                continue
            writer.write(data, repo["full_name"])
            print(f"[variantes {position}/{len(repositories)}] {repo['full_name']}: {len(data['c2_units'])} releases+pré, {len(data['c3_units'])} tags")
    return failures
