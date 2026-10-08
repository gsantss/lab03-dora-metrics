from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .github_api import GitHubAPI
from .releases import collect_releases
from .selection import Funnel, candidate_repositories, has_actions, write_csv
from .workflows import collect_workflow_runs


def _parse_day(value: str, end_of_day: bool = False) -> datetime:
    day = datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)
    return day.replace(hour=23, minute=59, second=59) if end_of_day else day


def run(config_path: str) -> None:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    start = _parse_day(config["window"]["start"])
    end = _parse_day(config["window"]["end"], end_of_day=True)
    out_dir = Path(config["output_dir"])

    api = GitHubAPI(cache_dir=config["cache_dir"])
    funnel = Funnel()
    selected: list[dict] = []

    for repo in candidate_repositories(api):
        if len(selected) >= config["sample_size"]:
            break
        funnel.candidates += 1
        owner, name = repo["owner"]["login"], repo["name"]

        if not has_actions(api, owner, name):
            continue
        funnel.with_actions += 1

        _, in_window = collect_releases(api, owner, name, start, end)
        if len(in_window) < config["min_releases"]:
            continue
        funnel.with_min_releases += 1

        runs = collect_workflow_runs(api, owner, name, repo["default_branch"], start, end)
        if len(runs) < config["min_runs"]:
            continue
        funnel.with_min_runs += 1

        selected.append(
            {
                "full_name": repo["full_name"],
                "default_branch": repo["default_branch"],
                "stars": repo["stargazers_count"],
                "language": repo.get("language"),
                "created_at": repo["created_at"],
                "contributors": api.contributor_count(owner, name),
                "releases_valid": len(in_window),
                "workflow_runs_valid": len(runs),
            }
        )
        funnel.included = len(selected)
        print(f"[{len(selected)}/{config['sample_size']}] {repo['full_name']}")

    write_csv(out_dir / "funnel.csv", funnel.to_rows())
    write_csv(out_dir / "repositories.csv", selected)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    parser.add_argument("--config", default="config.yaml")
    run(parser.parse_args().config)


if __name__ == "__main__":
    main()
