from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RepositoryRecord:
    full_name: str
    owner: str
    name: str
    html_url: str
    default_branch: str
    stars: int
    language: str | None
    created_at: str
    contributors: int | None
    releases_valid: int
    workflow_runs_valid: int

    def asdict(self) -> dict[str, Any]:
        return self.__dict__.copy()
