/* geo.js — 定位追蹤、距離／方位計算、反向地理編碼
 *
 * Tracker 的濾波做法參考自同目錄下的「汽車聲浪」作品（exhaust-note-site）：
 * GPS 大約 1 Hz 且帶雜訊，直接使用會一格一格跳。這裡用 alpha-beta 濾波器
 * （等加速度模型的簡化 Kalman）同時維護「平滑速度」與「加速度」兩個狀態。
 *
 * 差別在於用途：聲浪作品拿速度去驅動音訊，這裡拿速度與行進方向去決定
 * 「該往哪裡找風景」——移動中會把搜尋中心往前方推，先看到即將到達的景點。
 */

const R = 6371000; // 地球半徑（公尺）
const rad = (d) => d * Math.PI / 180;
const deg = (r) => r * 180 / Math.PI;

/* ── 幾何 ─────────────────────────────────────────────────── */

/** 兩點間大圓距離（公尺） */
export function distanceMeters(a, b) {
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const s = Math.sin(dLat / 2) ** 2 +
            Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(s)));
}

/** a → b 的方位角（0–360，正北為 0） */
export function bearingDeg(a, b) {
  const dLon = rad(b.lon - a.lon);
  const y = Math.sin(dLon) * Math.cos(rad(b.lat));
  const x = Math.cos(rad(a.lat)) * Math.sin(rad(b.lat)) -
            Math.sin(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.cos(dLon);
  return (deg(Math.atan2(y, x)) + 360) % 360;
}

/** 從一點沿指定方位前進指定距離後的座標 */
export function projectAhead(from, bearing, meters) {
  const d = meters / R;
  const br = rad(bearing);
  const la1 = rad(from.lat), lo1 = rad(from.lon);
  const la2 = Math.asin(Math.sin(la1) * Math.cos(d) + Math.cos(la1) * Math.sin(d) * Math.cos(br));
  const lo2 = lo1 + Math.atan2(Math.sin(br) * Math.sin(d) * Math.cos(la1),
                               Math.cos(d) - Math.sin(la1) * Math.sin(la2));
  return { lat: deg(la2), lon: ((deg(lo2) + 540) % 360) - 180 };
}

/** 兩個方位角之間的夾角：0 為同向，180 為反向 */
export function angleBetween(a, b) {
  return Math.abs(((a - b) % 360 + 540) % 360 - 180);
}

const COMPASS = ['北', '東北', '東', '東南', '南', '西南', '西', '西北'];
export const compassLabel = (d) => COMPASS[Math.round(d / 45) % 8];

/** 公尺 → 易讀字串 */
export function formatDistance(m) {
  if (!isFinite(m)) return '';
  if (m < 950) return `${Math.round(m / 10) * 10} 公尺`;
  return `${(m / 1000).toFixed(m < 9500 ? 1 : 0)} 公里`;
}

/** 座標 → 度分秒 */
export function formatCoord(lat, lon) {
  const dms = (v, pos, neg) => {
    const dir = v >= 0 ? pos : neg;
    v = Math.abs(v);
    const d = Math.floor(v);
    const m = Math.floor((v - d) * 60);
    const s = (((v - d) * 60) - m) * 60;
    return `${d}°${String(m).padStart(2, '0')}'${s.toFixed(1)}"${dir}`;
  };
  return `${dms(lat, 'N', 'S')}  ${dms(lon, 'E', 'W')}`;
}

/* ── 定位追蹤器 ───────────────────────────────────────────── */

export class Tracker {
  constructor() { this.reset(); }

  reset() {
    this.ok = false;
    this.manual = false;
    this.lat = null; this.lon = null;
    this.speed = 0;          // m/s（已平滑）
    this.accel = 0;          // m/s²（濾波器狀態，非事後差分）
    this.heading = null;     // 行進方向（GPS）
    this.compass = null;     // 電子羅盤（靜止時的備援）
    this.accuracy = null;
    this.rate = 0;           // 定位更新率 Hz
    this.fixes = 0;
    this.derived = false;    // 速度是自己用座標推算的
    this.stale = false;
    this.last = 0;
    this.lastPos = null;
  }

  /** 桌機測試：直接指定一個不動的座標 */
  setManual(lat, lon) {
    this.reset();
    this.manual = true; this.ok = true;
    this.lat = lat; this.lon = lon;
    this.last = performance.now();
  }

  /** 收到定位：用殘差同時修正速度與加速度（correct） */
  onFix(pos) {
    const now = performance.now();
    const c = pos.coords;

    this.lat = c.latitude;
    this.lon = c.longitude;
    this.accuracy = c.accuracy;

    // heading 是「行進方向」，靜止時裝置依規範回傳 null 或 NaN
    if (c.heading != null && isFinite(c.heading) && c.speed > 0.8) this.heading = c.heading;

    // 多數裝置直接給 coords.speed；沒有的話退回用連續兩點的距離推算
    let z = (c.speed != null && c.speed >= 0) ? c.speed : null;
    if (z === null && this.lastPos) {
      const dt = (now - this.last) / 1000;
      if (dt > 0.25 && dt < 6) {
        z = distanceMeters(this.lastPos, { lat: c.latitude, lon: c.longitude }) / dt;
        this.derived = true;
        // 沒有 heading 時，用移動軌跡自己算一個
        if (z > 1.5) this.heading = bearingDeg(this.lastPos, { lat: c.latitude, lon: c.longitude });
      }
    }
    this.lastPos = { lat: c.latitude, lon: c.longitude };

    if (z === null) { this.last = now; return; }

    const dt = (now - this.last) / 1000;
    this.last = now;
    this.fixes++;

    if (!this.ok) { this.ok = true; this.speed = z; this.accel = 0; return; }
    if (dt <= 0.05 || dt > 6) return;
    this.rate = 1 / dt;

    // tick() 已把狀態外推到現在，這裡只做修正。
    // 係數沿用聲浪作品掃參數的結果：GPS 的速度量測本身夠準，
    // 濾波器的工作是平順內插而不是抑制雜訊，所以要大膽相信量測值。
    const r = z - this.speed;
    const A = 0.95, B = 0.90;
    this.speed = Math.max(0, this.speed + A * r);
    this.accel = Math.max(-9, Math.min(9, this.accel + (B / dt) * r));
  }

  /** 兩次定位之間以等加速度外推，讓速度顯示連續而不是每秒跳一格 */
  tick(dt) {
    if (!this.ok || this.manual) return this.speed;
    const age = (performance.now() - this.last) / 1000;
    this.stale = age > 3;
    if (this.stale) this.accel *= (1 - Math.min(1, dt * 1.2));

    this.speed = Math.max(0, this.speed + this.accel * dt);
    if (this.speed < 0.4 && this.accel <= 0) { this.speed = 0; this.accel = 0; }
    return this.speed;
  }

  get pos() {
    return this.lat == null ? null : { lat: this.lat, lon: this.lon };
  }

  get speedKmh() { return this.speed * 3.6; }

  /** 行進中優先用 GPS 的行進方向，靜止時退回手機羅盤 */
  bearing() {
    if (this.speed > 1.2 && this.heading != null) return { deg: this.heading, src: 'GPS' };
    if (this.compass != null) return { deg: this.compass, src: '羅盤' };
    if (this.heading != null) return { deg: this.heading, src: 'GPS' };
    return null;
  }

  status() {
    if (!this.ok) return '未定位';
    if (this.manual) return '模擬座標';
    if (this.stale) return '訊號中斷';
    return (this.rate ? this.rate.toFixed(1) : '—') + ' Hz' + (this.derived ? '（推算）' : '');
  }
}

/* ── 瀏覽器介面 ───────────────────────────────────────────── */

/** 持續監看 GPS，把原始 GeolocationPosition 交給呼叫端。回傳 stop()。 */
export function watchPosition(onFix, onError) {
  if (!('geolocation' in navigator)) {
    onError?.(new Error('此瀏覽器不支援定位功能'));
    return () => {};
  }
  const id = navigator.geolocation.watchPosition(onFix, (e) => onError?.(e), {
    enableHighAccuracy: true,
    maximumAge: 0,        // 行進中不吃快取，寧可等新的一筆
    timeout: 20000
  });
  return () => navigator.geolocation.clearWatch(id);
}

/** 取一次定位（用來確認權限並取得起始座標） */
export function getPositionOnce() {
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(resolve, reject,
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
  });
}

