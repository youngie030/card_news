#!/usr/bin/env python3
"""구글뉴스 키워드 RSS를 수집해 data/news_link.json 을 갱신한다.

매 실행은 기존 파일을 덮어쓰지 않고 병합한다. 삭제는 만료(MAX_AGE_DAYS)와
상한(MAX_ITEMS) 규칙으로만 일어나므로, 일시적인 RSS 장애가 데이터 유실로
이어지지 않는다. 키워드 일부가 실패해도 나머지는 저장하며, 전량 실패일
때만 저장을 건너뛰고 종료 코드 1로 끝낸다.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parents[1]
KEYWORDS_PATH = ROOT / "config" / "keywords.json"
OUTPUT_PATH = ROOT / "data" / "news_link.json"

KST = timezone(timedelta(hours=9), "KST")
MAX_AGE_DAYS = 7
MAX_ITEMS = 300
REQUEST_TIMEOUT = 15
REQUEST_INTERVAL = 1.0
USER_AGENT = "card-news-bot/1.0 (+https://github.com/youngie030/card_news)"

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "igshid",
}

SOURCE_SUFFIX_RE = re.compile(r"\s+-\s+[^-]{1,40}$")
# 제목 비교용: 공백과 문장부호를 모두 걷어낸다. 한글·한자는 \w 이므로 남는다.
TITLE_NOISE_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def log(message: str) -> None:
    print(message, flush=True)


# --------------------------------------------------------------------------
# 수집
# --------------------------------------------------------------------------


def build_feed_url(keyword: str) -> str:
    """키워드 검색용 구글뉴스 한국어 RSS URL을 만든다. [FR-C-01]"""
    query = urllib.parse.quote(keyword)
    return (
        f"https://news.google.com/rss/search?q={query}"
        "&hl=ko&gl=KR&ceid=KR:ko"
    )


def fetch_feed(url: str) -> bytes:
    """UA 헤더와 타임아웃을 붙여 피드를 내려받는다. [FR-C-13]"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return response.read()


# --------------------------------------------------------------------------
# 정규화
# --------------------------------------------------------------------------


def normalize_link(link: str) -> str:
    """추적 파라미터와 프래그먼트를 제거한 링크를 돌려준다. [FR-C-06]"""
    parts = urllib.parse.urlsplit(link.strip())
    kept = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    query = urllib.parse.urlencode(kept)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def make_id(normalized_link: str) -> str:
    """정규화된 링크의 SHA-1을 기사 식별자로 사용한다. [FR-C-06]"""
    return hashlib.sha1(normalized_link.encode("utf-8")).hexdigest()


def strip_source_suffix(title: str, source: str) -> str:
    """구글뉴스가 제목 끝에 붙이는 ' - 매체명'을 제거한다. [FR-C-03]"""
    title = title.strip()
    if source:
        # 구글뉴스는 같은 매체명을 두 번 붙여 보내는 경우가 있다.
        suffix = f" - {source}"
        while title.endswith(suffix):
            title = title[: -len(suffix)].strip()
        return title
    # 매체명을 모를 때만 보수적으로 패턴 제거를 시도한다.
    return SOURCE_SUFFIX_RE.sub("", title).strip()


def to_kst_iso(published_parsed) -> str:
    """feedparser의 UTC struct_time을 KST ISO 8601로 바꾼다. [FR-C-05]"""
    if not published_parsed:
        return datetime.now(KST).replace(microsecond=0).isoformat()
    epoch = calendar.timegm(published_parsed)
    return datetime.fromtimestamp(epoch, KST).replace(microsecond=0).isoformat()


