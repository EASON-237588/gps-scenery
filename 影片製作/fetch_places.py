"""為精選景點抓候選照片（沿用專案 build-demo.py 的查詢與篩選規則），存到 _work/cand，並拼出挑選用總覽圖。
用法：python fetch_places.py            抓取＋產生總覽
      python fetch_places.py --sheets   只重畫總覽
不會動到專案原有的 .demo-cache 與 dist。"""
import importlib.util, io, json, os, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CAND = os.path.join(HERE, "_work", "cand"); os.makedirs(CAND, exist_ok=True)
spec = importlib.util.spec_from_file_location("bd", os.path.join(ROOT, "build-demo.py"))
bd = importlib.util.module_from_spec(spec); sys.path.insert(0, ROOT); spec.loader.exec_module(bd)
bd.CACHE = os.path.join(HERE, "_work", "cache")
bd.UA = "WayfarerDemoVideo/1.0 (personal non-commercial demo; python-urllib)"

# (key, 名稱, 緯度, 經度, 地區字串)  ── 順序即影片順序
DOMESTIC = [
 ("qingshui", "清水斷崖", 24.2147, 121.6903, "中華民國 · 花蓮縣 · 秀林鄉"),
 ("shakadang", "太魯閣砂卡礑", 24.1631, 121.6127, "中華民國 · 花蓮縣 · 秀林鄉"),
 ("qixingtan", "七星潭", 24.0300, 121.6270, "中華民國 · 花蓮縣 · 新城鄉"),
 ("sanxiantai", "三仙台", 23.1210, 121.4085, "中華民國 · 臺東縣 · 成功鎮"),
 ("lanyu", "蘭嶼", 22.0560, 121.5600, "中華民國 · 臺東縣 · 蘭嶼鄉"),
 ("liuqiu", "小琉球花瓶岩", 22.3452, 120.3608, "中華民國 · 屏東縣 · 琉球鄉"),
 ("eluanbi", "鵝鑾鼻燈塔", 21.9020, 120.8527, "中華民國 · 屏東縣 · 恆春鎮"),
 ("maobitou", "墾丁貓鼻頭", 21.9253, 120.7447, "中華民國 · 屏東縣 · 恆春鎮"),
 ("sunmoon", "日月潭慈恩塔", 23.8500, 120.9322, "中華民國 · 南投縣 · 魚池鄉"),
 ("alishan", "阿里山", 23.5100, 120.8030, "中華民國 · 嘉義縣 · 阿里山鄉"),
 ("yushan", "玉山", 23.4700, 120.9570, "中華民國 · 南投縣 · 信義鄉"),
 ("hehuan", "合歡山", 24.1426, 121.2713, "中華民國 · 南投縣 · 仁愛鄉"),
 ("qingjing", "清境農場", 24.0500, 121.1600, "中華民國 · 南投縣 · 仁愛鄉"),
 ("gaomei", "高美濕地", 24.3125, 120.5497, "中華民國 · 臺中市 · 清水區"),
 ("jiufen", "九份", 25.1099, 121.8444, "中華民國 · 新北市 · 瑞芳區"),
 ("shifen", "十分瀑布", 25.0420, 121.7745, "中華民國 · 新北市 · 平溪區"),
 ("yehliu", "野柳地質公園", 25.2087, 121.6906, "中華民國 · 新北市 · 萬里區"),
 ("taipei101", "台北 101", 25.0339, 121.5645, "中華民國 · 臺北市 · 信義區"),
 ("lotus", "高雄龍虎塔", 22.6830, 120.2960, "中華民國 · 高雄市 · 左營區"),
 ("anping", "安平古堡", 23.0010, 120.1600, "中華民國 · 臺南市 · 安平區"),
 ("qimei", "七美雙心石滬", 23.2000, 119.4300, "中華民國 · 澎湖縣 · 七美鄉"),
 ("wuling", "武陵農場", 24.3600, 121.3100, "中華民國 · 臺中市 · 和平區"),
]
WORLD = [
 ("fuji", "富士山", 35.3606, 138.7274, "日本 · 山梨縣 · 富士河口湖町"),
 ("kiyomizu", "京都清水寺", 34.9949, 135.7850, "日本 · 京都府 · 京都市"),
 ("eiffel", "艾菲爾鐵塔", 48.8584, 2.2945, "法國 · 巴黎"),
 ("colosseum", "羅馬競技場", 41.8902, 12.4922, "義大利 · 羅馬"),
 ("sagrada", "聖家堂", 41.4036, 2.1744, "西班牙 · 巴塞隆納"),
 ("sydney", "雪梨歌劇院", -33.8568, 151.2153, "澳洲 · 新南威爾斯州 · 雪梨"),
 ("machu", "馬丘比丘", -13.1631, -72.5450, "秘魯 · 庫斯科大區"),
 ("canyon", "大峽谷", 36.1070, -112.1130, "美國 · 亞利桑那州"),
 ("liberty", "自由女神像", 40.6892, -74.0445, "美國 · 紐約州 · 紐約"),
 ("taj", "泰姬瑪哈陵", 27.1751, 78.0421, "印度 · 北方邦 · 阿格拉"),
 ("angkor", "吳哥窟", 13.4125, 103.8670, "柬埔寨 · 暹粒省"),
 ("burj", "哈里發塔", 25.1972, 55.2744, "阿拉伯聯合大公國 · 杜拜"),
]
ALL = DOMESTIC + WORLD
PER = 8

