"""用維基百科『條目名稱』直接取各景點的代表圖（中文、英文各一），放在候選清單最前面，再接座標附近的備選。
用法：python fetch_titles.py   →   更新 _work/cand/*.json 並重畫 _work/pick_*.png"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_places as fp
bd = fp.bd

TITLES = {
 "qingshui": ("清水斷崖", "Qingshui Cliff"), "shakadang": ("砂卡礑步道", "Shakadang Trail"), "qixingtan": ("七星潭", "Qixingtan"),
 "sanxiantai": ("三仙台", "Sanxiantai"), "lanyu": ("蘭嶼", "Orchid Island"), "liuqiu": ("小琉球", "Xiaoliuqiu"),
 "eluanbi": ("鵝鑾鼻燈塔", "Eluanbi Lighthouse"), "maobitou": ("貓鼻頭", "Maobitou"), "sunmoon": ("慈恩塔", "Sun Moon Lake"),
 "alishan": ("阿里山森林鐵路", "Alishan Forest Railway"), "yushan": ("玉山", "Yushan"), "hehuan": ("合歡山", "Hehuan Mountain"),
 "qingjing": ("清境農場", "Cingjing Farm"), "gaomei": ("高美濕地", "Gaomei Wetlands"), "jiufen": ("九份", "Jiufen"),
 "shifen": ("十分瀑布", "Shifen Waterfall"), "yehliu": ("野柳地質公園", "Yehliu Geopark"), "taipei101": ("台北101", "Taipei 101"),
 "anping": ("安平古堡", "Fort Zeelandia (Taiwan)"), "qimei": ("雙心石滬", "Cimei"),
 "fuji": ("富士山", "Mount Fuji"), "kiyomizu": ("清水寺", "Kiyomizu-dera"), "eiffel": ("艾菲爾鐵塔", "Eiffel Tower"),
 "colosseum": ("羅馬競技場", "Colosseum"), "sydney": ("雪梨歌劇院", "Sydney Opera House"), "machu": ("馬丘比丘", "Machu Picchu"),
 "canyon": ("大峽谷", "Grand Canyon"), "liberty": ("自由女神像", "Statue of Liberty"), "taj": ("泰姬瑪哈陵", "Taj Mahal"),
 "angkor": ("吳哥窟", "Angkor Wat"),
}
bd.UA = "WayfarerDemoVideo/1.0 (personal non-commercial demo; python-urllib)"

def one(host, title, tag):
    for n in range(6):
        try:
            d = bd.api(host, dict(prop="pageimages|extracts", titles=title, redirects="1", piprop="thumbnail", pithumbsize="1100",
                                  exintro="1", explaintext="1", exchars="620"))
            break
        except urllib.error.HTTPError as e:
            if e.code != 429: return None
            time.sleep(15 * (n + 1))
    else: return None
    p = (d.get("query", {}).get("pages") or [{}])[0]; t = p.get("thumbnail")
    if not t or t.get("width", 0) < 640 or not bd.looks_like_photo(t["source"]): return None
    return dict(kind="wikipedia", kicker="附近景點", title=p.get("title", title), caption=bd.clamp(bd.strip_html(p.get("extract", "")), 420) or "（此條目尚無摘要）",
                credit=("維基百科（中文）" if host.startswith("zh") else "維基百科（英文）") + " · CC BY-SA", src=t["source"],
                sourceUrl=f"https://{host}/?curid={p.get('pageid')}", lat=None, lon=None)

if __name__ == "__main__":
    bd.CACHE = os.path.join(fp.HERE, "_work", "cache")
    for key, (zh, en) in TITLES.items():
        pj = os.path.join(fp.CAND, key + ".json"); old = json.load(open(pj, encoding="utf-8")) if os.path.exists(pj) else []
        old = [o for o in old if not o.get("byTitle")]
        got = []
        for host, t in (("zh.wikipedia.org", zh), ("en.wikipedia.org", en)):
            it = one(host, t, key); time.sleep(0.8)
            if it and all(bd.file_name_of(it["src"]).lower() != g.get("name", "") for g in got):
                try: blob = bd.cached_download(it["src"])
                except Exception as e: print("  下載失敗", e); continue
                f = os.path.join(fp.CAND, f"{key}_t{len(got)}.jpg"); open(f, "wb").write(blob)
                it["name"] = bd.file_name_of(it["src"]).lower(); it["file"] = f; it["byTitle"] = True; del it["src"]; got.append(it)
        # 舊的備選保留（它們的 src 已不在，只留 file 與資料）
        for o in old: o.pop("src", None)
        json.dump(got + old, open(pj, "w", encoding="utf-8"), ensure_ascii=False)
        print(key, "標題圖", len(got), "備選", len(old), flush=True)
    fp.PER = 10
    names = [x for x in fp.ALL if x[0] in TITLES]
    for i in range(0, len(names), 3):
        fp.sheet(names[i:i + 3], os.path.join(fp.HERE, "_work", f"pick_{i // 3 + 1}.png"))
    print("總覽已輸出")
