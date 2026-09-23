"""승격 공백 관측 — 계약 TDD (2026-09-23 실측 결함 후속).

09-21·09-22 nightly 가 수집한 55건이 존에 한 번도 올라가지 않은 채 이틀간
**아무 경보도 없었다.** 배포된 `run_collect` 에 승격 단계가 없었기 때문인데,
승격이 event 경로로 옮겨간 지금도 consumer 가 죽어 있으면 같은 침묵이 반복된다
— 실제로 같은 날 consumer 는 무한 재기동 중이었고 그것도 lag 를 직접 본 뒤에야
알았다. 공백은 **탐지 가능해야** 한다.

관측 지점은 nightly 수집 **직전**이다. 그 시점의 공백은 전날 수집분이 하루가
지나도록 승격되지 않았다는 뜻이고, 이번 런이 방금 발행한 이벤트의 비동기 승격
지연과 섞이지 않는다.
"""
from __future__ import annotations

import pathlib

import pytest

from orc_citadel.incremental_promote import promote_incremental
from orc_citadel.promotion_gap import (
    GAP_SAMPLE,
    PromotionGap,
    measure_promotion_gap,
)
from orc_citadel.raw_shard import RawShardStore

HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""


def _html(tag: str) -> bytes:
    return HTML.replace(b"<h1>", b"<h1>" + tag.encode() + b" ")


@pytest.fixture
def workspace(tmp_path):
    raw, data = tmp_path / "raw", tmp_path / "data"
    data.mkdir()
    return raw, data


def _seed(raw: pathlib.Path, tags: list[str]) -> list[str]:
    store = RawShardStore(raw)
    doc_ids = [store.append("official-nvidia-news", f"https://e/{tag}",
                            _html(tag), {})[0] for tag in tags]
    store.flush()
    return doc_ids


def test_gap_is_zero_when_every_raw_document_reached_the_zone(workspace):
    raw, data = workspace
    _seed(raw, ["a", "b"])
    promote_incremental(raw, data)

    gap = measure_promotion_gap(raw, data)

    assert gap == PromotionGap(gap=0, sample=())
    assert gap.behind is False


def test_gap_counts_the_documents_the_zone_never_received(workspace):
    raw, data = workspace
    _seed(raw, ["a", "b"])
    promote_incremental(raw, data)
    missing = _seed(raw, ["c", "d"])

    gap = measure_promotion_gap(raw, data)

    assert gap.gap == 2
    assert gap.behind is True
    assert set(gap.sample) == set(missing)


def test_sample_is_bounded_so_a_large_gap_stays_loggable(workspace):
    raw, data = workspace
    _seed(raw, ["a", "b", "c"])

    gap = measure_promotion_gap(raw, data, sample=1)

    # 공백 자체는 전수 집계하되, 로그에 싣는 근거는 상한이 있어야 한다 —
    # 1,000만 스케일에서 공백 목록 전량은 로그도 메모리도 감당하지 못한다.
    assert gap.gap == 3
    assert len(gap.sample) == 1
    assert GAP_SAMPLE > 0


def test_gap_describes_itself_with_evidence_for_the_run_log(workspace):
    raw, data = workspace
    missing = _seed(raw, ["a"])

    described = measure_promotion_gap(raw, data).describe()

    assert "1" in described and missing[0] in described


# ---- nightly 런과의 결합 (메트릭 경로까지) ----

def _nightly(monkeypatch, raw: pathlib.Path):
    """수집은 0건으로 고정한 nightly 런 — 관측 경로만 남긴다."""
    from scripts import nightly_collect
    import orc_citadel.collect_large as cl

    monkeypatch.setattr(nightly_collect.KafkaEventProducer, "from_env",
                        lambda: None)
    monkeypatch.setattr(cl, "SOURCES", {"rss-test": ("rss", "https://feed")})
    monkeypatch.setattr(nightly_collect, "SOURCES", cl.SOURCES)
    monkeypatch.setattr(cl, "RAW", raw)
    monkeypatch.setattr(cl, "_SHARD_STORES", {})
    monkeypatch.setitem(
        cl.COLLECTORS, "rss",
        lambda spec, source_id, *, slo_log, known_urls, event_producer:
            {"saved": 0, "skipped": 0, "errors": 0})
    return nightly_collect


def test_nightly_summary_carries_the_gap_into_the_run_metrics(monkeypatch, workspace):
    raw, _ = workspace
    _seed(raw, ["a", "b"])
    nightly_collect = _nightly(monkeypatch, raw)

    summary = nightly_collect.main()

    from orc_citadel.run_metrics import summary_metrics
    rows = {row["metric"]: row["value"] for row in summary_metrics(summary)
            if not row["labels"]}
    # 공백이 postgres 메트릭 행이 돼야 대시보드·경보가 볼 수 있다.
    assert rows["promotion_gap"] == 2.0


def test_unmeasurable_gap_is_not_reported_as_zero(monkeypatch, workspace, capsys):
    raw, _ = workspace
    nightly_collect = _nightly(monkeypatch, raw)

    def unreachable(*_a, **_kw):
        raise RuntimeError("lakekeeper unreachable")

    monkeypatch.setattr(nightly_collect, "measure_promotion_gap", unreachable)

    summary = nightly_collect.main()

    # 관측 계층 장애가 수집 런을 실패시키면 안 되고(§6.2), 미관측을 "공백 0"
    # 으로 위장해서도 안 된다 — 키 자체가 없어야 한다.
    assert summary["total_new"] == 0
    assert "promotion_gap" not in summary
    assert "lakekeeper unreachable" in capsys.readouterr().out


def test_gap_warning_names_the_stranded_documents_in_the_run_log(monkeypatch,
                                                                 workspace, capsys):
    raw, _ = workspace
    missing = _seed(raw, ["a"])
    nightly_collect = _nightly(monkeypatch, raw)

    nightly_collect.main()

    out = capsys.readouterr().out
    assert "WARN" in out and missing[0] in out
