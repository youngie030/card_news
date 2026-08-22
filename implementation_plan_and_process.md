# card_news 구현 계획 및 진행 상황

- 문서 버전: v1.3
- 최종 수정일: 2026-08-22
- 대응 요구사항: `requirements.md` v1.2

---

## 1. 기술스택

| 레이어 | 기술 | 버전/비고 |
|---|---|---|
| 수집 스크립트 | Python | 3.11 (Actions `setup-python`으로 고정) |
| RSS 파싱 | `feedparser` | 유일한 외부 의존성. `requirements.txt`로 고정 |
| 데이터 포맷 | JSON | `data/news_link.json`, UTF-8 / `ensure_ascii=False` |
| 프론트엔드 | HTML5 + CSS3 + Vanilla JS (ES2020) | 빌드 단계 없음, 외부 의존성 없음 |
| 레이아웃 | CSS Grid (`auto-fill` + `minmax`) | 미디어쿼리 없이 반응형 |
| 테마 | CSS Custom Properties + `prefers-color-scheme` | 라이트/다크 자동 |
| 자동화 | GitHub Actions | `schedule` cron + `workflow_dispatch` |
| 호스팅 | GitHub Pages | `main` 브랜치 루트, 빌드 워크플로 없음 |

**의도적으로 배제한 것**: Node/npm, 번들러, CSS 프레임워크, 차트/아이콘 라이브러리, CDN. 카드 그리드 한 화면에 빌드 파이프라인을 얹을 이유가 없고, 의존성이 없으면 Pages 배포가 커밋 즉시 반영된다.

---

## 2. 프로젝트 구조

```
card_news/
├─ index.html                     # 페이지 셸 (헤더 / 필터 / 그리드 / 상태 UI)
├─ .nojekyll                      # Pages의 Jekyll 처리 비활성화        [FR-P-03]
├─ assets/
│  ├─ style.css                   # 전체 스타일, 테마 토큰, 카드/그리드
│  └─ app.js                      # JSON fetch → 상태 관리 → 렌더 → 필터
├─ data/
│  └─ news_link.json              # 수집 결과 (Actions가 커밋)          [FR-D-01]
├─ config/
│  └─ keywords.json               # 수집 키워드 목록 (사용자가 편집)     [§2.1]
├─ scripts/
│  ├─ fetch_news.py               # 수집·병합·정리·저장 진입점
│  └─ requirements.txt            # feedparser 핀 고정
├─ .github/workflows/
│  └─ update-news.yml             # 매시간 수집 + 변경 시에만 커밋
├─ requirements.md                # 요구사항 명세서
├─ implementation_plan_and_process.md
├─ README.md                      # 프로젝트 소개, 로컬 실행, 키워드 변경법
└─ .gitignore                     # access.json 등 크리덴셜 차단 (기존)
```

`CLAUDE.md`, `USERRULE.md`, `access.json`은 커밋 대상이 아니다. [NFR-03, NFR-04]

---

## 3. 요구사항 및 구현 매핑 테이블

