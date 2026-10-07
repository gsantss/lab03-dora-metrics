from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from math import floor
from statistics import median
from typing import Iterable


FAILURES = {"failure", "timed_out", "startup_failure"}
SUCCESSES = {"success"}
IGNORED = {"cancelled", "skipped", "neutral", "action_required", "stale", None, ""}


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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
