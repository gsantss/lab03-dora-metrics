from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from collections import defaultdict
from datetime import datetime

import requests

from metricas import version_key

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


def previous_releases(history: list[dict], ties_to_latest: bool = False) -> list[dict | None]:
    """Release anterior de cada release de `history` (em ordem de publicação).

    É a maior versão menor que a da release, com o mesmo prefixo de tag, publicada antes
    dela: assim um patch de uma linha antiga (3.6.3 publicada depois da 4.7.2) é comparado
    com a 3.6.2, e não com uma release de outra linha. Sem versão reconhecível ou sem
    candidata na mesma linha, vale a anterior por data.

    `ties_to_latest` (variantes com pré-releases e tags): versões iguais contam como
    anteriores, e vale a mais recente; `2.0.0` é comparada com `2.0.0-rc2`, não com `1.9.x`.
    """
    output: list[dict | None] = []
    lines: dict[str, list[tuple[tuple[int, int, int], int]]] = defaultdict(list)

    for i, release in enumerate(history):
        chosen = history[i - 1] if i else None
        key = version_key(release["tag_name"])
        if key is not None:
            prefix, version = key
            line = lines[prefix]
            position = bisect_right(line, (version, i)) if ties_to_latest else bisect_left(line, (version,))
            if position:
                chosen = history[line[position - 1][1]]
            insort(line, (version, i))
        output.append(chosen)

    return output


def collect_tags(api: GitHubAPI, owner: str, repo: str) -> list[dict]:
    return api.get_all(f"/repos/{owner}/{repo}/tags")


def slim_compare(data: dict) -> dict:
    # O compare traz os diffs dos arquivos em "files"; o lead time só usa sha, data e mensagem.
    return {
        "total_commits": data.get("total_commits", 0),
        "commits": [
            {
                "sha": c.get("sha"),
                "commit": {
                    "author": {"date": c.get("commit", {}).get("author", {}).get("date")},
                    "message": c.get("commit", {}).get("message", ""),
                },
            }
            for c in data.get("commits", [])
        ],
    }


def compare_commits(api: GitHubAPI, path: str) -> list[dict]:
    # O compare devolve um objeto com a lista em "commits"; sem paginar, para em 250.
    commits: list[dict] = []
    page = 1
    while True:
        data, _ = api.get_json(path, {"per_page": 100, "page": page}, slim=slim_compare)
        batch = data.get("commits", [])
        commits.extend(batch)
        if not batch or len(commits) >= data.get("total_commits", 0):
            return commits
        page += 1


def commits_between_releases(
    api: GitHubAPI,
    owner: str,
    repo: str,
    all_published_releases: list[dict],
    releases_in_window: list[dict],
    ties_to_latest: bool = False,
) -> tuple[list[dict], list[dict]]:
    index = {r["id"]: i for i, r in enumerate(all_published_releases)}
    previous_of = previous_releases(all_published_releases, ties_to_latest)
    records: list[dict] = []
    ignored: list[dict] = []

    for release in releases_in_window:
        previous = previous_of[index[release["id"]]]
        if previous is None:
            ignored.append(
                {
                    "release_id": release["id"],
                    "tag_name": release["tag_name"],
                    "reason": "no_previous_release",
                }
            )
            continue

        base = previous["tag_name"]
        head = release["tag_name"]
        path = f"/repos/{owner}/{repo}/compare/{base}...{head}"

        try:
            commits = compare_commits(api, path)
        except (requests.RequestException, RuntimeError) as exc:
            ignored.append(
                {
                    "release_id": release["id"],
                    "tag_name": head,
                    "reason": f"compare_error:{type(exc).__name__}",
                }
            )
            continue

        if not commits:
            ignored.append(
                {
                    "release_id": release["id"],
                    "tag_name": head,
                    "reason": "no_new_commits",
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
                    "commit_message": commit.get("commit", {}).get("message", "").split("\n", 1)[0],
                }
            )

    return records, ignored
