/* app.js — 主流程：定位 → 抓圖 → 輪播
 *
 * 定位部分用 geo.js 的 Tracker（濾波做法參考「汽車聲浪」作品）。
 * 有了平滑後的速度與行進方向之後，這裡做兩件事：
 *   1. 移動中把搜尋中心往前方推，先看到即將到達的風景而不是剛開過的
 *   2. 依速度調整重新搜尋的觸發距離 —— 高速公路上要更早換一批，市區則不必
 */

import {
  Tracker, watchPosition, getPositionOnce, attachCompass,
  distanceMeters, bearingDeg, projectAhead,
  compassLabel, formatDistance, formatCoord, reverseGeocode, keepAwake
} from './geo.js';
import { fetchNearby, nearestBaked } from './photos.js';

const $ = (s) => document.querySelector(s);

const el = {
  photoA: $('#photoA'), photoB: $('#photoB'),
  kicker: $('#p-kicker'), title: $('#p-title'), meta: $('#p-meta'),
  body: $('#p-body'), credit: $('#p-credit'), source: $('#p-source'),
  count: $('#p-count'),
  hudDot: $('#hud-dot'), hudCoords: $('#hud-coords'),
  hudPlace: $('#hud-place'), hudMotion: $('#hud-motion'),
  bar: $('#progress i'),
  boot: $('#boot'), bootMsg: $('#boot-msg'), bootBtn: $('#boot-btn'),
  toast: $('#toast'), controls: $('#controls'),
  bootSkip: $('#boot-skip'), btnPlace: $('#btn-place')
};

/* 展示版（Artifact）：內容已 base64 內嵌，完全不連網。
   同一份程式碼兩用 —— 有 __BAKED__ 就走內嵌資料，沒有就即時查 API。 */
const BAKED = window.__BAKED__ || null;

const INTERVALS = [10000, 15000, 20000];
const RADII     = [2000, 5000, 10000];

/** 移動中把搜尋中心推到「這麼多秒之後會到的位置」 */
const LOOKAHEAD_SECONDS = 45;
/** 低於這個速度（m/s，約 11 km/h）就當作沒在移動，不做前瞻 */
const MOVING_THRESHOLD = 3;
/** 兩次搜尋之間至少間隔這麼久，避免高速行駛時狂打 API */
const MIN_FETCH_GAP_MS = 20000;

const track = new Tracker();

const state = {
  place: '',
  anchor: null,        // 上次搜尋時用的中心點
  lastFetchAt: 0,
  photos: [],
  idx: -1,
  playing: true,
  intervalIdx: 1,      // 預設 15 秒
  radiusIdx: 2,        // 預設 10 km
  timer: null,
  loading: false,
  front: 'B',
  manual: false
};

const intervalMs = () => INTERVALS[state.intervalIdx];
const radius     = () => RADII[state.radiusIdx];

/* ── 啟動 ─────────────────────────────────────────────────── */

// 桌機測試用：index.html?lat=25.0339&lon=121.5645[&auto=1]
const qs = new URLSearchParams(location.search);
if (qs.has('lat') && qs.has('lon')) {
  state.manual = true;
  track.setManual(+qs.get('lat'), +qs.get('lon'));
}

el.bootBtn.addEventListener('click', start, { once: true });

if (BAKED) {
  // 大部分人不在台灣，給一個不需要定位也能看的入口
  el.bootSkip.hidden = false;
  el.btnPlace.hidden = false;
  // 內嵌資料是固定的，搜尋半徑在這個版本沒有意義
  $('#btn-radius').hidden = true;

  el.bootMsg.innerHTML =
    '這是<b>展示版</b>：' + BAKED.length + ' 個台灣景點的照片與簡介已預先內嵌，' +
    '完全不連網。<br>完整版會依你的即時座標向 Wikipedia 與 Wikimedia Commons ' +
    '搜尋任何地點，並在行進中往前方找即將到達的風景。<br>' +
    '按 <b>⌖</b> 可以在 ' + BAKED.map(function (p) { return p.name; }).join('、') + ' 之間切換。';
  el.bootSkip.addEventListener('click', () => {
    state.manual = true;
    const p = BAKED[0];
    track.setManual(p.lat, p.lon);
    start();
  }, { once: true });
}

if (state.manual) {
  el.bootBtn.textContent = '開始（模擬座標）';
  // ?auto=1 直接跳過開場畫面，方便截圖與自動化測試
  if (qs.get('auto') === '1') start();
}

