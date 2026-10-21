from __future__ import annotations

import csv
import gzip
import io
from contextlib import ExitStack
from dataclasses import fields
from datetime import datetime
from pathlib import Path

import requests

from .github_api import GitHubAPI
from .models import RepositoryRecord
from .releases import collect_releases, commits_between_releases, previous_releases
from .selection import Funnel, has_actions
from .workflows import collect_workflow_runs


OUTPUTS = {
    "repositories": [f.name for f in fields(RepositoryRecord)],
    "releases": ["full_name", "release_id", "tag_name", "published_at", "previous_tag"],
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
# Um .csv.gz por repositório em data/processed/<nome>/: num arquivo só, passam do limite de
# 100 MB por arquivo do GitHub. pandas: pd.concat(map(pd.read_csv, glob(".../commits/*.csv.gz")))
PER_REPOSITORY = {"commits", "workflow_runs"}


def repository_file(directory: Path, full_name: str) -> Path:
    return directory / (full_name.replace("/", "__") + ".csv.gz")


def _write_gzip_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    # mtime=0: a mesma coleta gera os mesmos bytes, e o git não vê mudança à toa.
    with path.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        with io.TextIOWrapper(gz, encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


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
        # A "release anterior" do lead time segue a definição principal (sem pré-releases),
        # é da mesma linha de versão e pode estar fora da janela.
        history = [r for r in published if not r.get("prerelease")]
        previous_tag = {
            r["id"]: (p["tag_name"] if p else "") for r, p in zip(history, previous_releases(history))
        }
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
                "previous_tag": previous_tag[r["id"]],
            }
            for r in in_window
        ],
        "commits": [{"full_name": full_name, **c} for c in commits],
        "ignored_releases": [{"full_name": full_name, **i} for i in ignored],
        "workflow_runs": [{"full_name": full_name, **r} for r in runs],
    }


class SampleWriter:
    """Grava os CSVs da amostra repositório a repositório, sem acumular tudo em memória."""

    def __init__(
        self,
        out_dir: str | Path,
        outputs: dict[str, list[str]] = OUTPUTS,
        per_repository: set[str] = PER_REPOSITORY,
    ):
        self.out_dir = Path(out_dir)
        self.outputs = outputs
        self.per_repository = per_repository
        self._stack = ExitStack()
        self._writers: dict[str, csv.DictWriter] = {}

    def __enter__(self) -> SampleWriter:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        for name, columns in self.outputs.items():
            if name in self.per_repository:
                directory = self.out_dir / name
                directory.mkdir(exist_ok=True)
                for stale in directory.glob("*.csv.gz"):  # repositórios de uma execução anterior
                    stale.unlink()
                continue
            fp = self._stack.enter_context(
                (self.out_dir / f"{name}.csv").open("w", newline="", encoding="utf-8")
            )
            writer = csv.DictWriter(fp, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            self._writers[name] = writer
        return self

    def write(self, data: dict[str, list[dict]], full_name: str | None = None) -> None:
        full_name = full_name or data["repositories"][0]["full_name"]
        for name, rows in data.items():
            if name not in self.per_repository:
                self._writers[name].writerows(rows)
            elif rows:
                _write_gzip_csv(repository_file(self.out_dir / name, full_name), self.outputs[name], rows)

    def __exit__(self, *exc_info) -> None:
        self._stack.close()
