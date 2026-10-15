from __future__ import annotations

import calendar
from datetime import datetime, time, timedelta

from .github_api import GitHubAPI


VALID_SUCCESS = {"success"}
VALID_FAILURE = {"failure", "timed_out", "startup_failure"}
IGNORED = {"cancelled", "skipped", "neutral", "action_required", "stale", None, ""}
RUNS_CAP = 1000  # a API devolve no máximo 1000 runs por consulta filtrada
MIN_SPLIT = timedelta(minutes=1)
RUN_FIELDS = (
    "id",
    "workflow_id",
    "name",
    "conclusion",
    "event",
    "head_branch",
    "created_at",
    "run_started_at",
    "updated_at",
    "html_url",
)


def slim_runs(data: dict) -> dict:
    # Cada run completo traz ~10 KB (repositório, ator, commit); o cache guarda só o usado.
    return {
        "total_count": data.get("total_count", 0),
        "workflow_runs": [{k: run.get(k) for k in RUN_FIELDS} for run in data.get("workflow_runs", [])],
    }


def month_windows(start: datetime, end: datetime):
    cursor = datetime(start.year, start.month, 1, tzinfo=start.tzinfo)

    while cursor <= end:
        days = calendar.monthrange(cursor.year, cursor.month)[1]
        month_end = cursor.replace(day=days, hour=23, minute=59, second=59)
        chunk_start = max(start, cursor)
        chunk_end = min(end, month_end)
        yield chunk_start, chunk_end
        cursor = month_end + timedelta(seconds=1)


def _created(first: datetime, last: datetime) -> str:
    # Dias inteiros vão só com a data: mantém as chaves de cache das coletas anteriores.
    if first.time() == time(0) and last.time() == time(23, 59, 59):
        return f"{first.date().isoformat()}..{last.date().isoformat()}"
    return f"{first:%Y-%m-%dT%H:%M:%SZ}..{last:%Y-%m-%dT%H:%M:%SZ}"


def runs_in_range(
    api: GitHubAPI,
    path: str,
    default_branch: str,
    first: datetime,
    last: datetime,
) -> list[dict]:
    params = {"branch": default_branch, "event": "push", "created": _created(first, last)}
    # Mesma chave de cache da 1ª página do get_all: a checagem do teto não gasta cota extra.
    first_page, _ = api.get_json(path, {**params, "per_page": 100, "page": 1}, slim=slim_runs)
    if int(first_page.get("total_count", 0)) < RUNS_CAP:
        return api.get_all(path, params, slim=slim_runs)

    days = (last.date() - first.date()).days
    if days:
        # Vários dias: divide em dias inteiros.
        middle_day = first.date() + timedelta(days=days // 2)
        split = datetime.combine(middle_day, time(23, 59, 59), tzinfo=first.tzinfo)
    elif last - first >= MIN_SPLIT:
        # Um dia com 1000+ runs (pytorch, sentry…): divide o dia em horas, minutos.
        split = first + timedelta(seconds=int((last - first).total_seconds()) // 2)
    else:
        raise RuntimeError(f"{path}: {first:%Y-%m-%d %H:%M} atingiu {RUNS_CAP} workflow runs em menos de um minuto.")

    return runs_in_range(api, path, default_branch, first, split) + runs_in_range(
        api, path, default_branch, split + timedelta(seconds=1), last
    )


def collect_workflow_runs(
    api: GitHubAPI,
    owner: str,
    repo: str,
    default_branch: str,
    start: datetime,
    end: datetime,
) -> list[dict]:
    output: list[dict] = []
    seen: set[int] = set()

    path = f"/repos/{owner}/{repo}/actions/runs"

    for chunk_start, chunk_end in month_windows(start, end):
        runs = runs_in_range(api, path, default_branch, chunk_start, chunk_end)

        for run in runs:
            run_id = int(run["id"])
            if run_id in seen:
                continue
            seen.add(run_id)

            conclusion = run.get("conclusion")
            if conclusion in IGNORED:
                continue
            if conclusion not in VALID_SUCCESS | VALID_FAILURE:
                continue

            output.append(
                {
                    "id": run_id,
                    "workflow_id": run.get("workflow_id"),
                    "name": run.get("name"),
                    "conclusion": conclusion,
                    "event": run.get("event"),
                    "head_branch": run.get("head_branch"),
                    "created_at": run.get("created_at"),
                    "run_started_at": run.get("run_started_at"),
                    "updated_at": run.get("updated_at"),
                    "html_url": run.get("html_url"),
                }
            )

    output.sort(key=lambda r: (r.get("run_started_at") or r.get("created_at") or ""))
    return output