def parse_entry(entry, keyword: str) -> dict | None:
    """RSS 엔트리 하나를 스키마에 맞는 항목으로 변환한다. [FR-C-02]"""
    link = (entry.get("link") or "").strip()
    title = (entry.get("title") or "").strip()
    if not link or not title:
        return None

    source = ""
    source_field = entry.get("source")
    if isinstance(source_field, dict):
        source = (source_field.get("title") or "").strip()

    normalized = normalize_link(link)
    return {
        "id": make_id(normalized),
        "title": strip_source_suffix(title, source),
        "link": normalized,
        "source": source,
        "published_at": to_kst_iso(entry.get("published_parsed")),
        "keywords": [keyword],
    }


def collect(keywords: list[str]) -> tuple[list[dict], int]:
    """키워드별로 피드를 조회한다. 개별 실패는 격리한다. [FR-C-11]"""
    collected: list[dict] = []
    failures = 0

    for index, keyword in enumerate(keywords):
        try:
            raw = fetch_feed(build_feed_url(keyword))
            feed = feedparser.parse(raw)
            entries = feed.entries or []
            parsed = [item for item in (parse_entry(e, keyword) for e in entries) if item]
            collected.extend(parsed)
            log(f"  [ok]   {keyword}: {len(parsed)}건")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            failures += 1
            log(f"  [fail] {keyword}: {exc}")
        except Exception as exc:  # 파싱 단계의 예상 못 한 오류도 격리한다.
            failures += 1
            log(f"  [fail] {keyword}: 예기치 못한 오류 - {exc}")

        if index < len(keywords) - 1:
            time.sleep(REQUEST_INTERVAL)

    return collected, failures


# --------------------------------------------------------------------------
# 병합 / 정리 / 저장
# --------------------------------------------------------------------------


def load_existing(path: Path) -> list[dict]:
    """기존 결과를 읽는다. 없거나 깨졌으면 빈 목록으로 시작한다. [FR-C-08]"""
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        log(f"[warn] 기존 {path.name} 을 읽지 못해 새로 시작한다: {exc}")
        return []

    items = data.get("items")
    return items if isinstance(items, list) else []


def merge_items(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """id 기준으로 병합한다. 같은 기사면 keywords를 합집합으로 모은다. [FR-C-07]"""
    merged: dict[str, dict] = {}

    for item in existing + incoming:
        item_id = item.get("id")
        if not item_id:
            continue

        current = merged.get(item_id)
        if current is None:
            merged[item_id] = {**item, "keywords": list(dict.fromkeys(item.get("keywords") or []))}
            continue

        for keyword in item.get("keywords") or []:
            if keyword not in current["keywords"]:
                current["keywords"].append(keyword)

        # 기존 항목에 비어 있던 필드는 새로 들어온 값으로 채운다.
        for field in ("title", "source"):
            if not current.get(field) and item.get(field):
                current[field] = item[field]

    return list(merged.values())


def normalize_title(title: str) -> str:
    """비교용 제목. 공백·문장부호·대소문자 차이를 없앤다. [FR-C-14]"""
    return TITLE_NOISE_RE.sub("", title or "").lower()


def dedupe_by_title(items: list[dict]) -> list[dict]:
    """제목이 같은 기사를 하나로 합친다. [FR-C-14]

    통신사 기사를 여러 매체가 그대로 싣는 경우 링크가 달라 id 중복제거를
    통과한다. 가장 먼저 발행된 항목을 남기고 나머지의 키워드를 합친다.
    발행시각이 같으면 id가 작은 쪽을 남겨 실행마다 결과가 흔들리지 않게 한다.
    """
    groups: dict[str, list[dict]] = {}
    kept: list[dict] = []

    for item in items:
        key = normalize_title(item.get("title", ""))
        if key:
            groups.setdefault(key, []).append(item)
        else:
            kept.append(item)  # 제목이 없으면 판단할 근거가 없으니 그대로 둔다.

    for group in groups.values():
        winner = min(
            group,
            key=lambda i: (parse_published(i.get("published_at", "")), i.get("id", "")),
        )

        keywords = list(winner.get("keywords") or [])
        for other in group:
            for keyword in other.get("keywords") or []:
                if keyword not in keywords:
                    keywords.append(keyword)

        kept.append({**winner, "keywords": keywords})

    return kept


def parse_published(value: str) -> datetime:
    """published_at 문자열을 datetime으로 바꾼다. 실패하면 아주 오래된 값으로 본다."""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=KST)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)