| 요구사항 ID | 구현 위치 | 구현 방식 |
|---|---|---|
| FR-C-01 | `scripts/fetch_news.py::build_feed_url` | `news.google.com/rss/search?q={quote(kw)}&hl=ko&gl=KR&ceid=KR:ko` |
| FR-C-02 | `fetch_news.py::parse_entry` | `feedparser` 엔트리에서 `title`/`link`/`source.title`/`published_parsed` 추출 |
| FR-C-03 | `fetch_news.py::strip_source_suffix` | 제목 끝의 ` - {매체명}`을 반복 제거(while). 매체명을 모를 때만 정규식 폴백 |
| FR-C-04 | (구현 없음 — 의도적 제외) | `description`을 읽지 않는다. §5.8 참조 |
| FR-C-05 | `fetch_news.py::to_kst_iso` | `published_parsed`(UTC) → `timezone(timedelta(hours=9))` → `isoformat()` |
| FR-C-06 | `fetch_news.py::normalize_link`, `make_id` | `utm_*`/`fbclid` 등 추적 파라미터 제거 후 `sha1(link).hexdigest()` |
| FR-C-07 | `fetch_news.py::merge_items` | `dict[id]` 누적, 충돌 시 `keywords` 합집합 |
| FR-C-08 | `fetch_news.py::load_existing` | 기존 JSON 로드 후 신규와 병합 (파일 없으면 빈 목록) |
| FR-C-09 | `fetch_news.py::prune` | `published_at < now - 7d` 제거 |
| FR-C-10 | `fetch_news.py::prune` | 정렬 후 상위 `MAX_ITEMS=300`만 유지 |
| FR-C-11 | `fetch_news.py::main` | 키워드 루프를 `try/except`로 감싸고 실패 카운트 집계 |
| FR-C-12 | `fetch_news.py::main` | 전량 실패 시 저장 생략 + `sys.exit(1)` |
| FR-C-13 | `fetch_news.py::fetch_feed` | `urllib` 요청에 UA 헤더 + `timeout=15`, 루프 말미 `time.sleep(1)` |
| FR-D-01~04 | `fetch_news.py::save` | `json.dump(..., ensure_ascii=False, indent=2)`, `encoding="utf-8"`, `newline="\n"` |
| FR-D-05 | `update-news.yml` | `git diff --quiet -- data/news_link.json`로 변경 여부 판정 |
| FR-W-01 | `app.js::loadNews` | `fetch('data/news_link.json?t=' + Date.now())` |
| FR-W-02 | `app.js::renderCard` | 제목(최대 4줄)/매체/상대시각/키워드 배지 조립 |
| FR-W-03 | `app.js::renderCard` | 카드 루트를 `<a target="_blank" rel="noopener noreferrer">`로 생성 |
| FR-W-04 | `app.js::renderChips`, `state.keyword` | `data.keywords` + "전체" 칩, 클릭 시 상태 갱신 후 재렌더 |
| FR-W-05 | `app.js::applyFilters` | `title+source`를 소문자 정규화 후 `includes` |
| FR-W-06 | `app.js::applyFilters` | 키워드 조건 && 검색 조건 |
| FR-W-07 | `app.js::renderMeta` | `generated_at`을 `toLocaleString('ko-KR')`로 표시 |
| FR-W-08 | `index.html` 상태 노드 + `app.js::setStatus` | `loading` / `error` / `empty` 세 상태 전환 |
| FR-W-09 | `style.css` | `grid-template-columns: repeat(auto-fill, minmax(320px, 1fr))` |
| FR-W-10 | `style.css` | `:root` 토큰 + `@media (prefers-color-scheme: dark)` 재정의 |
| FR-W-11 | `app.js::keywordHue` + `style.css` | 키워드 문자열 해시 → `EARTH_HUES` 7종 중 고정 배정, CSS 변수 `--kw-h`로 전달 (§5.6) |
| FR-W-12 | `app.js::syncUrl`, `readUrl` | `URLSearchParams` + `history.replaceState` |
| FR-W-13 | `app.js::loadNews` | fetch URL에 타임스탬프 쿼리 부착 |
| FR-W-14 | `app.js::cycleTheme`, `applyTheme` | `system→light→dark` 순환, `<html data-theme>` + `localStorage['card-news-theme']` (§5.7) |
| FR-W-15 | `index.html` `<head>` 인라인 스크립트 | CSS 파싱 전 `data-theme` 선반영으로 FOUC 차단 |
| FR-W-16 | `app.js::render` | `#result-count`에 건수 출력, `aria-live="polite"` |
| FR-W-17 | `style.css` `:root` 토큰 | 샌드 옐로우 웜 팔레트 (§5.5) |
| FR-W-18 | `style.css` `.grid`, `.card` | `minmax(280px, 1fr)` / `gap: 14px` / 카드 패딩 `16px 18px` / 제목 행간 1.5 |
| FR-A-01 | `update-news.yml` | `schedule: - cron: "0 * * * *"` |
| FR-A-02 | `update-news.yml` | `workflow_dispatch:` |
| FR-A-03 | `update-news.yml` | diff 있을 때만 `git commit && git push` |
| FR-A-04 | `update-news.yml` | `user.name=github-actions[bot]`, `user.email=41898282+github-actions[bot]@users.noreply.github.com` |
| FR-A-05 | `update-news.yml` | `permissions: contents: write` |
| FR-A-06 | `update-news.yml` | 항목 수를 스크립트 stdout에서 읽어 커밋 메시지에 삽입 |
| FR-A-07 | `update-news.yml` | 스크립트 비정상 종료 시 이후 스텝 미실행 (기본 fail-fast) |
| FR-A-08 | `update-news.yml` | `concurrency: group: update-news, cancel-in-progress: false` |
| FR-P-01~03 | 저장소 루트 배치 + `.nojekyll` | Pages 설정은 Deploy from branch / main / `(root)` |
| FR-P-04 | (사용자 수행) | GitHub Settings → General → Change visibility → Public |
| NFR-01 | 전 파일 | 외부 URL 참조 없음, 시스템 폰트 스택 사용 |
| NFR-02 | 전 파일 | Python은 `encoding="utf-8"` 명시, HTML은 `<meta charset="utf-8">` |
| NFR-03/04 | `.gitignore` + 커밋 전 검증 | `git check-ignore access.json` 확인 |
| NFR-05 | `app.js::render` | `DocumentFragment` 1회 삽입, 재렌더 시 전체 교체 |
| NFR-06 | `index.html`/`style.css` | 시맨틱 태그, `:focus-visible` 아웃라인, 칩은 `<button>` |
| NFR-07 | `style.css` | 라이트/다크 각각 대비비 4.5:1 이상 색상 토큰 |
| NFR-08 | `scripts/requirements.txt` | `feedparser`만 기재 |
| NFR-09 | `app.js::renderCard` | 카드에 매체명 항상 노출, 링크는 원문으로 |

