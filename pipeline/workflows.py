from __future__ import annotations

import calendar
from datetime import datetime, timedelta

from .github_api import GitHubAPI


VALID_SUCCESS = {"success"}
VALID_FAILURE = {"failure", "timed_out", "startup_failure"}
IGNORED = {"cancelled", "skipped", "neutral", "action_required", "stale", None, ""}


def month_windows(start: datetime, end: datetime):
    cursor = datetime(start.year, start.month, 1, tzinfo=start.tzinfo)

    while cursor <= end:
        days = calendar.monthrange(cursor.year, cursor.month)[1]
        month_end = cursor.replace(day=days, hour=23, minute=59, second=59)
        chunk_start = max(start, cursor)
        chunk_end = min(end, month_end)
        yield chunk_start, chunk_end
        cursor = month_end + timedelta(seconds=1)


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

    for chunk_start, chunk_end in month_windows(start, end):
        created = f"{chunk_start.date().isoformat()}..{chunk_end.date().isoformat()}"
        runs = api.get_all(
            f"/repos/{owner}/{repo}/actions/runs",
            {
                "branch": default_branch,
                "event": "push",
                "created": created,
            },
        )

        if len(runs) >= 1000:
            raise RuntimeError(
                f"{owner}/{repo}: um mês atingiu 1000 workflow runs; subdivida esse mês."
            )

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
