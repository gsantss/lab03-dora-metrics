from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .collect import SampleWriter, collect_repository
from .dataset import build_metrics
from .github_api import GitHubAPI
from .selection import Funnel, candidate_repositories, write_csv


def _parse_day(value: str, end_of_day: bool = False) -> datetime:
    day = datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)
    return day.replace(hour=23, minute=59, second=59) if end_of_day else day


def run(config_path: str, metrics_only: bool = False) -> Funnel | None:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    start = _parse_day(config["window"]["start"])
    end = _parse_day(config["window"]["end"], end_of_day=True)
    out_dir = Path(config["output_dir"])

    funnel = None if metrics_only else collect(config, start, end, out_dir)
    count = build_metrics(out_dir, start, end)
    print(f"[métricas] {count} repositórios em {out_dir / 'metrics.csv'}")
    return funnel


def collect(config: dict, start: datetime, end: datetime, out_dir: Path) -> Funnel:
    sample_size = config["sample_size"]
    api = GitHubAPI(cache_dir=config["cache_dir"])
    funnel = Funnel()

    with SampleWriter(out_dir) as writer:
        for repo in candidate_repositories(api):
            if funnel.counts["included"] >= sample_size:
                break
            funnel.reached("candidates")

            data = collect_repository(
                api,
                repo,
                start,
                end,
                funnel,
                min_releases=config["min_releases"],
                min_runs=config["min_runs"],
            )
            if data:
                writer.write(data)
                print(f"[{funnel.counts['included']}/{sample_size}] {repo['full_name']}")

    write_csv(out_dir / "funnel.csv", funnel.to_rows())
    if funnel.counts["included"] < sample_size:
        print(f"[aviso] candidatos esgotados: {funnel.counts['included']}/{sample_size} repositórios.")
    return funnel


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument(
        "--metrics-only",
        action="store_true",
        help="só recalcula metrics.csv a partir dos CSVs já coletados (sem API)",
    )
    args = parser.parse_args()
    run(args.config, metrics_only=args.metrics_only)


if __name__ == "__main__":
    main()