async function start() {
  el.bootBtn.disabled = true;
  el.bootBtn.textContent = '定位中…';

  try {
    if (!state.manual) {
      if (!window.isSecureContext) {
        throw new Error('瀏覽器只允許在 HTTPS（或 localhost）網頁上使用定位功能。');
      }
      track.onFix(await getPositionOnce());
    }
  } catch (err) {
    el.bootBtn.disabled = false;
    el.bootBtn.textContent = '再試一次';
    el.bootMsg.textContent = describeGeoError(err);
    el.bootBtn.addEventListener('click', start, { once: true });
    return;
  }

  el.boot.classList.add('gone');
  keepAwake();
  bindControls();
  bindGestures();
  startTickLoop();

  if (!state.manual) {
    // 停車時 GPS 沒有 heading，靠羅盤才知道車頭朝哪
    attachCompass(track);
    watchPosition(
      (pos) => { track.onFix(pos); onFix(); },
      (err) => { renderHUD(); toast(describeGeoError(err)); }
    );
  }

  // ?drive=270&kmh=60 —— 模擬行駛，讓前瞻與自動重搜可以在桌機上驗證
  if (state.manual && qs.has('drive')) {
    startDriveSim(+qs.get('drive'), +(qs.get('kmh') || 60));
    return;
  }

  onFix();
}

/**
 * 餵合成定位給 Tracker，走完整條真實路徑（濾波 → 前瞻 → 重新搜尋）。
 * 參考「汽車聲浪」作品的模擬加速：GPS 功能沒辦法在桌機上手動測。
 */
function startDriveSim(heading, kmh) {
  const v = kmh / 3.6;
  let pos = { lat: track.lat, lon: track.lon };
  track.reset();   // 清掉 manual 旗標，讓濾波器與前瞻照真實流程跑

  const feed = () => {
    track.onFix({ coords: {
      latitude: pos.lat, longitude: pos.lon,
      accuracy: 8, speed: v, heading, altitude: null
    } });
    onFix();
  };

  feed();
  setInterval(() => { pos = projectAhead(pos, heading, v); feed(); }, 1000);
  toast(`模擬行駛：${compassLabel(heading)}方 ${kmh} km/h`);
}

function describeGeoError(err) {
  if (err && err.code === 1) return '定位權限被拒絕。請到瀏覽器的網站設定中允許「位置」後再試。';
  if (err && err.code === 2) return '目前抓不到位置訊號，請到戶外或開啟手機定位服務後再試。';
  if (err && err.code === 3) return '定位逾時，請再試一次。';
  return (err && err.message) || '定位失敗，請再試一次。';
}

/* ── 搜尋中心：移動中往前方推 ─────────────────────────────── */

/**
 * 回傳這次該用哪個點去搜尋。
 * 只有 GPS 的行進方向能用來前瞻 —— 羅盤讀的是「手機朝哪」，
 * 車上手機隨便擺，拿它推搜尋中心會整個歪掉。
 */
function searchCenter() {
  const p = track.pos;
  if (!p) return null;

  const moving = !track.manual && track.speed >= MOVING_THRESHOLD && track.heading != null;
  if (!moving) return { lat: p.lat, lon: p.lon, ahead: 0, heading: null };

  const ahead = Math.min(4000, Math.max(300, track.speed * LOOKAHEAD_SECONDS));
  const c = projectAhead(p, track.heading, ahead);
  return { lat: c.lat, lon: c.lon, ahead, heading: track.heading };
}

/** 每收到一筆定位就檢查一次要不要重抓 */
function onFix() {
  renderHUD();
  refreshMeta();

  const c = searchCenter();
  if (!c) return;

  if (!state.anchor) { loadNearby(false, c); return; }
  if (Date.now() - state.lastFetchAt < MIN_FETCH_GAP_MS) return;

  // 開得越快，越早需要下一批：市區 400 m 就換，國道約 2.5 km
  const threshold = Math.min(2500, Math.max(400, track.speed * 30));
  if (distanceMeters(state.anchor, c) > threshold) loadNearby(true, c);
}

/* ── 顯示 ─────────────────────────────────────────────────── */

/** 60 Hz 太浪費，5 Hz 已經足夠讓速度讀數看起來連續 */
function startTickLoop() {
  let last = performance.now();
  setInterval(() => {
    const now = performance.now();
    track.tick((now - last) / 1000);
    last = now;
    renderHUD();
  }, 200);
}

