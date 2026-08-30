/* photos.js — 依座標抓取附近景點的公開照片與簡介
 *
 * 來源（皆為免金鑰、開放 CORS 的公開 API）：
 *   1. Wikipedia geosearch         → 附近條目的代表照片 + 條目摘要（最適合當「簡介」）
 *   2. Wikimedia Commons geosearch → 帶有 GPS 座標的公開授權照片 + 說明／授權
 *
 * 注意：Wikimedia 的 geosearch 半徑上限為 10000 公尺。
 */

const MAX_RADIUS = 10000;

/* 常見的「非風景」檔案，用檔名關鍵字先濾掉 */
const REJECT = /(logo|icon|emblem|seal|map|karte|mapa|地図|地圖|flag|coat[_ ]of[_ ]arms|diagram|chart|plaque|signpost|banner|qr[_ ]code|screenshot|blank|placeholder)/i;
/* 由 SVG 轉出的點陣圖幾乎都是標誌、徽章或地圖，不是照片 */
const FROM_SVG = /\.svgx?\.(png|jpe?g)$/i;
const OK_EXT = /\.(jpe?g|png|webp)$/i;

const api = (host, params) =>
  `https://${host}/w/api.php?` + new URLSearchParams({
    action: 'query', format: 'json', formatversion: '2', origin: '*', ...params
  });

