from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .github_api import GitHubAPI


STAGES = ("candidates", "with_actions", "with_min_releases", "with_min_runs", "included")


@dataclass
class Funnel:
    """Quantos repositórios chegaram a cada etapa e por que os demais ficaram nela."""

    counts: Counter = field(default_factory=Counter)
    discards: defaultdict = field(default_factory=lambda: defaultdict(Counter))

    def reached(self, stage: str) -> None:
        self.counts[stage] += 1

    def discard(self, stage: str, reason: str) -> None:
        """Registra um repositório que não chegou a `stage` pelo motivo `reason`."""
        self.discards[stage][reason] += 1

    def to_rows(self) -> list[dict[str, int | str]]:
        return [
            {
                "stage": stage,
                "count": self.counts[stage],
                "discarded": sum(self.discards[stage].values()),
                "reasons": "; ".join(f"{r}={n}" for r, n in sorted(self.discards[stage].items())),
            }
            for stage in STAGES
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
