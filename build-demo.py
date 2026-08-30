#!/usr/bin/env python3
"""烘焙展示版：把幾個台灣經典景點的照片與簡介抓下來、base64 內嵌成零網路單檔。

    python build-demo.py         # → dist/demo.html

Artifact 的 CSP 會擋掉對外部主機的 fetch() 與遠端圖片，所以完整版沒辦法上
Artifact。這裡照「汽車聲浪」專案的做法把內容全部內嵌，換成一個可以分享、
但只有預先烘焙地點的展示版。

篩選規則刻意與 js/photos.js 一致（SVG 轉檔、關鍵字黑名單、尺寸與比例、去重），
兩邊要一起改。
"""

import base64
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, 'dist', 'demo.html')
CACHE = os.path.join(ROOT, '.demo-cache')

UA = 'gps-scenery-demo-builder/1.0 (https://github.com/; personal project)'
THUMB_W = 1100
PHOTOS_PER_PLACE = 6
BYTES_PER_PLACE = 1_150_000        # 每個地點的原始位元組預算
TOTAL_BUDGET = 7_000_000           # base64 之後約 9.3 MB，仍在 16 MB 上限內

PLACES = [
    ('taipei101', '台北 101',   25.0339, 121.5645, '中華民國 · 臺北市 · 信義區'),
    ('taroko',    '太魯閣',     24.1580, 121.6210, '中華民國 · 花蓮縣 · 秀林鄉'),
    ('yushan',    '玉山',       23.4700, 120.9570, '中華民國 · 南投縣 · 信義鄉'),
    ('sunmoon',   '日月潭',     23.8600, 120.9150, '中華民國 · 南投縣 · 魚池鄉'),
    ('alishan',   '阿里山',     23.5100, 120.8030, '中華民國 · 嘉義縣 · 阿里山鄉'),
    ('kenting',   '墾丁',       21.9450, 120.7970, '中華民國 · 屏東縣 · 恆春鎮'),
]

REJECT = re.compile(
    r'(logo|icon|emblem|seal|map|karte|mapa|地図|地圖|flag|coat[_ ]of[_ ]arms|diagram'
    r'|chart|plaque|signpost|banner|qr[_ ]code|screenshot|blank|placeholder)', re.I)
FROM_SVG = re.compile(r'\.svgx?\.(png|jpe?g)$', re.I)
OK_EXT = re.compile(r'\.(jpe?g|png|webp)$', re.I)


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read()


def api(host, params):
    p = dict(action='query', format='json', formatversion='2', **params)
    return json.loads(get('https://%s/w/api.php?%s' % (host, urllib.parse.urlencode(p))))