---

## 4. 구현 단계 (Phase)

### Phase 0 — 문서화 및 기반 설정
요구사항·계획 문서 확정, 디렉터리 골격과 `config/keywords.json`, `.nojekyll` 생성.
산출물: `requirements.md`, `implementation_plan_and_process.md`, `config/keywords.json`, `.nojekyll`

### Phase 1 — 수집 스크립트
`scripts/fetch_news.py`와 `requirements.txt` 작성. 로컬에서 실행하여 `data/news_link.json` 최초 생성 및 스키마 검증. 두 번 실행하여 누적·중복제거 동작 확인.
검증 대상: FR-C-01~13, FR-D-01~04, 완료기준 1~3

### Phase 2 — 정적 페이지
`index.html`, `assets/style.css`, `assets/app.js` 작성. Phase 1이 만든 실제 데이터로 렌더링 확인. 로컬 서버(`python -m http.server`)로 구동 — `file://`은 fetch가 CORS로 막히므로 반드시 HTTP로 확인한다.
검증 대상: FR-W-01~13, NFR-05~07, 완료기준 4~6

### Phase 3 — 배포
`README.md` 갱신 → `.gitignore` 보강 → 최초 커밋·푸시 → 저장소 public 전환(사용자 수행) → Pages 활성화 → 실제 URL 동작 확인.
검증 대상: FR-P-01~04, 완료기준 9~10

### Phase 4 — 자동화 및 마무리
`.github/workflows/update-news.yml` 작성 → 수동 실행으로 커밋 동작 확인 → 무변경 재실행으로 빈 커밋 미발생 확인 → 배포 URL에 갱신분이 반영되는지 확인.
검증 대상: FR-A-01~08, 완료기준 7~8

> **배포를 자동화보다 먼저 하는 이유** (v1.3에서 순서 교체)
> Actions 워크플로는 저장소에 푸시된 뒤에야 수동 실행으로 검증할 수 있다. 자동화를 먼저 만들면 검증 없이 다음 단계로 넘어가야 하므로, 배포를 선행해 실행 환경을 확보한 뒤 자동화를 붙인다.

> Git 명령은 USERRULE에 따라 임의 실행하지 않고, 순서를 안내한 뒤 사용자의 "진행해" 응답 후에만 수행한다.

---

## 5. 핵심 디자인

### 5.1 데이터 흐름