async function getJSON(url) {
  const res = await fetch(url, { cache: 'default' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

const stripHTML = (s = '') =>
  s.replace(/<[^>]*>/g, ' ').replace(/&[a-z]+;|&#\d+;/gi, ' ').replace(/\s+/g, ' ').trim();

const clamp = (s, n) => (s.length > n ? s.slice(0, n).replace(/[，,、。;；\s]\S*$/, '') + '…' : s);

/** 清理 Commons 常見的機器命名：「2010 07 22100 6911 Xinyi District…」→「Xinyi District…」 */
function tidyTitle(s) {
  const cleaned = String(s)
    .replace(/^(?:\d{2,8}[-_ ]+){2,}/, '')
    .replace(/^(?:IMG|DSC|DSCN|PICT|P)[-_ ]?\d+[-_ ]*/i, '')
    .replace(/[_]+/g, ' ')
    .replace(/\s*-\s*panoramio\s*(\(\d+\))?\s*$/i, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
  return cleaned.length >= 3 ? cleaned : String(s).replace(/[_]+/g, ' ').trim();
}

/** 從圖片網址取出檔名（去掉查詢字串與 NNNpx- 前綴） */
function fileNameOf(url) {
  const seg = String(url).split('?')[0].split('/').pop() || '';
  let name = seg.replace(/^\d+px-/, '');
  try { name = decodeURIComponent(name); } catch { /* 保留原字串 */ }
  return name;
}

/** 同一張底圖在不同條目會重複出現，用檔名當去重鍵 */
const imageKey = (url) => fileNameOf(url).toLowerCase();

/** 這張圖看起來像照片嗎？ */
function looksLikePhoto(url) {
  const name = fileNameOf(url);
  return !FROM_SVG.test(name) && !REJECT.test(name) && OK_EXT.test(name);
}

/**
 * zh 維基的條目標題是原始用字，可能是簡體或非台灣慣用譯名
 * （「罗马斗兽场」「大本钟」「金门大桥」），而且 API 的 variant /
 * converttitles / uselang 都不會轉換 generator 回傳的標題。
 * 但 extract 已依 zh-tw 轉換過，且幾乎總是以正確名稱開頭，所以改用它。
 *
 * 保險：只在「字數相同、用字不同」時採用。簡繁與地區詞轉換是逐字對應的，
 * 字數必然相同；字數不同代表開頭那段根本不是標題（例如「拉魯島」的內文
 * 以「拉魯」開頭），這時保留原標題。
 */
function displayTitle(title, extract) {
  const head = String(extract || '').split(/[（(，,。、：:；;]/)[0].trim();
  if (!head || head === title) return title;
  return [...head].length === [...title].length ? head : title;
}

/* ── 1. Wikipedia 條目 ─────────────────────────────────────── */
async function fromWikipedia(lat, lon, radius, lang) {
  const url = api(`${lang}.wikipedia.org`, {
    generator: 'geosearch',
    ggscoord: `${lat}|${lon}`,
    ggsradius: String(radius),
    ggslimit: '20',
    prop: 'pageimages|extracts|coordinates',
    colimit: 'max',
    codistancefrompoint: `${lat}|${lon}`,
    piprop: 'thumbnail',
    pithumbsize: '1600',
    exintro: '1',
    explaintext: '1',
    exchars: '620',
    exlimit: '20'
  });

  const data = await getJSON(url);
  const pages = data?.query?.pages ?? [];

  return pages
    .filter((p) => {
      const t = p.thumbnail;
      if (!t?.source || t.width < 640) return false;
      if (t.width / t.height < 0.5) return false;   // 極端直幅在橫向版面只剩一條
      return looksLikePhoto(t.source);
    })
    .map((p) => ({
      id: `wp:${lang}:${p.pageid}`,
      kind: 'wikipedia',
      kicker: lang === 'zh' ? '附近景點' : 'NEARBY',
      title: lang === 'zh' ? displayTitle(p.title, p.extract) : p.title,
      caption: clamp(stripHTML(p.extract || ''), 420) || '（此條目尚無摘要）',
      credit: `維基百科（${lang === 'zh' ? '中文' : lang.toUpperCase()}）· CC BY-SA`,
      image: p.thumbnail.source,
      sourceUrl: `https://${lang}.wikipedia.org/?curid=${p.pageid}`,
      lat: p.coordinates?.[0]?.lat,
      lon: p.coordinates?.[0]?.lon
    }));
}

/* ── 2. Wikimedia Commons 照片 ─────────────────────────────── */
async function fromCommons(lat, lon, radius) {
  const url = api('commons.wikimedia.org', {
    generator: 'geosearch',
    ggsnamespace: '6',
    ggscoord: `${lat}|${lon}`,
    ggsradius: String(radius),
    ggslimit: '60',
    prop: 'imageinfo|coordinates',
    coprimary: 'all',
    colimit: 'max',
    codistancefrompoint: `${lat}|${lon}`,
    iiprop: 'url|extmetadata|dimensions|mime',
    iiurlwidth: '1600',
    iiextmetadatalanguage: 'zh',
    iiextmetadatafilter: 'ImageDescription|ObjectName|Artist|Credit|LicenseShortName|DateTimeOriginal'
  });

  const data = await getJSON(url);
  const pages = data?.query?.pages ?? [];

  return pages.flatMap((p) => {
    const ii = p.imageinfo?.[0];
    if (!ii?.thumburl) return [];
    if (!/^image\/(jpeg|png|webp)$/.test(ii.mime || '')) return [];
    if (ii.width < 900) return [];                 // 太小的放大會糊
    if (ii.width / ii.height < 0.95) return [];    // 直幅在橫向版面不好看
    if (!looksLikePhoto(p.title)) return [];

    const m = ii.extmetadata || {};
    const rawName = stripHTML(m.ObjectName?.value || '') ||
                    fileNameOf(p.title.replace(/^File:/, '')).replace(OK_EXT, '');
    const name = tidyTitle(rawName);
    const desc = stripHTML(m.ImageDescription?.value || '');
    const by   = stripHTML(m.Artist?.value || m.Credit?.value || '');
    const lic  = stripHTML(m.LicenseShortName?.value || '公開授權');
    const year = (stripHTML(m.DateTimeOriginal?.value || '').match(/\d{4}/) || [])[0];

    return [{
      id: `cm:${p.pageid}`,
      kind: 'commons',
      kicker: '在地影像',
      title: clamp(name, 60),
      caption: clamp(desc, 380) || '這張照片由攝影者標註於此座標附近，未附文字說明。',
      credit: [by && `攝影：${clamp(by, 60)}`, year, lic].filter(Boolean).join(' · '),
      image: ii.thumburl,
      sourceUrl: ii.descriptionurl,
      lat: p.coordinates?.[0]?.lat,
      lon: p.coordinates?.[0]?.lon
    }];
  });
}

/* ── 對外主函式 ───────────────────────────────────────────── */
/**
 * @param {object}   opts
 * @param {number}   opts.lat      搜尋中心（移動中會是「前方」的推算點）
 * @param {number}   opts.lon
 * @param {object}  [opts.from]    使用者實際位置；距離與「前方與否」都以這裡為基準。
 *                                 預設等於搜尋中心 —— 兩者不同時一定要傳，否則
 *                                 「介於你與前瞻點之間」的景點會被誤判成在身後。
 * @param {number}  [opts.radius]  搜尋半徑，上限 10 公里
 * @param {number}  [opts.heading] 行進方向；有給的話會濾掉身後的景點
 * @param {string[]}[opts.langs]
 * @returns {Promise<Array>} 依「距離 + 來源 + 前方與否」排序的照片清單
 */
export async function fetchNearby({ lat, lon, from = null, radius = MAX_RADIUS, heading = null, langs = ['zh', 'en'] }) {
  // 展示版（Artifact）沒有網路可用，改讀內嵌資料
  if (window.__BAKED__) return fromBaked({ lat, lon, from, heading });

  const r = Math.max(100, Math.min(MAX_RADIUS, Math.round(radius)));

  const settled = await Promise.allSettled([
    ...langs.map((l) => fromWikipedia(lat, lon, r, l)),
    fromCommons(lat, lon, r)
  ]);
  const all = settled.flatMap((s) => (s.status === 'fulfilled' ? s.value : []));
  if (!all.length) return [];

  // 去重：同一張底圖、同名條目只留一筆（中文條目先進來，因此優先保留）
  const seen = new Set();
  let unique = [];
  for (const item of all) {
    const kImg = imageKey(item.image);
    const kName = item.title.toLowerCase().replace(/\s+/g, '');
    if (seen.has(kImg) || seen.has(kName)) continue;
    seen.add(kImg); seen.add(kName);
    unique.push(item);
  }

  // 距離與方位一律以「使用者實際位置」為基準；搜尋中心只用來決定跟 API 要哪一帶
  const here = from || { lat, lon };
  for (const it of unique) {
    const known = it.lat != null && it.lon != null;
    it.distance = known ? haversine(here, { lat: it.lat, lon: it.lon }) : r * 0.75;
    it.offBearing = (heading != null && known && it.distance > 60)
      ? offBearing(bearingTo(here, it), heading)     // 0 = 正前方，180 = 正後方
      : null;
    it.ahead = it.offBearing == null ? null : it.offBearing < 90;
  }

  // 行進中直接濾掉身後的景點 —— 開車時想看的是即將到達的風景。
  // 只在濾完還留得夠多時才套用，免得在景點稀疏的路段整個清空。
  let pool = unique;
  if (heading != null) {
    const ahead = unique.filter((i) => i.offBearing == null || i.offBearing <= 120);
    if (ahead.length >= 12) pool = ahead;
  }

  // 排序：以距離為主，維基條目（有完整簡介）與更正前方的景點加權提前
  for (const it of pool) {
    let w = it.kind === 'wikipedia' ? 0.55 : 1;
    if (it.offBearing != null) w *= 1 + (it.offBearing / 180) * 1.4;
    it._score = it.distance * w;
  }
  unique = pool;
  unique.sort((a, b) => a._score - b._score);

  // 同一位攝影者連拍上傳的照片幾乎長得一樣，每個批次最多留 2 張
  const perBatch = new Map();
  const varied = unique.filter((it) => {
    if (it.kind !== 'commons') return true;
    const batch = it.title.replace(/\d+/g, '').slice(0, 24).toLowerCase();
    const n = (perBatch.get(batch) || 0) + 1;
    perBatch.set(batch, n);
    return n <= 2;
  });

  // 交錯兩種來源，讓「有完整簡介的景點」與「在地影像」輪流出現
  const wiki = varied.filter((i) => i.kind === 'wikipedia');
  const cm   = varied.filter((i) => i.kind === 'commons');
  const out = [];
  while (wiki.length || cm.length) {
    if (wiki.length) out.push(wiki.shift());
    if (cm.length) out.push(cm.shift());
  }

  return out.slice(0, 60);
}

/* ── 展示版：內嵌資料 ─────────────────────────────────────── */

/** 離指定座標最近的烘焙地點；沒有內嵌資料時回 null */
export function nearestBaked(pos) {
  const baked = window.__BAKED__;
  if (!baked || !baked.length || !pos) return null;
  return baked
    .map((p) => ({ p, d: haversine(pos, p) }))
    .sort((a, b) => a.d - b.d)[0].p;
}

function fromBaked({ lat, lon, from, heading }) {
  const here = from || { lat, lon };
  const place = nearestBaked({ lat, lon });
  if (!place) return [];

  const items = place.photos.map((x) => Object.assign({}, x));
  for (const it of items) {
    const known = it.lat != null && it.lon != null;
    it.distance = known ? haversine(here, it) : 0;
    it.offBearing = (heading != null && known && it.distance > 60)
      ? offBearing(bearingTo(here, it), heading)
      : null;
    it.ahead = it.offBearing == null ? null : it.offBearing < 90;
    it._score = it.distance * (it.kind === 'wikipedia' ? 0.55 : 1);
  }
  items.sort((a, b) => a._score - b._score);
  return items;
}

/* 內部用的幾何計算（讓 photos.js 不必依賴 geo.js） */
function bearingTo(a, b) {
  const rad = (d) => d * Math.PI / 180;
  const dLon = rad(b.lon - a.lon);
  const y = Math.sin(dLon) * Math.cos(rad(b.lat));
  const x = Math.cos(rad(a.lat)) * Math.sin(rad(b.lat)) -
            Math.sin(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.cos(dLon);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

/** 兩個方位角的夾角，0（同向）～180（反向） */
function offBearing(a, b) {
  return Math.abs(((a - b) % 360 + 540) % 360 - 180);
}


function haversine(a, b) {
  const rad = (d) => d * Math.PI / 180;
  const dLat = rad(b.lat - a.lat), dLon = rad(b.lon - a.lon);
  const s = Math.sin(dLat / 2) ** 2 +
            Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 12742000 * Math.asin(Math.min(1, Math.sqrt(s)));
}

export { MAX_RADIUS };
