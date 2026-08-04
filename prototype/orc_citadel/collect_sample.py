"""소량 실수집 (04 signal verification, prototype).

각 소스에서 제한된 수의 문서를 수집 → raw 3-zone(data/raw/) 저장.
politeness 준수: arXiv 1 req/3s, SEC 10 req/s + 선언 UA, press feeds는 항목 수 제한.
실은 "커넥터 구현 + 소량 실수집(신호 검증)" 계획의 스모크 — 전체 1만 수집 아님.
"""
from __future__ import annotations

import json
import pathlib
import re
import time
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent  # prototype/
RAW = ROOT / "data" / "raw"

# press(RSS), research(arXiv), gov(SEC) 3개 소스 유형 — design 04 §1.4 실제 소스로 신호 검증.
FEEDS = {
    # 공식 NVIDIA Newsroom RSS (design 04 §1.4 #4, official)
    "official": "https://nvidianews.nvidia.com/rss.xml",
    # 공식 press RSS — SemiEngineering (design 04 §1.4 #5, press)
    "press": "https://semiengineering.com/feed/",
    # 공식 research — arXiv (design 04 §1.4 #2, research)
    "research": [
        # arXiv OAI search — 1 req/3s, 반드시 UA 선언
        ("https://export.arxiv.org/api/query", {
            "search_query": "cat:cs.CR", "start": "0", "max_results": "3",
        }),
    ],
    "gov": None,  # SEC는 robots/인증 정교화 후 별도 — 이번 스모크는 제외
}
USER_AGENT = "OrcCitadel-Research (prototype; contact research@example.com)"
MAX_PER_SOURCE = 3
ARXIV_INTERVAL = 3.0


def _get(url: str) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read(), dict(resp.headers)


def _save_zone(store_dir: pathlib.Path, source_id: str, url: str,
               content: bytes, meta: dict) -> str:
    """raw 3-zone: data/raw/<source_id>/doc/<doc_id>/content.bin + fetch.json."""
    import hashlib

    doc_id = "doc-" + hashlib.sha256(content).hexdigest()[:24]
    d = store_dir / source_id / "doc" / doc_id
    # 내용 기반 doc_id 불변식 (03 §2.1): 동일 bytes는 이미 존재 → no-op 중복 제거.
    if d.exists():
        return doc_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "content.bin").write_bytes(content)
    meta["doc_id"] = doc_id
    meta["url"] = url
    meta["fetched_at"] = datetime.now(timezone.utc).isoformat()
    (d / "fetch.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return doc_id


def collect_rss(feed_url: str, source_id: str, label: str) -> None:
    xml, _ = _get(feed_url)
    body = xml.decode("utf-8", errors="replace")
    links = re.findall(r"<link>\s*(\S+)\s*</link>", body)
    seen: set[str] = set()
    n = 0
    for url in links:
        if url.startswith("http") and url not in seen:
            seen.add(url)
            try:
                content, hdrs = _get(url)
            except Exception as e:
                print(f"  [{label}] skip {url}: {e}")
                continue
            _save_zone(RAW, source_id, url, content,
                       {"http_status": 200, "content_type": hdrs.get("Content-Type")})
            n += 1
            print(f"  [{label}] saved {url} -> {n}")
            if n >= MAX_PER_SOURCE:
                break


def collect_arxiv() -> None:
    url, params = FEEDS["research"][0]
    data = "&".join(f"{k}={v}" for k, v in params.items())
    # politeness: 처음 호출 직전에도 3초 대기 → 시작부터 안전 간격 유지.
    time.sleep(ARXIV_INTERVAL)
    xml, _ = _get(f"{url}?{data}")
    time.sleep(ARXIV_INTERVAL)
    for entry in re.findall(r"<entry>(.*?)</entry>", xml.decode("utf-8", errors="replace"), re.S):
        m = re.search(r"<id>\s*(\S+)\s*</id>", entry)
        if not m:
            continue
        doc_url = m.group(1)
        content, hdrs = _get(doc_url)
        _save_zone(RAW, "research-arxiv-cs-cr", doc_url, content,
                   {"http_status": 200, "content_type": hdrs.get("Content-Type")})
        print(f"  [research] saved {doc_url}")
        # politeness: 각 실물 문서 호출 후 3초 대기 (1 req/3s 준수).
        time.sleep(ARXIV_INTERVAL)


def main() -> None:
    print("== 소량 실수집 스모크 (04) ==")
    print(f"raw zone: {RAW}")
    RAW.mkdir(parents=True, exist_ok=True)
    print("[official] NVIDIA Newsroom RSS")
    collect_rss(FEEDS["official"], "official-nvidia-news", "official")
    print("[press] SemiEngineering RSS")
    collect_rss(FEEDS["press"], "press-semiengineering", "press")
    print("[research] arXiv")
    collect_arxiv()
    print("[gov] SEC — 이번 스모크에서 제외 (robots/인증 정교화 후 별도)")
    print("== 완료 ==")


if __name__ == "__main__":
    main()