```
config/keywords.json
        │
        ▼
[GitHub Actions · 매시간 cron]
        │
        ▼
scripts/fetch_news.py
   ├─ 키워드별 구글뉴스 RSS 조회 (실패 격리)
   ├─ 파싱 → 정규화 → id 부여
   ├─ 기존 data/news_link.json 로드 후 병합 (id 기준 dedup)
   ├─ 7일 초과 / 300개 초과 정리
   └─ 최신순 정렬 후 저장
        │
        ▼
data/news_link.json ──(변경 있을 때만 커밋·푸시)──▶ main 브랜치
        │
        ▼
GitHub Pages (정적 서빙)
        │
        ▼
index.html → app.js: fetch → 필터 적용 → 카드 그리드 렌더
        │
        ▼
카드 클릭 → 새 탭으로 원문 기사
```

### 5.2 수집 스크립트 설계 원칙

- **멱등하지 않고 누적적이다.** 매 실행은 기존 데이터에 더하는 연산이며, 삭제는 오직 만료(7일)·상한(300) 규칙으로만 일어난다. 일시적 RSS 장애가 데이터 유실로 이어지지 않는다.
- **부분 실패를 허용한다.** 키워드 5개 중 1개가 실패해도 나머지 4개 결과는 저장된다. 전량 실패일 때만 저장을 건너뛰고 실패로 종료한다.
- **출력이 안정적이다.** 정렬 순서 고정 + 들여쓰기 고정 + `ensure_ascii=False`로, 실제 내용 변화가 있을 때만 diff가 발생한다. 매시간 실행에서 커밋 노이즈를 줄이는 핵심 장치다.

### 5.3 프론트엔드 상태 모델

단일 상태 객체 하나와 순수 렌더 함수 한 개로 유지한다. 프레임워크 없이도 예측 가능한 구조를 만드는 최소 설계다.

```js
const state = {
  all: [],        // JSON에서 읽은 전체 items
  keyword: null,  // 선택된 키워드 (null = 전체)
  query: '',      // 검색어
  status: 'loading' // 'loading' | 'ready' | 'error'
};
// 상태 변경 → render() 전체 재실행 → DocumentFragment 1회 삽입
```

### 5.4 카드 시각 설계 (텍스트 중심)

이미지도 요약도 없으므로, **제목 하나가 카드의 전부**다. 제목에 충분한 크기와 여백을 주고 키워드 색상으로 카드를 구분한다.

```
┌────────────────────────────────┐
│ ▍생성형 AI                      │  ← 좌측 4px 액센트 바 + 키워드 배지
│                                │
│ 오픈AI, 차세대 추론 모델         │  ← 제목: 1.15rem / 650 / 1.45 행간
│ 공개…수학 벤치마크 1위 탈환      │     최대 4줄 말줄임 (주 시각 요소)
│                                │
│ 연합뉴스 · 2시간 전             │  ← 메타: 0.78rem / 흐린색, 카드 하단 고정
└────────────────────────────────┘
```

- 키워드별 hue를 문자열 해시로 고정 배정하여, 키워드가 추가돼도 코드 수정 없이 색이 배정된다.
- 카드 전체가 링크이므로 `:hover`에서 살짝 떠오르고(`translateY(-2px)`), `:focus-visible`에서 뚜렷한 아웃라인이 나타난다.
- 제목은 `-webkit-line-clamp: 4`로 말줄임하고, 메타 줄은 `margin-top: auto`로 카드 하단에 붙여 제목 길이가 달라도 그리드 정렬이 흐트러지지 않게 한다.

### 5.5 색상 토큰 — 샌드 옐로우 웜 팔레트 [FR-W-17]

회색을 쓰지 않는 것이 이 팔레트의 규칙이다. 무채색으로 보이는 자리에도 노랑 계열 hue를 낮은 채도로 섞어, 화면 전체가 모래·크림 톤으로 읽히게 한다. 다크 테마도 청회색이 아니라 **웜 차콜**을 기준으로 삼는다.

| 토큰 | 라이트 | 다크 | 용도 |
|---|---|---|---|
| `--bg` | `#f6f1e4` | `#14120d` | 페이지 배경 (모래 / 웜 차콜) |
| `--surface` | `#fffdf7` | `#1e1b14` | 카드·헤더 배경 |
| `--surface-raised` | `#fffefb` | `#262218` | 카드 hover |
| `--border` | `#e7dcc4` | `#332d21` | 테두리 |
| `--text` | `#2a2419` | `#f2ebdb` | 제목 |
| `--text-muted` | `#6a5f4c` | `#b5a893` | 보조 텍스트 |
| `--text-faint` | `#7e7159` | `#8d8271` | 메타 (매체·시각) |
| `--accent` | `#93630a` | `#e6b862` | 링크·선택 칩·포커스 |
| `--accent-soft` | `#f0e3c4` | `#3a3120` | 선택 칩 배경 |

