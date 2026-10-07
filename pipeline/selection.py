from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

from .github_api import GitHubAPI


@dataclass
class Funnel:
    candidates: int = 0
    with_actions: int = 0
    with_min_releases: int = 0
    with_min_runs: int = 0
    included: int = 0

    def to_rows(self) -> list[dict[str, int | str]]:
        return [
            {"stage": "candidates", "count": self.candidates},
            {"stage": "with_actions", "count": self.with_actions},
            {"stage": "with_min_releases", "count": self.with_min_releases},
            {"stage": "with_min_runs", "count": self.with_min_runs},
            {"stage": "included", "count": self.included},
        ]


STAR_QUERIES = [
    "stars:>50000",
    "stars:20000..50000",
    "stars:10000..19999",
    "stars:5000..9999",
    "stars:2000..4999",
    "stars:1000..1999",
]


def candidate_repositories(api: GitHubAPI) -> Iterable[dict]:
    seen: set[str] = set()
    for stars in STAR_QUERIES:
        for page in range(1, 11):
            data, _ = api.get_json(
                "/search/repositories",
                {
                    "q": f"{stars} archived:false mirror:false",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": 100,
                    "page": page,
                },
            )
            items = data.get("items", [])
            if not items:
                break

            for repo in items:
                full_name = repo["full_name"]
                if full_name not in seen:
                    seen.add(full_name)
                    yield repo

            if len(items) < 100:
                break


def has_actions(api: GitHubAPI, owner: str, repo: str) -> bool:
    data, _ = api.get_json(f"/repos/{owner}/{repo}/actions/workflows", {"per_page": 1})
    return int(data.get("total_count", 0)) > 0


def write_csv(path: str | Path, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
