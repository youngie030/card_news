# card_news

키워드별 최신 뉴스를 카드로 모아 보여주고, 카드를 누르면 원문 기사로 이동하는 정적 페이지입니다.

서버가 없습니다. GitHub Actions가 매시간 구글뉴스 RSS를 훑어 `data/news_link.json`을 갱신·커밋하고, GitHub Pages가 그 JSON을 읽는 정적 페이지를 서빙합니다.

기사 제목·링크·매체명·발행시각만 저장하며 본문은 수집하지 않습니다. 각 기사의 저작권은 해당 언론사에 있습니다.

## 화면

- 키워드별 카드 그리드 (반응형: 1열 → 2열 → 4열)
- 키워드 칩 필터 + 제목·매체명 검색 (AND 조건)
- 필터 상태가 주소창에 반영되어 링크 공유 가능 (`?k=반도체&q=HBM`)
- 샌드 옐로우 웜 팔레트, 라이트/다크 3단 전환 (시스템 → 라이트 → 다크)
- 외부 CDN·폰트·라이브러리 의존성 없음

## 구조

```
index.html                    페이지 셸
assets/style.css              색상 토큰, 카드·그리드
assets/app.js                 JSON 로드 → 필터 → 렌더
config/keywords.json          수집 키워드 목록
data/news_link.json           수집 결과 (Actions가 갱신)
scripts/fetch_news.py         수집·병합·정리·저장
scripts/requirements.txt      feedparser
.github/workflows/            매시간 갱신 워크플로
```

## 로컬에서 실행하기

`index.html`을 파일로 직접 열면 브라우저가 `fetch`를 CORS로 막습니다. 반드시 HTTP로 띄우세요.

```bash
# 1. 의존성 설치 (최초 1회)
pip install -r scripts/requirements.txt

# 2. 뉴스 수집
python scripts/fetch_news.py

# 3. 로컬 서버
python -m http.server 8765
```

브라우저에서 http://127.0.0.1:8765 로 접속합니다.

## 수집 키워드 바꾸기

`config/keywords.json`만 고치면 됩니다. 코드 수정은 필요 없습니다.

```json
{
  "keywords": ["생성형 AI", "반도체", "금리", "주식시장", "스타트업"]
}
```

키워드별 색상은 이 배열의 **순서**로 정해집니다. 7개까지는 색이 겹치지 않으며, 중간에 키워드를 끼워 넣으면 뒤쪽 키워드의 색이 밀립니다.

## 데이터 규칙

`data/news_link.json`은 실행할 때마다 덮어쓰지 않고 **누적 병합**됩니다. RSS가 일시적으로 죽어도 기존 데이터가 날아가지 않습니다.

- 링크 정규화 후 SHA-1을 `id`로 삼아 중복 제거
- 같은 기사가 여러 키워드에 걸리면 하나로 합치고 `keywords` 배열에 모두 기록
- 발행 후 7일 경과분 삭제, 최대 300건 보관 (`scripts/fetch_news.py`의 `MAX_AGE_DAYS`, `MAX_ITEMS`)
- 키워드 일부가 실패해도 나머지는 저장하며, 전량 실패일 때만 저장을 건너뛰고 종료 코드 1로 끝냄

```jsonc
{
  "generated_at": "2026-08-22T14:00:00+09:00",
  "keywords": ["생성형 AI", "반도체", "금리", "주식시장", "스타트업"],
  "count": 300,
  "items": [
    {
      "id": "9a1f0c…",
      "title": "삼성전자, HBM4 양산 일정 앞당긴다",
      "link": "https://news.google.com/rss/articles/…",
      "source": "연합뉴스",
      "published_at": "2026-08-22T13:41:00+09:00",
      "keywords": ["반도체"]
    }
  ]
}
```

## 자동 갱신

`.github/workflows/update-news.yml`이 매시간(UTC 정각) 실행되며, Actions 탭에서 수동 실행도 가능합니다. 수집 결과가 이전과 완전히 같으면 커밋하지 않습니다.

## 문서

- [`requirements.md`](requirements.md) — 요구사항 명세서
- [`implementation_plan_and_process.md`](implementation_plan_and_process.md) — 구현 계획 및 진행 상황

## 출처

뉴스 메타데이터는 [Google News RSS](https://news.google.com/)에서 가져옵니다.