대비비 실측(본문 기준, [NFR-07] 4.5:1 이상):

| 조합 | 라이트 | 다크 |
|---|---|---|
| `--text` / `--surface` | 15.2 : 1 | 14.6 : 1 |
| `--text-muted` / `--surface` | 6.2 : 1 | 7.3 : 1 |
| `--text-faint` / `--surface` | 4.8 : 1 | 4.6 : 1 |
| `--accent` / `--surface` | 5.2 : 1 | 9.3 : 1 |

### 5.6 키워드 색상 배정 [FR-W-11]

무지개 hue를 자유롭게 쓰면 샌드 톤과 충돌한다. 대신 **웜 팔레트와 어울리는 어스 컬러 hue 7종**을 정해 두고 그중 하나를 배정한다.

```js
const EARTH_HUES = [38, 202, 20, 160, 88, 344, 272];
//                 모래 더스티블루 테라코타 세이지 올리브 클레이로즈 플럼
```

배정 기준은 **`config/keywords.json`의 키워드 순서**다. 처음에는 키워드 문자열 해시를 썼으나, 실제로 그려 보니 5개 키워드 중 3개가 핑크·퍼플로 몰려 샌드 배경과 정면으로 충돌했다. 해시는 균등 분포를 보장하지 않는다. 순서 기반으로 바꾸면 키워드 7개까지 색이 절대 겹치지 않고, 따뜻한 색과 찬 색이 번갈아 나온다. 목록에 없는 키워드(과거 데이터에 남은 것)만 해시로 폴백한다.

| 용도 | 라이트 | 다크 |
|---|---|---|
| 배지 글자 | `hsl(h, 60%, 28%)` | `hsl(h, 58%, 72%)` |
| 배지 배경 | `hsl(h, 48%, 90%)` | `hsl(h, 25%, 16%)` |
| 카드 액센트 바 | `hsl(h, 52%, 48%)` | `hsl(h, 45%, 55%)` |

### 5.7 테마 전환 [FR-W-14, FR-W-15]

`시스템 → 라이트 → 다크 → 시스템` 3단 순환. 상태는 `<html data-theme>`와 `localStorage['card-news-theme']`에 담는다.

```css
:root { /* 라이트 토큰 (기본값) */ }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { /* 다크 토큰 */ }
}
:root[data-theme="dark"] { /* 다크 토큰 — 수동 선택이 항상 이긴다 */ }
```

- 다크 토큰을 두 번 정의하는 것은 의도적이다. 미디어쿼리 안에만 두면 수동 선택이 시스템 설정을 이길 수 없다.
- `<head>`의 인라인 스크립트가 CSS 파싱 전에 `data-theme`를 세팅하므로, 다크 사용자가 라이트 화면을 잠깐 보는 깜빡임이 발생하지 않는다. [FR-W-15]

### 5.8 요약을 저장하지 않는 이유

Phase 1에서 실제 피드를 받아 확인한 결과, 구글뉴스 검색 RSS의 `description`은 기사 요약이 아니라 **관련 기사 링크 목록**이었다.

```html
<ol><li><a href="...">기사 제목</a>&nbsp;&nbsp;<font>매체명</font></li> ... </ol>
```

태그를 벗기면 `제목 매체명 제목 매체명 ...`이 되어 카드에 제목이 두 번 나오는 형태가 된다. 요약을 얻으려면 기사 원문 페이지를 개별 호출해 `og:description`을 파싱해야 하는데, 1회 실행에 500여 건을 요청하게 되어 매시간 실행과 맞지 않고 언론사 차단 위험도 생긴다. 따라서 요약은 스키마에서 제외하고 제목 중심 카드로 확정했다. [FR-C-04]

---

## 6. 구현 진행 상황

### Phase 0 — 문서화 및 기반 설정
- [x] `requirements.md` 작성
- [x] `implementation_plan_and_process.md` 작성
- [x] `config/keywords.json` 생성 (초기 5개 키워드)
- [x] `.nojekyll` 생성
- [x] `data/` 디렉터리 준비