function renderHUD() {
  const p = track.pos;
  if (!p) return;

  el.hudDot.className = 'dot ' +
    (!track.ok ? '' : (track.stale || track.accuracy > 100) ? 'warm' : 'live');

  el.hudCoords.textContent = formatCoord(p.lat, p.lon) +
    (track.accuracy ? ` ±${Math.round(track.accuracy)}m` : '');

  el.hudPlace.textContent = [state.place, `${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`]
    .filter(Boolean).join('  ·  ');

  const bits = [];
  if (track.speed > 0.5) bits.push(`${Math.round(track.speedKmh)} km/h`);
  const b = track.bearing();
  if (b) bits.push(`${compassLabel(b.deg)}方 ${Math.round(b.deg)}° ${b.src}`);
  bits.push(track.status());
  const c = searchCenter();
  if (c && c.ahead > 0) bits.push(`前方 ${formatDistance(c.ahead)} 搜尋中`);
  el.hudMotion.textContent = bits.join('  ·  ');
}

/* ── 抓取附近照片 ─────────────────────────────────────────── */

async function loadNearby(isMove, center) {
  if (state.loading) return;
  state.loading = true;
  state.lastFetchAt = Date.now();
  state.anchor = { lat: center.lat, lon: center.lon };

  if (isMove) {
    toast(center.ahead > 0
      ? `已前進，改搜尋前方 ${formatDistance(center.ahead)} 的風景…`
      : '位置改變了，重新尋找附近的風景…');
  } else {
    showPlaceholder('搜尋附近的風景…',
      '正在向 Wikipedia 與 Wikimedia Commons 查詢這個座標周圍的景點照片。');
  }

  if (BAKED) {
    const p = nearestBaked(center);
    if (p) { state.place = p.area; renderHUD(); }
  } else {
    reverseGeocode(center.lat, center.lon).then((name) => {
      if (name) { state.place = name; renderHUD(); }
    });
  }

  try {
    // 搜尋中心可能在前方，但距離與前後判斷要以「你人在哪」為準
    const opts = {
      lat: center.lat, lon: center.lon,
      from: track.pos, heading: center.heading
    };
    let list = await fetchNearby({ ...opts, radius: radius() });

    // 半徑內沒東西 → 自動放大到上限再找一次
    if (!list.length && radius() < 10000) {
      state.radiusIdx = RADII.length - 1;
      syncRadiusBtn();
      list = await fetchNearby({ ...opts, radius: radius() });
    }

    if (!list.length) {
      state.photos = [];
      state.idx = -1;
      stopTimer();
      showPlaceholder('這附近還沒有公開照片',
        '以 ' + formatDistance(radius()) + '為半徑，資料庫裡找不到帶有座標的公開照片。' +
        '這在偏遠地區或海上很常見 — 繼續前進，抓到新位置時會自動再找一次。');
      return;
    }

    state.photos = list;
    state.idx = -1;
    show(0);
    toast('找到 ' + list.length + ' 張附近的照片');
  } catch (err) {
    showPlaceholder('連線失敗',
      '無法取得照片資料：' + err.message + '。請確認網路連線後按 ↻ 重試。');
  } finally {
    state.loading = false;
  }
}

/* ── 輪播 ─────────────────────────────────────────────────── */

function show(i, dir) {
  dir = dir || 1;
  if (!state.photos.length) return;
  const n = state.photos.length;
  const idx = ((i % n) + n) % n;
  const item = state.photos[idx];

  const img = new Image();
  img.decoding = 'async';
  img.onload = () => {
    state.idx = idx;
    paint(item);
    updateCount();
    preload(idx + 1);
    if (state.playing) startTimer();
  };
  img.onerror = () => {
    // 這張圖掛了就丟掉，直接換下一張
    state.photos.splice(idx, 1);
    if (state.photos.length) show(dir > 0 ? idx : idx - 1, dir);
    else showPlaceholder('照片載入失敗', '這批照片都無法載入，請按 ↻ 重新搜尋。');
  };
  img.src = item.image;
}

