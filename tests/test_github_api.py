import time

import pytest

from pipeline.github_api import GitHubAPI


class FakeResponse:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code = status
        self._data = data if data is not None else {}
        self.headers = headers or {}
        self.text = str(self._data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    sleeps.clear()
    return GitHubAPI(cache_dir=tmp_path, token="fake")


sleeps: list[float] = []


def script(api, monkeypatch, responses):
    calls = []
    queue = list(responses)

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        return queue.pop(0)

    monkeypatch.setattr(api.session, "get", fake_get)
    return calls


def test_requires_token(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        GitHubAPI(cache_dir=tmp_path)


def test_second_call_is_served_from_disk_cache(api, monkeypatch):
    calls = script(api, monkeypatch, [FakeResponse(data={"ok": 1})])
    first, _ = api.get_json("/x", {"a": 1})
    second, _ = api.get_json("/x", {"a": 1})
    assert first == second == {"ok": 1}
    assert len(calls) == 1


def test_cache_survives_new_client_instance(api, monkeypatch, tmp_path):
    script(api, monkeypatch, [FakeResponse(data={"ok": 1})])
    api.get_json("/x")
    other = GitHubAPI(cache_dir=tmp_path, token="fake")
    calls = script(other, monkeypatch, [])
    data, _ = other.get_json("/x")
    assert data == {"ok": 1}
    assert calls == []


def test_5xx_retries_with_exponential_backoff(api, monkeypatch):
    calls = script(
        api,
        monkeypatch,
        [FakeResponse(502), FakeResponse(503), FakeResponse(500), FakeResponse(data={"ok": 1})],
    )
    data, _ = api.get_json("/x")
    assert data == {"ok": 1}
    assert len(calls) == 4
    assert sleeps == [1, 2, 4]


def test_5xx_gives_up_after_max_attempts(api, monkeypatch):
    script(api, monkeypatch, [FakeResponse(500)] * 3)
    with pytest.raises(RuntimeError):
        api.get_json("/x", max_attempts=3)


def test_rate_limit_waits_until_reset_then_retries(api, monkeypatch):
    now = 1_000_000
    monkeypatch.setattr(time, "time", lambda: now)
    limited = FakeResponse(
        403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(now + 30)}
    )
    calls = script(api, monkeypatch, [limited, FakeResponse(data={"ok": 1})])
    data, _ = api.get_json("/x")
    assert data == {"ok": 1}
    assert len(calls) == 2
    assert sleeps == [32]


def test_get_all_follows_pages_until_short_page(api, monkeypatch):
    calls = script(
        api,
        monkeypatch,
        [FakeResponse(data=[1, 2]), FakeResponse(data=[3])],
    )
    assert api.get_all("/x", {"per_page": 2}) == [1, 2, 3]
    assert [c[1]["page"] for c in calls] == [1, 2]


def test_get_all_unwraps_workflow_runs_and_items(api, monkeypatch):
    script(api, monkeypatch, [FakeResponse(data={"workflow_runs": [{"id": 1}]})])
    assert api.get_all("/runs") == [{"id": 1}]
    script(api, monkeypatch, [FakeResponse(data={"items": [{"id": 2}]})])
    assert api.get_all("/search") == [{"id": 2}]


def test_get_all_rejects_unexpected_payload(api, monkeypatch):
    script(api, monkeypatch, [FakeResponse(data={"foo": 1})])
    with pytest.raises(TypeError):
        api.get_all("/x")


def test_contributor_count_reads_last_page_from_link_header(api, monkeypatch):
    link = (
        '<https://api.github.com/repositories/1/contributors?per_page=1&anon=true&page=2>; rel="next", '
        '<https://api.github.com/repositories/1/contributors?per_page=1&anon=true&page=137>; rel="last"'
    )
    script(api, monkeypatch, [FakeResponse(data=[{"login": "a"}], headers={"Link": link})])
    assert api.contributor_count("o", "r") == 137


def test_contributor_count_without_link_header(api, monkeypatch):
    script(api, monkeypatch, [FakeResponse(data=[{"login": "a"}])])
    assert api.contributor_count("o", "r") == 1