def strip_html(s):
    s = re.sub(r'<[^>]*>', ' ', s or '')
    s = re.sub(r'&[a-z]+;|&#\d+;', ' ', s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip()


def clamp(s, n):
    return s if len(s) <= n else re.sub(r'[，,、。;；\s]\S*$', '', s[:n]) + '…'


def file_name_of(url):
    seg = urllib.parse.unquote(url.split('?')[0].split('/')[-1])
    return re.sub(r'^\d+px-', '', seg)


def looks_like_photo(url):
    n = file_name_of(url)
    return not FROM_SVG.search(n) and not REJECT.search(n) and OK_EXT.search(n)


def tidy(s):
    c = re.sub(r'^(?:\d{2,8}[-_ ]+){2,}', '', str(s))
    c = re.sub(r'^(?:IMG|DSC|DSCN|PICT|P)[-_ ]?\d+[-_ ]*', '', c, flags=re.I)
    c = c.replace('_', ' ')
    c = re.sub(r'\s*-\s*panoramio\s*(\(\d+\))?\s*$', '', c, flags=re.I)
    c = re.sub(r'\s{2,}', ' ', c).strip()
    return c if len(c) >= 3 else str(s).replace('_', ' ').strip()


def display_title(title, extract):
    """與 js/photos.js 的 displayTitle 同規則：zh 條目標題可能是簡體或非台灣譯名，
    改用已轉換過的 extract 開頭；只在字數相同、用字不同時採用。"""
    head = re.split(r"[（(，,。、：:；;]", extract or "")[0].strip()
    if not head or head == title:
        return title
    return head if len(head) == len(title) else title


def from_wikipedia(lat, lon):
    d = api('zh.wikipedia.org', dict(
        generator='geosearch', ggscoord='%s|%s' % (lat, lon), ggsradius='10000',
        ggslimit='20', prop='pageimages|extracts|coordinates', colimit='max',
        piprop='thumbnail', pithumbsize=str(THUMB_W),
        exintro='1', explaintext='1', exchars='620', exlimit='20'))
    out = []
    for p in d.get('query', {}).get('pages', []):
        t = p.get('thumbnail')
        if not t or t.get('width', 0) < 640:
            continue
        if t['width'] / max(1, t['height']) < 0.5 or not looks_like_photo(t['source']):
            continue
        co = (p.get('coordinates') or [{}])[0]
        out.append(dict(
            kind='wikipedia', kicker='附近景點',
            title=display_title(p['title'], p.get('extract', '')),
            caption=clamp(strip_html(p.get('extract', '')), 420) or '（此條目尚無摘要）',
            credit='維基百科（中文）· CC BY-SA',
            src=t['source'],
            sourceUrl='https://zh.wikipedia.org/?curid=%d' % p['pageid'],
            lat=co.get('lat'), lon=co.get('lon')))
    return out


def from_commons(lat, lon):
    d = api('commons.wikimedia.org', dict(
        generator='geosearch', ggsnamespace='6', ggscoord='%s|%s' % (lat, lon),
        ggsradius='10000', ggslimit='60', prop='imageinfo|coordinates',
        coprimary='all', colimit='max',
        iiprop='url|extmetadata|dimensions|mime', iiurlwidth=str(THUMB_W),
        iiextmetadatalanguage='zh',
        iiextmetadatafilter='ImageDescription|ObjectName|Artist|Credit|LicenseShortName|DateTimeOriginal'))
    out = []
    for p in d.get('query', {}).get('pages', []):
        ii = (p.get('imageinfo') or [None])[0]
        if not ii or not ii.get('thumburl'):
            continue
        if ii.get('mime') not in ('image/jpeg', 'image/png', 'image/webp'):
            continue
        if ii.get('width', 0) < 900 or ii['width'] / max(1, ii['height']) < 0.95:
            continue
        if not looks_like_photo(p['title']):
            continue
        m = ii.get('extmetadata', {})
        val = lambda k: strip_html((m.get(k) or {}).get('value', ''))
        name = val('ObjectName') or OK_EXT.sub('', file_name_of(p['title'][5:]))
        year = re.search(r'\d{4}', val('DateTimeOriginal') or '')
        by = val('Artist') or val('Credit')
        co = (p.get('coordinates') or [{}])[0]
        out.append(dict(
            kind='commons', kicker='在地影像', title=clamp(tidy(name), 60),
            caption=clamp(val('ImageDescription'), 380)
                    or '這張照片由攝影者標註於此座標附近，未附文字說明。',
            credit=' · '.join(x for x in [
                ('攝影：' + clamp(by, 60)) if by else '',
                year.group(0) if year else '',
                val('LicenseShortName') or '公開授權'] if x),
            src=ii['thumburl'],
            sourceUrl=ii.get('descriptionurl', ''),
            lat=co.get('lat'), lon=co.get('lon')))
    return out


def interleave(wiki, commons):
    out = []
    while wiki or commons:
        if wiki:
            out.append(wiki.pop(0))
        if commons:
            out.append(commons.pop(0))
    return out


def cached_download(url):
    if not os.path.isdir(CACHE):
        os.makedirs(CACHE)
    key = re.sub(r'[^A-Za-z0-9._-]', '_', file_name_of(url))[-120:]
    path = os.path.join(CACHE, key)
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return f.read()
    data = get(url)
    with open(path, 'wb') as f:
        f.write(data)
    return data


def mime_of(url):
    n = file_name_of(url).lower()
    if n.endswith('.png'):
        return 'image/png'
    if n.endswith('.webp'):
        return 'image/webp'
    return 'image/jpeg'


def main():
    baked = []
    total = 0

    for key, name, lat, lon, area in PLACES:
        print('抓取 %s …' % name)
        wiki, commons = from_wikipedia(lat, lon), from_commons(lat, lon)

        seen, uniq = set(), []
        for it in interleave(wiki, commons):
            k = file_name_of(it['src']).lower()
            if k in seen or it['title'].lower() in seen:
                continue
            seen.add(k)
            seen.add(it['title'].lower())
            uniq.append(it)

        photos, used = [], 0
        for it in uniq:
            if len(photos) >= PHOTOS_PER_PLACE or used >= BYTES_PER_PLACE:
                break
            if total + used >= TOTAL_BUDGET:
                break
            try:
                blob = cached_download(it['src'])
            except Exception as e:
                print('   略過 %s（%s）' % (it['title'][:30], e))
                continue
            if len(blob) > 420_000:            # 單張太大就不要，免得吃掉整個預算
                continue
            used += len(blob)
            it = dict(it)
            src = it.pop('src')
            it['image'] = 'data:%s;base64,%s' % (mime_of(src), base64.b64encode(blob).decode())
            photos.append(it)

        total += used
        print('   %d 張，%.1f KB' % (len(photos), used / 1024))
        baked.append(dict(key=key, name=name, lat=lat, lon=lon, area=area, photos=photos))

    print('合計原始 %.1f MB' % (total / 1024 / 1024))

    write_demo(baked)


def write_demo(baked):
    """用 build.py 打包成單檔，再把烘焙資料塞在模組腳本之前先執行。"""
    import build

    payload = json.dumps(baked, ensure_ascii=False, separators=(',', ':'))
    payload = payload.replace('</', chr(92) + 'u003c/')      # 避免提早關掉 <script>

    html = build.bundle()
    inject = '<script>window.__BAKED__=' + payload + ';</script>' + chr(10)
    marker = '<script type="module">'
    if marker not in html:
        sys.exit('打包結果裡找不到模組腳本')
    html = html.replace(marker, inject + marker, 1)

    html = html.replace('<title>途中 Wayfarer · GPS 風景輪播</title>',
                        '<title>途中 Wayfarer</title>', 1)

    out_dir = os.path.dirname(OUT)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with io.open(OUT, 'w', encoding='utf-8', newline=chr(10)) as f:
        f.write(html)
    print('寫出 %s（%.1f MB）' % (os.path.relpath(OUT, ROOT), os.path.getsize(OUT) / 1024 / 1024))
    with io.open(os.path.join(ROOT, 'demo-data.json'), 'w', encoding='utf-8') as f:
        json.dump(baked, f, ensure_ascii=False)
    print('已寫出 demo-data.json')


if __name__ == '__main__':
    # 已經有 demo-data.json 就直接重組，不重抓（改前端程式碼時用）
    if '--repack' in sys.argv:
        with io.open(os.path.join(ROOT, 'demo-data.json'), encoding='utf-8') as f:
            write_demo(json.load(f))
    else:
        main()