### Phase 1 — 수집 스크립트
- [x] `scripts/requirements.txt` 작성 (`feedparser==6.0.11`)
- [x] `scripts/fetch_news.py` — RSS 조회 및 파싱 (FR-C-01~05)
- [x] `scripts/fetch_news.py` — 링크 정규화 및 id 부여 (FR-C-06)
- [x] `scripts/fetch_news.py` — 병합·중복제거 (FR-C-07~08)
- [x] `scripts/fetch_news.py` — 만료·상한 정리 (FR-C-09~10)
- [x] `scripts/fetch_news.py` — 실패 격리 및 종료 코드 (FR-C-11~13)
- [x] `scripts/fetch_news.py` — JSON 저장 (FR-D-01~04)
- [x] 로컬 1회 실행 → 스키마 검증 (완료기준 1~2)
- [x] 로컬 2회 실행 → 누적·중복제거 검증 (완료기준 3)

> **Phase 1 실측 결과 (2026-08-22)**
> 5개 키워드에서 515건 수집 → 중복제거·정렬 후 상한 300건 저장, 파일 크기 160KB.
> id 중복 0건, 매체명 접미사 잔존 0건, 제목·매체 공백 0건, 최신순 정렬 정상.
> 2회차 실행에서 `기존 300건 + 수집 515건 → 최종 300건`으로 병합 동작 확인.
> 다중 키워드에 걸린 기사 2건이 하나로 병합됨.

### Phase 2 — 정적 페이지
- [x] `index.html` 셸 및 상태 노드 (FR-W-08)
- [x] `index.html` — FOUC 방지 인라인 테마 스크립트 (FR-W-15)
- [x] `assets/style.css` — 샌드 옐로우 웜 토큰 및 그리드 (FR-W-09~10·17~18, NFR-07)
- [x] `assets/style.css` — 카드 시각 설계 (§5.4)
- [x] `assets/app.js` — 데이터 로드 및 렌더 (FR-W-01~03)
- [x] `assets/app.js` — 키워드 칩 및 검색 필터 (FR-W-04~06, 검색 대상은 제목·매체명)
- [x] `assets/app.js` — 갱신 시각·상태 UI·결과 건수 (FR-W-07~08·16)
- [x] `assets/app.js` — 키워드 색상·URL 동기화·캐시 무효화 (FR-W-11~13)
- [x] `assets/app.js` — 테마 3단 순환 및 저장 (FR-W-14)
- [x] 로컬 HTTP 서버로 동작 확인 (완료기준 4~5)
- [x] 375px / 820px / 1440px 반응형 확인 (완료기준 6)

> **Phase 2 검증 결과 (2026-08-22)**
> Edge를 CDP로 구동해 뷰포트·테마를 에뮬레이션하여 확인했다.
> - 가로 오버플로: 375 / 820 / 1440 전부 `scrollWidth == clientWidth`, 넘치는 요소 0개
> - 그리드 컬럼: 375px → 1열, 820px → 2열, 1440px → 4열
> - 인터랙션 자동 검증 18항목 전부 통과 (테마 3단 순환·재방문 유지, 키워드 필터 건수 일치, 키워드+검색 AND, 결과 없음 상태, 카드 링크 속성, URL 진입 시 필터 복원)
> - 키워드 색상이 해시 배정에서 핑크·퍼플로 뭉치는 문제를 발견해 순서 기반 배정으로 교체 (§5.6)

### Phase 3 — 배포
- [x] `README.md` 갱신 (소개 / 로컬 실행 / 키워드 변경법)
- [x] `.gitignore`에 AI 지시문 파일 추가 (NFR-04)
- [ ] 커밋 제외 대상 점검: `access.json`·`CLAUDE.md`·`USERRULE.md` (완료기준 10, NFR-03~04)
- [ ] 최초 커밋 및 `main` 푸시
- [ ] 저장소 public 전환 (사용자 직접 수행, FR-P-04)
- [ ] Pages 활성화: Deploy from branch / `main` / `(root)`
- [ ] 배포 URL에서 동작 확인 (완료기준 9)

