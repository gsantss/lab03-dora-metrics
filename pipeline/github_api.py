from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse, parse_qs

import requests


class GitHubAPI:
    BASE_URL = "https://api.github.com"

    def __init__(self, cache_dir: str | Path = "data/cache", token: str | None = None):
        token = token or os.getenv("GITHUB_TOKEN")
        if not token:
            raise RuntimeError("Defina a variável de ambiente GITHUB_TOKEN.")

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "lab03-dora-metrics",
            }
        )

    @staticmethod
    def _cache_key(url: str, params: dict[str, Any] | None) -> str:
        payload = json.dumps({"url": url, "params": params or {}}, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _cache_path(self, url: str, params: dict[str, Any] | None) -> Path:
        return self.cache_dir / f"{self._cache_key(url, params)}.json"

    def get_json(
        self,
        path_or_url: str,
        params: dict[str, Any] | None = None,
        *,
        use_cache: bool = True,
        max_attempts: int = 6,
        slim: Callable[[Any], Any] | None = None,
    ) -> tuple[Any, dict[str, str]]:
        """`slim` reduz a resposta antes de ir para o cache (só os campos usados)."""
        url = path_or_url if path_or_url.startswith("http") else f"{self.BASE_URL}{path_or_url}"
        cache_path = self._cache_path(url, params)

        if use_cache and cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return cached["data"], cached.get("headers", {})

        delay = 1
        last_error = None

        for attempt in range(max_attempts):
            try:
                response = self.session.get(url, params=params, timeout=60)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise

            remaining = response.headers.get("X-RateLimit-Remaining")
            reset = response.headers.get("X-RateLimit-Reset")

            if response.status_code in {403, 429} and remaining == "0" and reset:
                sleep_for = max(int(reset) - int(time.time()) + 2, 1)
                print(f"[rate-limit] aguardando {sleep_for}s...")
                time.sleep(sleep_for)
                continue

            retry_after = response.headers.get("Retry-After")
            if response.status_code in {403, 429} and retry_after:
                sleep_for = max(int(retry_after), 1)
                print(f"[rate-limit secundário] aguardando {sleep_for}s...")
                time.sleep(sleep_for)
                continue

            if 500 <= response.status_code < 600:
                last_error = RuntimeError(
                    f"GitHub retornou {response.status_code}: {response.text[:300]}"
                )
                if attempt < max_attempts - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue

            response.raise_for_status()
            data = response.json()
            if slim is not None:
                data = slim(data)
            headers = {
                "Link": response.headers.get("Link", ""),
                "X-RateLimit-Remaining": response.headers.get("X-RateLimit-Remaining", ""),
                "X-RateLimit-Reset": response.headers.get("X-RateLimit-Reset", ""),
            }

            if use_cache:
                cache_path.write_text(
                    json.dumps({"data": data, "headers": headers}, ensure_ascii=False),
                    encoding="utf-8",
                )
            return data, headers

        raise last_error or RuntimeError("Falha desconhecida ao consultar GitHub.")

    def get_all(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        slim: Callable[[Any], Any] | None = None,
    ) -> list[Any]:
        params = dict(params or {})
        params.setdefault("per_page", 100)
        page = 1
        output: list[Any] = []

        while True:
            page_params = dict(params)
            page_params["page"] = page
            data, _ = self.get_json(path, page_params, slim=slim)

            if isinstance(data, dict) and "items" in data:
                batch = data["items"]
            elif isinstance(data, dict) and "workflow_runs" in data:
                batch = data["workflow_runs"]
            elif isinstance(data, list):
                batch = data
            else:
                raise TypeError(f"Resposta paginada inesperada para {path}")

            output.extend(batch)
            if len(batch) < page_params["per_page"]:
                break
            page += 1

        return output

    def contributor_count(self, owner: str, repo: str) -> int:
        path = f"/repos/{owner}/{repo}/contributors"
        data, headers = self.get_json(path, {"per_page": 1, "anon": "true"})
        link = headers.get("Link", "")

        if 'rel="last"' in link:
            for part in link.split(","):
                if 'rel="last"' in part:
                    url = part.split(";")[0].strip().strip("<>")
                    query = parse_qs(urlparse(url).query)
                    return int(query.get("page", ["1"])[0])

        return len(data) if isinstance(data, list) else 0
