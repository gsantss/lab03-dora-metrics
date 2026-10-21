from __future__ import annotations

import csv
import gzip
from datetime import datetime
from itertools import groupby
from operator import itemgetter
from pathlib import Path
from statistics import median

from metricas import (
    cfr_ci,
    cfr_delivery,
    classify_cfr,
    classify_deployment_frequency,
    classify_lead_time,
    classify_recovery,
    deployment_frequency,
    median_lead_time_commits,
    median_lead_time_release,
    overall_classification,
    recovery_episodes,
)

from .collect import repository_file
from .selection import write_csv


# Classificação de referência C1 (RQ 07): deploy = release, lead time (a) e CFR (a).
METRIC_FIELDS = [
    "full_name",
    "releases",
    "deployment_frequency",
    "lead_time_release_h",
    "lead_time_commit_h",
    "lead_time_releases",
    "lead_time_ignored",
    "workflow_runs",
    "cfr_ci",
    "cfr_delivery",
    "cfr_delivery_evaluated",
    "cfr_delivery_censored",
    "recovery_h",
    "recovery_episodes",
    "recovery_censored",
    "recovery_censored_ratio",
    "class_deployment_frequency",
    "class_lead_time",
    "class_cfr",
    "class_recovery",
    "class_overall",
]


def grouped_by_repository(path: Path) -> dict[str, list[dict]]:
    with path.open(newline="", encoding="utf-8") as fp:
        return {name: list(rows) for name, rows in groupby(csv.DictReader(fp), key=itemgetter("full_name"))}


def repository_rows(directory: Path, full_name: str) -> list[dict]:
    # Commits e runs ficam num .csv.gz por repositório; sem arquivo, o repositório não tem linhas.
    path = repository_file(directory, full_name)
    if not path.exists():
        return []
    with gzip.open(path, "rt", newline="", encoding="utf-8") as fp:
        return list(csv.DictReader(fp))


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def repository_metrics(
    full_name: str,
    releases: list[dict],
    commits: list[dict],
    ignored: list[dict],
    runs: list[dict],
    start: datetime,
    end: datetime,
) -> dict:
    frequency = deployment_frequency(len(releases), start, end)
    lead_time = median_lead_time_release(commits)
    failure_rate = cfr_ci(runs)
    delivery, delivery_censored = cfr_delivery(releases, commits, end)
    durations, recovery_censored = recovery_episodes(runs)
    recovery = median(durations) if durations else None
    episodes = len(durations) + recovery_censored

    classes = {
        "class_deployment_frequency": classify_deployment_frequency(frequency),
        "class_lead_time": classify_lead_time(lead_time) if lead_time is not None else None,
        "class_cfr": classify_cfr(failure_rate) if failure_rate is not None else None,
        "class_recovery": classify_recovery(recovery) if recovery is not None else None,
    }
    overall = overall_classification(classes.values()) if all(classes.values()) else None

    return {
        "full_name": full_name,
        "releases": len(releases),
        "deployment_frequency": _round(frequency),
        "lead_time_release_h": _round(lead_time),
        "lead_time_commit_h": _round(median_lead_time_commits(commits)),
        "lead_time_releases": len({c["release_id"] for c in commits if c["commit_author_date"]}),
        "lead_time_ignored": len(ignored),
        "workflow_runs": len(runs),
        "cfr_ci": _round(failure_rate),
        "cfr_delivery": _round(delivery),
        "cfr_delivery_evaluated": len(releases) - delivery_censored,
        "cfr_delivery_censored": delivery_censored,
        "recovery_h": _round(recovery),
        "recovery_episodes": episodes,
        "recovery_censored": recovery_censored,
        "recovery_censored_ratio": _round(recovery_censored / episodes) if episodes else None,
        **classes,
        "class_overall": overall,
    }


def build_metrics(out_dir: str | Path, start: datetime, end: datetime) -> int:
    """Gera `metrics.csv` (uma linha por repositório) a partir dos CSVs da coleta."""
    out_dir = Path(out_dir)
    for directory in ("commits", "workflow_runs"):
        if not (out_dir / directory).is_dir():
            # Coletas antigas gravavam um commits.csv.gz único: sem a pasta, as métricas sairiam vazias.
            raise FileNotFoundError(f"{out_dir / directory} não existe; rode a coleta com esta versão do pipeline.")
    with (out_dir / "repositories.csv").open(newline="", encoding="utf-8") as fp:
        names = [row["full_name"] for row in csv.DictReader(fp)]
    releases = grouped_by_repository(out_dir / "releases.csv")
    ignored = grouped_by_repository(out_dir / "ignored_releases.csv")

    rows = [
        repository_metrics(
            name,
            releases.get(name, []),
            repository_rows(out_dir / "commits", name),
            ignored.get(name, []),
            repository_rows(out_dir / "workflow_runs", name),
            start,
            end,
        )
        for name in names
    ]
    write_csv(out_dir / "metrics.csv", rows)
    return len(rows)
