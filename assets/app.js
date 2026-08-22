/* ==========================================================================
   card_news — data/news_link.json 을 읽어 카드 그리드를 그린다.
   외부 의존성 없음. 상태 객체 하나 + render() 하나로 유지한다. (계획서 §5.3)
   ========================================================================== */
(function () {
  'use strict';

  var DATA_URL = 'data/news_link.json';
  var THEME_KEY = 'card-news-theme';
  var THEME_ORDER = ['system', 'light', 'dark'];
  var THEME_LABEL = { system: '시스템 설정', light: '라이트', dark: '다크' };

  /* 샌드 옐로우 팔레트와 어울리는 어스 컬러 hue. (계획서 §5.6) [FR-W-11]
     모래 / 더스티블루 / 테라코타 / 세이지 / 올리브 / 클레이로즈 / 플럼
     앞쪽 5개가 기본 키워드에 배정되도록 따뜻한 색을 먼저 놓고 한색을 섞어 두었다. */
  var EARTH_HUES = [38, 202, 20, 160, 88, 344, 272];

  var state = {
    all: [],
    keywords: [],
    keyword: null,
    query: '',
    generatedAt: '',
    status: 'loading',
    error: ''
  };

  var el = {};
  var searchTimer = null;

  /* ---------------------------------------------------------------- 유틸 */

  /* 키워드 목록 순서로 색을 배정한다. 문자열 해시는 색이 한쪽으로 뭉쳐
     핑크·퍼플만 잔뜩 나오는 일이 생겨서, 순서 기반으로 바꿨다.
     목록에 없는 키워드(과거 데이터 잔여분)만 해시로 폴백한다. */
  function hueFor(keyword) {
    var index = state.keywords.indexOf(keyword);
    if (index !== -1) return EARTH_HUES[index % EARTH_HUES.length];

    var hash = 0;
    for (var i = 0; i < keyword.length; i++) {
      hash = (hash * 31 + keyword.charCodeAt(i)) >>> 0;
    }
    return EARTH_HUES[hash % EARTH_HUES.length];
  }

  function relativeTime(iso) {
    var then = new Date(iso);
    if (isNaN(then.getTime())) return '';

    var seconds = (Date.now() - then.getTime()) / 1000;
    if (seconds < 60) return '방금 전';
    if (seconds < 3600) return Math.floor(seconds / 60) + '분 전';
    if (seconds < 86400) return Math.floor(seconds / 3600) + '시간 전';
    if (seconds < 86400 * 7) return Math.floor(seconds / 86400) + '일 전';
    return then.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' });
  }

  function formatUpdated(iso) {
    var when = new Date(iso);
    if (isNaN(when.getTime())) return '';
    return when.toLocaleString('ko-KR', {
      month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
  }

  /* --------------------------------------------------------------- 테마 */

  function storedTheme() {
    try {
      var saved = localStorage.getItem(THEME_KEY);
      return saved === 'light' || saved === 'dark' ? saved : 'system';
    } catch (e) {
      return 'system';
    }
  }

  function applyTheme(mode) {
    if (mode === 'system') {
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.documentElement.setAttribute('data-theme', mode);
    }

    el.themeToggle.setAttribute('data-mode', mode);
    el.themeToggle.setAttribute('aria-label', '테마: ' + THEME_LABEL[mode] + ' — 눌러서 변경');
    el.themeToggle.title = '테마: ' + THEME_LABEL[mode];

    try {
      if (mode === 'system') localStorage.removeItem(THEME_KEY);
      else localStorage.setItem(THEME_KEY, mode);
    } catch (e) { /* 저장소가 막혀 있어도 이번 세션 전환은 동작한다 */ }
  }

  function cycleTheme() {
    var next = THEME_ORDER[(THEME_ORDER.indexOf(storedTheme()) + 1) % THEME_ORDER.length];
    applyTheme(next);
  }

  /* ----------------------------------------------------------- URL 동기화 */

  function readUrl() {
    var params = new URLSearchParams(location.search);
    state.keyword = params.get('k') || null;
    state.query = params.get('q') || '';
  }

  function syncUrl() {
    var params = new URLSearchParams();
    if (state.keyword) params.set('k', state.keyword);
    if (state.query) params.set('q', state.query);

    var qs = params.toString();
    history.replaceState(null, '', qs ? '?' + qs : location.pathname);
  }

  /* ------------------------------------------------------------- 데이터 */

  function loadNews() {
    // 갱신 직후 캐시된 구버전이 뜨지 않도록 한다. [FR-W-13]
    fetch(DATA_URL + '?t=' + Date.now(), { cache: 'no-store' })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        state.all = Array.isArray(data.items) ? data.items : [];
        state.keywords = Array.isArray(data.keywords) ? data.keywords : [];
        state.generatedAt = data.generated_at || '';
        state.status = 'ready';

        // URL로 들어온 키워드가 현재 목록에 없으면 무시한다.
        if (state.keyword && state.keywords.indexOf(state.keyword) === -1) {
          state.keyword = null;
        }

        renderUpdated();
        renderChips();
        render();
      })
      .catch(function (err) {
        state.status = 'error';
        state.error = String(err && err.message ? err.message : err);
        render();
      });
  }

  /* --------------------------------------------------------------- 필터 */

  function matches(item) {
    if (state.keyword && (item.keywords || []).indexOf(state.keyword) === -1) return false;
    if (!state.query) return true;

    var haystack = ((item.title || '') + ' ' + (item.source || '')).toLowerCase();
    return haystack.indexOf(state.query.toLowerCase()) !== -1;
  }

  function countFor(keyword) {
    var total = 0;
    for (var i = 0; i < state.all.length; i++) {
      if ((state.all[i].keywords || []).indexOf(keyword) !== -1) total++;
    }
    return total;
  }

  /* --------------------------------------------------------------- 렌더 */

  function renderUpdated() {
    var when = formatUpdated(state.generatedAt);
    el.updated.textContent = when ? when + ' 기준' : '갱신 시각 정보 없음';
  }

  function makeChip(label, value, count) {
    var chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip';
    chip.setAttribute('aria-pressed', String(state.keyword === value));
    if (value !== null) chip.style.setProperty('--kw-h', String(hueFor(value)));

    var text = document.createElement('span');
    text.textContent = label;
    chip.appendChild(text);

    var num = document.createElement('span');
    num.className = 'chip-count';
    num.textContent = count;
    chip.appendChild(num);

    chip.addEventListener('click', function () {
      state.keyword = state.keyword === value ? null : value;
      syncUrl();
      renderChips();
      render();
    });

    return chip;
  }

  function renderChips() {
    var fragment = document.createDocumentFragment();
    fragment.appendChild(makeChip('전체', null, state.all.length));

    state.keywords.forEach(function (keyword) {
      fragment.appendChild(makeChip(keyword, keyword, countFor(keyword)));
    });

    el.chips.replaceChildren(fragment);
  }

  function renderCard(item) {
    var keywords = item.keywords || [];
    var card = document.createElement('a');
    card.className = 'card';
    card.href = item.link;
    card.target = '_blank';
    card.rel = 'noopener noreferrer';
    card.style.setProperty('--kw-h', String(hueFor(keywords[0] || '')));

    if (keywords.length) {
      var badges = document.createElement('div');
      badges.className = 'card-badges';
      keywords.forEach(function (keyword) {
        var badge = document.createElement('span');
        badge.className = 'badge';
        badge.style.setProperty('--kw-h', String(hueFor(keyword)));
        badge.textContent = keyword;
        badges.appendChild(badge);
      });
      card.appendChild(badges);
    }

    var title = document.createElement('h2');
    title.className = 'card-title';
    title.textContent = item.title || '(제목 없음)';
    card.appendChild(title);

    var meta = document.createElement('p');
    meta.className = 'card-meta';

    var source = document.createElement('span');
    source.className = 'card-source';
    source.textContent = item.source || '출처 미상';
    meta.appendChild(source);

    var relative = relativeTime(item.published_at);
    if (relative) {
      var sep = document.createElement('span');
      sep.className = 'sep';
      sep.textContent = '·';
      meta.appendChild(sep);

      var time = document.createElement('time');
      time.dateTime = item.published_at;
      time.textContent = relative;
      meta.appendChild(time);
    }

    card.appendChild(meta);
    return card;
  }

  function setStatus(message, isError) {
    el.status.textContent = message;
    el.status.classList.toggle('is-error', !!isError);
    el.status.hidden = !message;
  }

  function render() {
    if (state.status === 'loading') {
      setStatus('뉴스를 불러오는 중입니다…', false);
      el.grid.replaceChildren();
      el.resultCount.textContent = '';
      return;
    }

    if (state.status === 'error') {
      setStatus('뉴스를 불러오지 못했습니다. (' + state.error + ') 잠시 후 새로고침해 주세요.', true);
      el.grid.replaceChildren();
      el.resultCount.textContent = '';
      return;
    }

    var visible = state.all.filter(matches);

    // [FR-W-16]
    el.resultCount.textContent = visible.length === state.all.length
      ? '전체 ' + state.all.length + '건'
      : visible.length + '건 / 전체 ' + state.all.length + '건';

    if (!visible.length) {
      setStatus('조건에 맞는 기사가 없습니다. 키워드나 검색어를 바꿔 보세요.', false);
      el.grid.replaceChildren();
      return;
    }

    setStatus('', false);

    var fragment = document.createDocumentFragment();
    visible.forEach(function (item) {
      fragment.appendChild(renderCard(item));
    });
    el.grid.replaceChildren(fragment);
  }

  /* ---------------------------------------------------------------- 초기화 */

  function init() {
    el.updated = document.getElementById('updated');
    el.themeToggle = document.getElementById('theme-toggle');
    el.chips = document.getElementById('chips');
    el.search = document.getElementById('search');
    el.status = document.getElementById('status');
    el.grid = document.getElementById('grid');
    el.resultCount = document.getElementById('result-count');

    applyTheme(storedTheme());
    el.themeToggle.addEventListener('click', cycleTheme);

    readUrl();
    el.search.value = state.query;

    el.search.addEventListener('input', function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        state.query = el.search.value.trim();
        syncUrl();
        render();
      }, 150);
    });

    loadNews();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