def candidates(key, lat, lon):
    p = os.path.join(CAND, key + ".json")
    if os.path.exists(p): return json.load(open(p, encoding="utf-8"))
    import time, urllib.error
    def retry(fn):
        for n in range(6):
            try: return fn(lat, lon)
            except urllib.error.HTTPError as e:
                if e.code != 429: raise
                time.sleep(20 * (n + 1))
        raise RuntimeError("一直被限流")
    wiki = retry(bd.from_wikipedia); time.sleep(1); commons = retry(bd.from_commons); time.sleep(1)
    seen, uniq = set(), []
    for it in bd.interleave(wiki, commons):
        k = bd.file_name_of(it["src"]).lower()
        if k in seen or it["title"].lower() in seen: continue
        seen.add(k); seen.add(it["title"].lower()); uniq.append(it)
    out = []
    for it in uniq:
        if len(out) >= PER: break
        try:
            blob = bd.cached_download(it["src"]); time.sleep(0.3)
        except Exception as e: print("   略過", it["title"][:24], e); time.sleep(5); continue
        if len(blob) > 600_000: continue
        f = os.path.join(CAND, f"{key}_{len(out)}.jpg"); open(f, "wb").write(blob)
        it = dict(it); it["file"] = f; out.append(it)
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return out

def sheet(names, out):
    tw, th = 190, 250; rows = len(names)
    im = Image.new("RGB", (PER * tw + 130, rows * th), (20, 20, 20)); d = ImageDraw.Draw(im)
    f = ImageFont.truetype("C:/Windows/Fonts/msjhbd.ttc", 17); f2 = ImageFont.truetype("C:/Windows/Fonts/msjh.ttc", 12)
    for r, (key, name, *_ ) in enumerate(names):
        d.text((6, r * th + 6), name, font=f, fill=(255, 220, 90)); d.text((6, r * th + 30), key, font=f2, fill=(180, 180, 180))
        c = json.load(open(os.path.join(CAND, key + ".json"), encoding="utf-8"))
        for n, it in enumerate(c):
            t = Image.open(it["file"]).convert("RGB"); t.thumbnail((tw - 4, th - 22)); im.paste(t, (130 + n * tw, r * th))
            d.rectangle((130 + n * tw, r * th, 130 + n * tw + 24, r * th + 22), fill=(0, 0, 0)); d.text((135 + n * tw, r * th + 2), str(n), font=f, fill=(255, 255, 255))
            d.text((130 + n * tw + 2, r * th + th - 18), it["title"][:14], font=f2, fill=(220, 220, 220))
    im.save(out)

if __name__ == "__main__":
    if "--sheets" not in sys.argv:
        for key, name, lat, lon, area in ALL:
            c = candidates(key, lat, lon); print(f"{name} {len(c)} 張", flush=True)
    for i in range(0, len(ALL), 4):
        sheet(ALL[i:i + 4], os.path.join(HERE, "_work", f"pick_{i // 4 + 1}.png"))
    print("總覽已輸出")