function paint(item) {
  const next = state.front === 'A' ? el.photoA : el.photoB;
  const prev = state.front === 'A' ? el.photoB : el.photoA;
  state.front = state.front === 'A' ? 'B' : 'A';

  next.style.backgroundImage = 'url("' + item.image + '")';
  next.classList.remove('kb');
  void next.offsetWidth;                 // 重啟 Ken Burns 動畫
  next.classList.add('on', 'kb');
  prev.classList.remove('on');

  el.kicker.textContent = item.kicker;
  el.title.textContent  = item.title;
  el.body.textContent   = item.caption;
  el.body.scrollTop     = 0;
  // 只有內文真的溢出時才加底部漸隱，短簡介加了會平白淡掉最後一行
  requestAnimationFrame(() => {
    el.body.classList.toggle('is-scrollable',
      el.body.scrollHeight > el.body.clientHeight + 1);
  });
  el.credit.textContent = item.credit;
  el.source.textContent = item.kind === 'wikipedia' ? '閱讀維基百科條目 ↗' : '查看原始照片與授權 ↗';
  el.source.href        = item.sourceUrl;
  refreshMeta();
}

/** 距離／方位相對的是「你現在的位置」，會隨移動改變，所以每次定位都重算 */
function refreshMeta() {
  const item = state.photos[state.idx];
  const p = track.pos;
  if (!item || !p || item.lat == null || item.lon == null) {
    el.meta.textContent = '';
    return;
  }

  const d = distanceMeters(p, item);
  const to = bearingDeg(p, item);
  item.distance = d;

  // 行進中額外標出這個景點在你前方，還是已經開過去了
  let rel = '';
  if (track.speed >= MOVING_THRESHOLD && track.heading != null) {
    const off = Math.abs(((to - track.heading) % 360 + 540) % 360 - 180);
    rel = off < 60 ? '前方' : off > 120 ? '已通過' : '側邊';
  }

  el.meta.innerHTML =
    '<b>' + formatDistance(d) + '</b>' +
    ' <span class="sep">/</span> ' + compassLabel(to) + '方' +
    (rel ? ' <span class="rel">' + rel + '</span>' : '') +
    ' <span class="sep">·</span> ' + item.lat.toFixed(4) + ', ' + item.lon.toFixed(4);
}

function preload(i) {
  const n = state.photos.length;
  if (!n) return;
  const item = state.photos[((i % n) + n) % n];
  if (item) new Image().src = item.image;
}

function showPlaceholder(title, msg) {
  el.kicker.textContent = '';
  el.title.textContent = title;
  el.body.textContent = msg;
  el.meta.textContent = '';
  el.credit.textContent = '';
  el.source.textContent = '';
  el.source.removeAttribute('href');
  el.count.textContent = '';
}

function updateCount() {
  el.count.textContent = state.photos.length ? (state.idx + 1) + ' / ' + state.photos.length : '';
}

/* ── 計時器與進度條 ───────────────────────────────────────── */

function startTimer() {
  stopTimer();
  runBar(intervalMs());
  state.timer = setTimeout(() => show(state.idx + 1, 1), intervalMs());
}

function stopTimer() {
  clearTimeout(state.timer);
  state.timer = null;
}

function runBar(ms) {
  el.bar.style.transition = 'none';
  el.bar.style.width = '0%';
  void el.bar.offsetWidth;
  el.bar.style.transition = 'width ' + ms + 'ms linear';
  el.bar.style.width = '100%';
}

function freezeBar() {
  const w = getComputedStyle(el.bar).width;
  el.bar.style.transition = 'none';
  el.bar.style.width = w;
}

/* ── 控制項 ───────────────────────────────────────────────── */