def prune(items: list[dict]) -> list[dict]:
    """만료 항목을 버리고 최신순으로 정렬한 뒤 상한을 적용한다. [FR-C-09, FR-C-10]"""
    cutoff = datetime.now(KST) - timedelta(days=MAX_AGE_DAYS)
    fresh = [item for item in items if parse_published(item.get("published_at", "")) >= cutoff]
    fresh.sort(key=lambda item: parse_published(item.get("published_at", "")), reverse=True)
    return fresh[:MAX_ITEMS]


def save(path: Path, keywords: list[str], items: list[dict]) -> bool:
    """내용이 실제로 바뀐 경우에만 고정된 형식으로 저장한다. [FR-D-01~05]

    `generated_at`을 매번 새로 쓰면 기사 목록이 그대로여도 파일이 달라져
    빈 커밋 방지(FR-D-05)가 무력화된다. 그래서 시각을 넣기 전에 기사 목록과
    키워드를 기존 파일과 먼저 비교하고, 같으면 파일에 손대지 않는다.
    반환값은 파일을 새로 썼는지 여부다.
    """
    payload_items = [
        {
            "id": item["id"],
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "source": item.get("source", ""),
            "published_at": item.get("published_at", ""),
            "keywords": item.get("keywords", []),
        }
        for item in items
    ]

    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as handle:
                previous = json.load(handle)
        except (json.JSONDecodeError, OSError):
            previous = None

        if (
            isinstance(previous, dict)
            and previous.get("keywords") == keywords
            and previous.get("items") == payload_items
        ):
            return False

    payload = {
        "generated_at": datetime.now(KST).replace(microsecond=0).isoformat(),
        "keywords": keywords,
        "count": len(payload_items),
        "items": payload_items,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return True


def load_keywords(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    keywords = [str(k).strip() for k in data.get("keywords", []) if str(k).strip()]
    if not keywords:
        raise ValueError(f"{path} 에 수집할 키워드가 없다")
    return list(dict.fromkeys(keywords))


def export_count(count: int) -> None:
    """워크플로가 커밋 메시지에 쓸 수 있도록 항목 수를 내보낸다. [FR-A-06]"""
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as handle:
        handle.write(f"count={count}\n")


def main() -> int:
    keywords = load_keywords(KEYWORDS_PATH)
    log(f"키워드 {len(keywords)}개 수집 시작: {', '.join(keywords)}")

    incoming, failures = collect(keywords)

    if failures == len(keywords):
        log("[error] 모든 키워드 수집에 실패했다. 기존 데이터를 유지하고 종료한다.")
        return 1  # [FR-C-12]

    existing = load_existing(OUTPUT_PATH)
    merged = merge_items(existing, incoming)          # [FR-C-07] 링크 기준
    deduped = dedupe_by_title(merged)                 # [FR-C-14] 제목 기준
    final = prune(deduped)                            # [FR-C-09, FR-C-10]
    written = save(OUTPUT_PATH, keywords, final)      # [FR-D-05]

    log(
        f"{'저장 완료' if written else '변화 없음 — 파일 유지'}: "
        f"{OUTPUT_PATH.relative_to(ROOT).as_posix()} "
        f"(기존 {len(existing)}건 + 수집 {len(incoming)}건 → 링크 중복제거 {len(merged)}건 "
        f"→ 제목 중복 {len(merged) - len(deduped)}건 제거 → 최종 {len(final)}건"
        f"{f', 실패 {failures}개 키워드' if failures else ''})"
    )
    export_count(len(final))
    return 0


if __name__ == "__main__":
    sys.exit(main())