/**
 * 要電子羅盤權限，並把讀數餵給 tracker。
 * 停車時 GPS 沒有 heading，只能靠羅盤知道車頭朝哪。
 */
export async function attachCompass(tracker) {
  try {
    let ok = true;
    if (typeof DeviceOrientationEvent !== 'undefined' &&
        typeof DeviceOrientationEvent.requestPermission === 'function') {
      ok = (await DeviceOrientationEvent.requestPermission()) === 'granted';
    }
    if (!ok) return false;

    window.addEventListener('deviceorientation', (e) => {
      // iOS 提供已修正為真北的 webkitCompassHeading；其他平台用 alpha 反推
      const h = (e.webkitCompassHeading != null && isFinite(e.webkitCompassHeading))
        ? e.webkitCompassHeading
        : (e.alpha != null && isFinite(e.alpha) ? (360 - e.alpha) % 360 : null);
      if (h != null) tracker.compass = h;
    });
    return true;
  } catch {
    return false;
  }
}

/** 反向地理編碼 → 「中華民國 · 臺北市」。失敗回空字串，不阻斷主流程。 */
export async function reverseGeocode(lat, lon) {
  try {
    const url = 'https://api-bdc.net/data/reverse-geocode-client' +
                `?latitude=${lat}&longitude=${lon}&localityLanguage=zh`;
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error(res.status);
    const j = await res.json();
    return [j.countryName, j.principalSubdivision, j.city || j.locality]
      .filter(Boolean)
      .filter((v, i, arr) => arr.indexOf(v) === i)
      .join(' · ');
  } catch {
    return '';
  }
}

/** 螢幕恆亮（必須在使用者手勢中呼叫才會成功） */
export async function keepAwake() {
  try {
    if ('wakeLock' in navigator) {
      let lock = await navigator.wakeLock.request('screen');
      document.addEventListener('visibilitychange', async () => {
        if (document.visibilityState === 'visible') {
          try { lock = await navigator.wakeLock.request('screen'); } catch {}
        }
      });
      return lock;
    }
  } catch {}
  return null;
}
