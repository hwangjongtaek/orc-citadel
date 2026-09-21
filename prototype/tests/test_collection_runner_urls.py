"""허가된 고정 공식 URL 수집 계약."""
from __future__ import annotations


def test_collect_urls_fetches_only_unseen_registered_urls(monkeypatch, tmp_path):
    from orc_citadel import collect_large

    saved = []
    monkeypatch.setattr(collect_large, "_get", lambda url: (url.encode(), {"Content-Type": "text/html"}))
    monkeypatch.setattr(collect_large, "_save_zone", lambda source_id, url, content, meta: saved.append((source_id, url, meta)) or ("doc-1", True))

    result = collect_large.collect_urls(
        ["https://news.blizzard.com/article/a", "https://news.blizzard.com/article/b"],
        "official-blizzard-blizzcon-2026", known_urls={"https://news.blizzard.com/article/a"},
    )

    assert result == {"saved": 1, "skipped": 1, "errors": 0}
    assert saved[0][0:2] == ("official-blizzard-blizzcon-2026", "https://news.blizzard.com/article/b")