### Phase 4 — 자동화 및 마무리
- [ ] `.github/workflows/update-news.yml` 작성 (FR-A-01~08)
- [ ] 수동 실행으로 커밋 확인 (완료기준 7)
- [ ] 무변경 재실행으로 빈 커밋 미발생 확인 (완료기준 8)
- [ ] 봇 커밋 후 Pages가 재배포되는지 확인 (§6 주의 참조)

> **주의 — 봇 커밋과 Pages 재배포**
> 브랜치 기반 Pages는 `main`에 푸시가 들어오면 `pages-build-deployment`가 자동으로 돈다. 다만 `GITHUB_TOKEN`으로 만든 푸시는 일반 워크플로를 트리거하지 않는 규칙이 있어, 봇 커밋에서도 재배포가 도는지 Phase 4에서 실제로 확인해야 한다. 만약 돌지 않으면 Pages 소스를 "GitHub Actions"로 바꾸고 `actions/deploy-pages`를 워크플로에 붙이는 방식으로 전환한다. (FR-P-01 변경 필요)

---

## 7. 기능 업데이트 제안

향후 검토 가능한 항목. 현재 범위에는 포함하지 않는다.

| 제안 | 내용 | 예상 난이도 |
|---|---|---|
| 원문 URL 해석 | 구글뉴스 리디렉트 URL을 실제 언론사 URL로 풀어 저장. 매체별 도메인 표시와 필터링이 가능해진다 | 중 |
| 매체별 필터 | 키워드 칩과 별개로 언론사 칩을 추가 | 하 |
| 즐겨찾기 | `localStorage`에 기사 id를 저장해 "저장한 기사" 탭 제공. 서버 없이 가능 | 하 |
| RSS 피드 제공 | 수집 결과를 `feed.xml`로도 내보내 RSS 리더에서 구독 | 하 |
| 일간 다이제스트 | 하루 단위 요약 페이지를 별도 생성해 아카이브로 축적 | 중 |
| og:image 하이브리드 | 이미지가 있는 기사만 썸네일 카드로 표시하고 나머지는 텍스트 카드 유지 | 중 |
| 키워드 트렌드 | 키워드별 일간 기사 수를 집계해 간단한 추이 그래프 표시 | 중 |
| AI 요약 | Claude API로 기사 요약을 재작성. API 키를 Secrets에 등록해야 하며 비용 발생 | 중 |
| 다국어 소스 | `hl=en&gl=US` 피드를 추가해 해외 뉴스 병행 수집 | 하 |
| 블로그 매체 제외 | 구글뉴스는 `Naver Blog` 등 개인 블로그도 섞어 준다. 제외 매체 목록을 `config`로 두고 필터링 | 하 |
| 동일 제목 중복 제거 | 통신사 기사를 여러 매체가 그대로 싣는 경우 링크가 달라 별개 항목으로 남는다. 정규화한 제목으로 2차 중복제거를 하고 가장 먼저 발행된 매체만 남기는 방안 (§6 Phase 2 관찰) | 하 |

---

## 8. 변경 이력

| 버전 | 일자 | 내용 |
|---|---|---|
| v1.0 | 2026-08-22 | 초기 구현 계획 수립. Phase 0 문서화 완료 |
| v1.3 | 2026-08-22 | 사용자 요청으로 Phase 3(자동화)과 Phase 4(배포) 순서 교체 — 배포를 선행해야 Actions를 실제로 검증할 수 있다. `README.md` 작성, `.gitignore`에 AI 지시문 파일 추가. 봇 커밋 시 Pages 재배포 확인 항목 추가 |
| v1.2 | 2026-08-22 | Phase 2 구현 완료. requirements.md v1.2에 맞춰 샌드 옐로우 팔레트(§5.5)·키워드 색상 배정(§5.6)·테마 전환(§5.7) 설계 추가, 매핑 테이블에 FR-W-14~18 반영, Phase 2 검증 결과 기록, 동일 제목 중복 제거 제안 추가 |
| v1.1 | 2026-08-22 | Phase 0·1 구현 완료. requirements.md v1.1(요약 필드 제거)에 맞춰 매핑 테이블·카드 설계(§5.4) 갱신, §5.6 요약 제외 근거 추가, 기능 업데이트 제안에 블로그 매체 제외 항목 추가 |
