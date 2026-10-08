from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from math import floor
from statistics import median
from typing import Iterable


FAILURES = {"failure", "timed_out", "startup_failure"}
SUCCESSES = {"success"}
IGNORED = {"cancelled", "skipped", "neutral", "action_required", "stale", None, ""}

WEEK_HOURS = 24 * 7
VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
FIX_MESSAGE = re.compile(r"\b(revert|hotfix|bugfix|fix(e[sd])?)\b", re.IGNORECASE)


def _dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def deployment_frequency(release_count: int, start: str | datetime, end: str | datetime) -> float:
    weeks = (_dt(end) - _dt(start)).total_seconds() / 3600 / WEEK_HOURS
    if weeks <= 0:
        raise ValueError("A janela de observação precisa ter duração positiva.")
    return release_count / weeks


def lead_time_release(release_date: str, commit_dates: Iterable[str]) -> float | None:
    commits = [_dt(x) for x in commit_dates if x]
    if not commits:
        return None
    hours = (_dt(release_date) - min(commits)).total_seconds() / 3600
    return max(hours, 0.0)


def lead_times_commits(release_date: str, commit_dates: Iterable[str]) -> list[float]:
    release = _dt(release_date)
    values = []
    for value in commit_dates:
        if value:
            values.append(max((release - _dt(value)).total_seconds() / 3600, 0.0))
    return values


def _commits_by_release(commits: Iterable[dict]) -> dict[object, tuple[str, list[str]]]:
    grouped: dict[object, tuple[str, list[str]]] = {}
    for commit in commits:
        _, dates = grouped.setdefault(commit["release_id"], (commit["release_published_at"], []))
        dates.append(commit["commit_author_date"])
    return grouped


def median_lead_time_release(commits: Iterable[dict]) -> float | None:
    """Lead time (a): mediana, entre as releases, de `release - commit mais antigo`."""
    values = [lead_time_release(published, dates) for published, dates in _commits_by_release(commits).values()]
    values = [v for v in values if v is not None]
    return median(values) if values else None


def median_lead_time_commits(commits: Iterable[dict]) -> float | None:
    """Lead time (b): mediana de todos os commits de todas as releases."""
    values = [
        value
        for published, dates in _commits_by_release(commits).values()
        for value in lead_times_commits(published, dates)
    ]
    return median(values) if values else None


def cfr_ci(runs: Iterable[dict]) -> float | None:
    success = 0
    failure = 0

    for run in runs:
        conclusion = run.get("conclusion")
        if conclusion in SUCCESSES:
            success += 1
        elif conclusion in FAILURES:
            failure += 1

    total = success + failure
    return failure / total if total else None


def parse_version(tag: str) -> tuple[int, int, int] | None:
    match = VERSION.search(tag or "")
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def is_patch_bump(previous_tag: str, tag: str) -> bool:
    previous, current = parse_version(previous_tag), parse_version(tag)
    if previous is None or current is None:
        return False
    return previous[:2] == current[:2] and current[2] > previous[2]


def is_corrective_release(previous_tag: str, tag: str, commit_messages: Iterable[str]) -> bool:
    """Heurística v1 (a validar na amostra-ouro da S02): a versão muda só no patch
    E há ao menos um commit de revert/hotfix/fix entre as duas releases."""
    has_fix = any(FIX_MESSAGE.search(message or "") for message in commit_messages)
    return has_fix and is_patch_bump(previous_tag, tag)


def cfr_delivery(
    releases: Iterable[dict],
    commits: Iterable[dict],
    window_end: str | datetime,
    max_days: int = 7,
) -> tuple[float | None, int]:
    """CFR (b): fração das releases seguidas, em até `max_days`, por uma release corretiva.

    `releases` são as linhas de `releases.csv` (`release_id`, `tag_name`, `published_at`)
    e `commits` as de `commits.csv` (`release_id`, `commit_message`). Releases dos
    últimos `max_days` dias da janela são censuradas: ficam fora do denominador e são
    devolvidas na contagem de censuradas.
    """
    messages: dict[object, list[str]] = defaultdict(list)
    for commit in commits:
        messages[commit["release_id"]].append(commit.get("commit_message") or "")

    ordered = sorted(releases, key=lambda r: _dt(r["published_at"]))
    limit = _dt(window_end) - timedelta(days=max_days)
    evaluated = failed = censored = 0

    for current, following in zip(ordered, ordered[1:] + [None]):
        published = _dt(current["published_at"])
        if published > limit:
            censored += 1
            continue

        evaluated += 1
        if (
            following is not None
            and _dt(following["published_at"]) - published <= timedelta(days=max_days)
            and is_corrective_release(current["tag_name"], following["tag_name"], messages[following["release_id"]])
        ):
            failed += 1

    return (failed / evaluated if evaluated else None), censored


def recovery_episodes(runs: Iterable[dict]) -> tuple[list[float], int]:
    by_workflow: dict[object, list[dict]] = defaultdict(list)
    for run in runs:
        conclusion = run.get("conclusion")
        if conclusion in SUCCESSES | FAILURES:
            by_workflow[run.get("workflow_id")].append(run)

    durations: list[float] = []
    censored = 0

    for workflow_runs in by_workflow.values():
        workflow_runs.sort(key=lambda r: _dt(r["run_started_at"]))
        in_failure = False
        failure_start = None
        previous_was_success = True

        for run in workflow_runs:
            conclusion = run["conclusion"]

            if conclusion in FAILURES:
                if not in_failure and previous_was_success:
                    in_failure = True
                    failure_start = _dt(run["run_started_at"])
                previous_was_success = False
                continue

            if conclusion in SUCCESSES:
                if in_failure and failure_start is not None:
                    end = _dt(run["updated_at"])
                    durations.append(max((end - failure_start).total_seconds() / 3600, 0.0))
                    in_failure = False
                    failure_start = None
                previous_was_success = True

        if in_failure:
            censored += 1

    return durations, censored


def median_recovery_hours(runs: Iterable[dict]) -> float | None:
    durations, _ = recovery_episodes(runs)
    return median(durations) if durations else None


def censored_recovery_ratio(runs: Iterable[dict]) -> float | None:
    durations, censored = recovery_episodes(runs)
    total = len(durations) + censored
    return censored / total if total else None


def classify_deployment_frequency(per_week: float) -> str:
    if per_week >= 7:
        return "Elite"
    if per_week >= 1:
        return "High"
    if per_week >= 1 / 4.345:
        return "Medium"
    return "Low"


def classify_lead_time(hours: float) -> str:
    if hours < 24:
        return "Elite"
    if hours < 24 * 7:
        return "High"
    if hours < 24 * 30:
        return "Medium"
    return "Low"


def classify_cfr(value: float) -> str:
    if value <= 0.15:
        return "Elite"
    if value <= 0.30:
        return "High"
    if value <= 0.45:
        return "Medium"
    return "Low"


def classify_recovery(hours: float) -> str:
    if hours < 1:
        return "Elite"
    if hours < 24:
        return "High"
    if hours < 24 * 7:
        return "Medium"
    return "Low"


def overall_classification(categories: Iterable[str]) -> str:
    score = {"Elite": 4, "High": 3, "Medium": 2, "Low": 1}
    reverse = {4: "Elite", 3: "High", 2: "Medium", 1: "Low"}
    values = [score[x] for x in categories]
    if len(values) != 4:
        raise ValueError("A classificação geral exige exatamente quatro métricas.")
    final_score = floor(median(values))
    return reverse[final_score]
