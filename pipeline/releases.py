from __future__ import annotations

from datetime import datetime, timezone

from .github_api import GitHubAPI


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def collect_releases(
    api: GitHubAPI,
    owner: str,
    repo: str,
    start: datetime,
    end: datetime,
) -> tuple[list[dict], list[dict]]:
    releases = api.get_all(f"/repos/{owner}/{repo}/releases")

    published = [
        r
        for r in releases
        if not r.get("draft")
        and r.get("published_at")
    ]
    published.sort(key=lambda r: parse_dt(r["published_at"]))

    main_window = [
        r
        for r in published
        if not r.get("prerelease")
        and start <= parse_dt(r["published_at"]) <= end
    ]

    return published, main_window


def collect_tags(api: GitHubAPI, owner: str, repo: str) -> list[dict]:
    return api.get_all(f"/repos/{owner}/{repo}/tags")


def commits_between_releases(
    api: GitHubAPI,
    owner: str,
    repo: str,
    all_published_releases: list[dict],
    releases_in_window: list[dict],
) -> tuple[list[dict], list[dict]]:
    index = {r["id"]: i for i, r in enumerate(all_published_releases)}
    records: list[dict] = []
    ignored: list[dict] = []

    for release in releases_in_window:
        i = index[release["id"]]
        if i == 0:
            ignored.append(
                {
                    "release_id": release["id"],
                    "tag_name": release["tag_name"],
                    "reason": "no_previous_release",
                }
            )
            continue

        previous = all_published_releases[i - 1]
        base = previous["tag_name"]
        head = release["tag_name"]
        path = f"/repos/{owner}/{repo}/compare/{base}...{head}"

        try:
            commits = api.get_all(path)
        except Exception as exc:
            ignored.append(
                {
                    "release_id": release["id"],
                    "tag_name": head,
                    "reason": f"compare_error:{type(exc).__name__}",
                }
            )
            continue

        for commit in commits:
            author_date = (
                commit.get("commit", {})
                .get("author", {})
                .get("date")
            )
            records.append(
                {
                    "release_id": release["id"],
                    "release_tag": head,
                    "release_published_at": release["published_at"],
                    "commit_sha": commit.get("sha"),
                    "commit_author_date": author_date,
                    "commit_message": commit.get("commit", {}).get("message", ""),
                }
            )

    return records, ignored