function bindControls() {
  $('#btn-prev').onclick = () => { stopTimer(); show(state.idx - 1, -1); };
  $('#btn-next').onclick = () => { stopTimer(); show(state.idx + 1, 1); };

  $('#btn-play').onclick = (e) => {
    state.playing = !state.playing;
    e.currentTarget.textContent = state.playing ? '❚❚' : '▶';
    if (state.playing) startTimer();
    else { stopTimer(); freezeBar(); }
  };

  $('#btn-speed').onclick = (e) => {
    state.intervalIdx = (state.intervalIdx + 1) % INTERVALS.length;
    e.currentTarget.textContent = (intervalMs() / 1000) + 's';
    toast('每 ' + (intervalMs() / 1000) + ' 秒換一張');
    if (state.playing) startTimer();
  };

  $('#btn-radius').onclick = () => {
    state.radiusIdx = (state.radiusIdx + 1) % RADII.length;
    syncRadiusBtn();
    toast('搜尋半徑 ' + formatDistance(radius()) + '，重新搜尋中…');
    forceReload();
  };

  $('#btn-reload').onclick = forceReload;

  // 展示版：在烘焙好的地點之間跳，讓不在台灣的人也看得到內容
  if (BAKED) {
    el.btnPlace.onclick = () => {
      const here = track.pos;
      const cur = here ? BAKED.indexOf(nearestBaked(here)) : -1;
      const next = BAKED[(cur + 1 + BAKED.length) % BAKED.length];
      state.manual = true;
      track.setManual(next.lat, next.lon);
      state.place = next.area;
      toast('切換到 ' + next.name);
      forceReload();
    };
  }

  // iPhone 的 Safari 不支援 requestFullscreen，App 內建瀏覽器更是連工具列都拿不掉。
  // 與其跳「不支援」，不如講出真正可行的做法。
  if (standalone()) {
    $('#btn-full').hidden = true;           // 已經從主畫面開啟，本來就是全螢幕
  } else if (!document.documentElement.requestFullscreen) {
    $('#btn-full').onclick = () => toast(fullscreenHint());
  } else {
    $('#btn-full').onclick = async () => {
      try {
        if (document.fullscreenElement) {
          await document.exitFullscreen();
        } else {
          await document.documentElement.requestFullscreen();
          if (screen.orientation && screen.orientation.lock) {
            screen.orientation.lock('landscape').catch(() => {});
          }
        }
      } catch { toast(fullscreenHint()); }
    };
  }

  syncRadiusBtn();
  $('#btn-speed').textContent = (intervalMs() / 1000) + 's';

  document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight') $('#btn-next').click();
    else if (e.key === 'ArrowLeft') $('#btn-prev').click();
    else if (e.key === ' ') { e.preventDefault(); $('#btn-play').click(); }
    else if (e.key === 'f') $('#btn-full').click();
  });
}

function forceReload() {
  const c = searchCenter();
  if (!c) return;
  state.anchor = null;
  state.lastFetchAt = 0;
  loadNearby(false, c);
}

/** 已經是「加入主畫面」啟動的獨立視窗？ */
function standalone() {
  return window.navigator.standalone === true ||
         window.matchMedia('(display-mode: standalone), (display-mode: fullscreen)').matches;
}

/** 依所在瀏覽器給出真的能達成全螢幕的做法 */
function fullscreenHint() {
  const ua = navigator.userAgent;
  const inApp = /(^|[^A-Za-z])Line\/|FBAN|FBAV|Instagram|MicroMessenger/i.test(ua);
  if (inApp) return '請按右下角選單 →「用預設瀏覽器開啟」，再加入主畫面';
  if (/iP(hone|od|ad)/.test(ua) || (/Macintosh/.test(ua) && 'ontouchend' in document)) {
    return 'iPhone 請按分享 →「加入主畫面」，從主畫面開啟就是全螢幕';
  }
  return '這個瀏覽器不支援全螢幕';
}

function syncRadiusBtn() {
  const r = radius();
  $('#btn-radius').textContent = r >= 1000 ? (r / 1000) + 'km' : r + 'm';
}

/** 觸控：左右滑換照片；碰到畫面就顯示控制列 */
function bindGestures() {
  const stage = $('#stage');
  let x0 = null, y0 = null;

  stage.addEventListener('touchstart', (e) => {
    x0 = e.touches[0].clientX;
    y0 = e.touches[0].clientY;
    revealControls();
  }, { passive: true });

  stage.addEventListener('touchend', (e) => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0;
    const dy = e.changedTouches[0].clientY - y0;
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      stopTimer();
      show(state.idx + (dx < 0 ? 1 : -1), dx < 0 ? 1 : -1);
    }
    x0 = null; y0 = null;
  }, { passive: true });

  stage.addEventListener('mousemove', revealControls);
}

let controlsTimer;
function revealControls() {
  el.controls.classList.add('show');
  clearTimeout(controlsTimer);
  controlsTimer = setTimeout(() => el.controls.classList.remove('show'), 3000);
}

/* ── Toast ────────────────────────────────────────────────── */

let toastTimer;
function toast(msg) {
  el.toast.textContent = msg;
  el.toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.toast.classList.remove('show'), 2600);
}

/* 分頁切回前景時重啟計時，避免瀏覽器凍結計時器後卡住 */
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && state.playing && state.photos.length) startTimer();
});
