from __future__ import annotations

import csv
from contextlib import ExitStack
from dataclasses import fields
from datetime import datetime
from pathlib import Path

import requests

from .github_api import GitHubAPI
from .models import RepositoryRecord
from .releases import collect_releases, commits_between_releases
from .selection import Funnel, has_actions
from .workflows import collect_workflow_runs


OUTPUTS = {
    "repositories": [f.name for f in fields(RepositoryRecord)],
    "releases": ["full_name", "release_id", "tag_name", "published_at"],
    "commits": [
        "full_name",
        "release_id",
        "release_tag",
        "release_published_at",
        "commit_sha",
        "commit_author_date",
        "commit_message",
    ],
    "ignored_releases": ["full_name", "release_id", "tag_name", "reason"],
    "workflow_runs": [
        "full_name",
        "id",
        "workflow_id",
        "name",
        "conclusion",
        "created_at",
        "run_started_at",
        "updated_at",
    ],
}


def _contributors(api: GitHubAPI, owner: str, name: str) -> int | None:
    try:
        return api.contributor_count(owner, name)
    except requests.HTTPError:
        # Repositórios enormes respondem 403 ("contributor list is too large").
        return None


def collect_repository(
    api: GitHubAPI,
    repo: dict,
    start: datetime,
    end: datetime,
    funnel: Funnel,
    min_releases: int = 5,
    min_runs: int = 50,
) -> dict[str, list[dict]] | None:
    """Coleta um candidato etapa por etapa do funil.

    Devolve as linhas de cada CSV de `OUTPUTS` ou `None` se o repositório for descartado
    (o motivo fica registrado no funil).
    """
    owner, name, full_name = repo["owner"]["login"], repo["name"], repo["full_name"]
    stage = "with_actions"

    try:
        if not has_actions(api, owner, name):
            funnel.discard(stage, "no_actions")
            return None
        funnel.reached(stage)

        stage = "with_min_releases"
        published, in_window = collect_releases(api, owner, name, start, end)
        if len(in_window) < min_releases:
            funnel.discard(stage, "few_releases")
            return None
        funnel.reached(stage)

        stage = "with_min_runs"
        runs = collect_workflow_runs(api, owner, name, repo["default_branch"], start, end)
        if len(runs) < min_runs:
            funnel.discard(stage, "few_runs")
            return None
        funnel.reached(stage)

        stage = "included"
        # A "release anterior" do lead time segue a definição principal (sem pré-releases)
        # e pode estar fora da janela.
        history = [r for r in published if not r.get("prerelease")]
        commits, ignored = commits_between_releases(api, owner, name, history, in_window)
        contributors = _contributors(api, owner, name)
    except (requests.RequestException, RuntimeError) as exc:
        funnel.discard(stage, "api_error")
        print(f"[erro] {full_name}: {exc}")
        return None
    funnel.reached(stage)

    record = RepositoryRecord(
        full_name=full_name,
        owner=owner,
        name=name,
        html_url=repo["html_url"],
        default_branch=repo["default_branch"],
        stars=repo["stargazers_count"],
        language=repo.get("language"),
        created_at=repo["created_at"],
        contributors=contributors,
        releases_valid=len(in_window),
        workflow_runs_valid=len(runs),
    )
    return {
        "repositories": [record.asdict()],
        "releases": [
            {
                "full_name": full_name,
                "release_id": r["id"],
                "tag_name": r["tag_name"],
                "published_at": r["published_at"],
            }
            for r in in_window
        ],
        "commits": [{"full_name": full_name, **c} for c in commits],
        "ignored_releases": [{"full_name": full_name, **i} for i in ignored],
        "workflow_runs": [{"full_name": full_name, **r} for r in runs],
    }


class SampleWriter:
    """Grava os CSVs da amostra repositório a repositório, sem acumular tudo em memória."""

    def __init__(self, out_dir: str | Path):
        self.out_dir = Path(out_dir)
        self._stack = ExitStack()
        self._writers: dict[str, csv.DictWriter] = {}

    def __enter__(self) -> SampleWriter:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        for name, columns in OUTPUTS.items():
            fp = self._stack.enter_context(
                (self.out_dir / f"{name}.csv").open("w", newline="", encoding="utf-8")
            )
            writer = csv.DictWriter(fp, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            self._writers[name] = writer
        return self

    def write(self, data: dict[str, list[dict]]) -> None:
        for name, rows in data.items():
            self._writers[name].writerows(rows)

    def __exit__(self, *exc_info) -> None:
        self._stack.close()
