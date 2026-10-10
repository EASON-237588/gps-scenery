"""途中 Wayfarer 手機直式示範影片（720x1280，3 分鐘內）。
錄的是專案真實程式的「手機直向版面」；景點換成精選名勝（照片預先內嵌，切換是瞬間）。
字幕 ＝ 口白同一句話。不修改專案原有檔案，產物全部在「影片製作」資料夾。

  python make_vertical.py --bake      用 選圖.json 組出 site/index.html（內嵌精選照片）
  python make_vertical.py --record    錄畫面（只錄視窗內容區，不錄桌面）
  python make_vertical.py --frames    抽檢查畫面
  python make_vertical.py --build     依 腳本2.json 與自動產生的景點口白，剪成成品
"""
import asyncio, base64, ctypes, hashlib, json, math, os, re, subprocess, sys, time
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont
import edge_tts, imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
WORK = os.path.join(HERE, "_work"); CAND = os.path.join(WORK, "cand"); os.makedirs(os.path.join(WORK, "audio"), exist_ok=True)
SITE = os.path.join(HERE, "site"); os.makedirs(SITE, exist_ok=True)
RAW = os.path.join(WORK, "raw_v.mkv"); MARK = os.path.join(WORK, "marks_v.json")
PICKS = os.path.join(HERE, "選圖.json"); SCRIPT2 = os.path.join(HERE, "腳本2.json")
OUT = os.path.join(HERE, "途中 Wayfarer 手機直式示範.mp4")
FF = imageio_ffmpeg.get_ffmpeg_exe()
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = os.path.join(os.environ["TEMP"], "wf_chrome")
PORT = 8124; BASE = f"http://localhost:{PORT}/index.html"
W, H, FPS = 720, 1280, 24
VOICE = "zh-TW-HsiaoChenNeural"; RATE = "+30%"
STEP = 5.6          # 錄影時每個景點停留秒數（之後依口白剪短）
LOAD = 5.0          # 開頁後等待秒數（內嵌資料，載入很快）
GAP = 0.2
OFF = 2.2           # 錄影檔時間軸比記錄的時間點晚的秒數（實測：偵測到的換景時間 − 預期時間）

sys.path.insert(0, HERE)
import fetch_places as fp
DOM = ["qingshui", "shakadang", "qixingtan", "sanxiantai", "lanyu", "liuqiu", "eluanbi", "maobitou", "sunmoon", "alishan",
       "yushan", "hehuan", "qingjing", "gaomei", "jiufen", "shifen", "yehliu", "taipei101", "qimei"]
WLD = ["fuji", "kiyomizu", "eiffel", "colosseum", "sydney", "machu", "canyon", "liberty", "taj", "angkor"]
INFO = {k: (n, la, lo, ar) for k, n, la, lo, ar in fp.ALL}
for _k, _n in {"liuqiu": "小琉球", "maobitou": "墾丁", "sunmoon": "日月潭", "alishan": "阿里山", "eluanbi": "鵝鑾鼻", "qimei": "七美雙心石滬"}.items():
    INFO[_k] = (_n,) + INFO[_k][1:]

# ---------- 組展示版 ----------
def bake():
    sys.path.insert(0, ROOT); import build
    picks = json.load(open(PICKS, encoding="utf-8")); desc = picks.get("_desc", {}); baked = []
    for k in DOM + WLD:
        c = json.load(open(os.path.join(CAND, k + ".json"), encoding="utf-8"))[picks[k]]
        n, la, lo, ar = INFO[k]
        it = {x: c[x] for x in ("kind", "kicker", "title", "caption", "credit", "sourceUrl", "lat", "lon")}
        it["title"] = picks["_titles"].get(k, n)
        it["caption"] = desc.get(k, it["caption"])
        it["credit"] = "照片：維基百科／維基共享資源 · 公開授權（詳見來源頁）"
        it["image"] = "data:image/jpeg;base64," + base64.b64encode(open(c["file"], "rb").read()).decode()
        baked.append(dict(key=k, name=n, lat=la, lon=lo, area=ar, photos=[it]))
    # 行駛示範：太魯閣牌樓往西進峽谷的一條真實路線（照片座標為維基共享資源上標註的真實位置）
    rc = json.load(open(os.path.join(CAND, "route.json"), encoding="utf-8")); route = []
    for idx, ttl, cap in ((33, "太魯閣牌樓", "中橫公路太魯閣段的入口牌樓，過了這裡就進入峽谷。"),
                          (10, "峽谷口的紅色橋樑", "進入峽谷後的紅色橋樑，下方是寬闊的溪谷。"),
                          (7, "砂卡礑大橋", "跨越砂卡礑溪口的紅色拱橋。"),
                          (19, "砂卡礑隧道", "公路由這裡鑽進山壁，穿過砂卡礑隧道。"),
                          (3, "砂卡礑溪", "砂卡礑溪的碧綠溪水，是太魯閣最受歡迎的溪谷之一。")):
        c = rc[idx]; it = {x: c[x] for x in ("kind", "kicker", "title", "caption", "credit", "sourceUrl", "lat", "lon")}
        it["title"], it["caption"] = ttl, cap
        it["image"] = "data:image/jpeg;base64," + base64.b64encode(open(c["file"], "rb").read()).decode(); route.append(it)
    baked.append(dict(key="route", name="太魯閣", lat=24.1560, lon=121.6200, area="中華民國 · 花蓮縣 · 秀林鄉", photos=route))
    payload = json.dumps(baked, ensure_ascii=False, separators=(",", ":")).replace("</", chr(92) + "u003c/")
    boot = "依你的 GPS 座標，尋找附近的旅遊勝地與風光，每 15 秒換一張照片並附上簡介。橫向、直向都可以。"
    inject = ("<script>window.__BAKED__=" + payload + ";(function(){var q=new URLSearchParams(location.search);var s=+q.get('start')||0;"
              "var o=q.get('only');if(o)window.__BAKED__=window.__BAKED__.filter(function(p){return p.key===o});var b=window.__BAKED__;if(s)window.__BAKED__=b.slice(s).concat(b.slice(0,s));"
              "addEventListener('keydown',function(e){if(e.key==='ArrowDown'){var x=document.getElementById('btn-place');if(x)x.click()}});"
              "setTimeout(function(){var m=document.getElementById('boot-msg');if(m)m.textContent=" + json.dumps(boot, ensure_ascii=False) + ";"
              "var sk=document.getElementById('boot-skip');if(sk)sk.style.display='none'},400);})();</script>\n")
    html = build.bundle(); mk = '<script type="module">'
    assert mk in html; html = html.replace(mk, inject + mk, 1).replace("<title>途中 Wayfarer · GPS 風景輪播</title>", "<title>途中 Wayfarer</title>", 1)
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8", newline="\n").write(html)
    print("已輸出 site/index.html", round(os.path.getsize(os.path.join(SITE, "index.html")) / 1048576, 1), "MB，景點", len(baked))

# ---------- 錄影 ----------
VK = {"right": 0x27, "left": 0x25, "space": 0x20, "n": 0x28}
def press(k):
    u = ctypes.windll.user32; u.keybd_event(VK[k], 0, 0, 0); time.sleep(0.05); u.keybd_event(VK[k], 0, 2, 0)

def focus():
    """把『途中 Wayfarer』視窗拉到最前面，讓按鍵送得進去"""
    u = ctypes.windll.user32; h = u.FindWindowW(None, "途中 Wayfarer")
    if not h: return False
    u.keybd_event(0x12, 0, 0, 0); u.keybd_event(0x12, 0, 2, 0)      # 先按一下 Alt，繞過前景鎖
    u.ShowWindow(h, 9); u.SetForegroundWindow(h); time.sleep(0.3)
    return u.GetForegroundWindow() == h

def kill_chrome():
    subprocess.run(["powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*wf_chrome*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"], capture_output=True)

def grab(path):
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "gdigrab", "-framerate", "5", "-offset_x", "0", "-offset_y", "0",
                    "-video_size", "3840x2160", "-i", "desktop", "-frames:v", "1", path], check=True)

def launch(qs):
    subprocess.Popen([CHROME, "--app=" + BASE + qs, "--window-size=508,912", "--window-position=0,0", f"--user-data-dir={PROFILE}",
                      "--no-first-run", "--disable-notifications", "--disable-infobars", "--disable-session-crashed-bubble"])

def measure():
    """有／無視窗兩張截圖相減，量出內容區，再裁成 9:16"""
    kill_chrome(); time.sleep(1.5); bg = os.path.join(WORK, "m_bg.png"); win = os.path.join(WORK, "m_win.png"); grab(bg)
    launch("?lat=24.2147&lon=121.6903&auto=1"); time.sleep(7); grab(win); kill_chrome()
    a = np.array(Image.open(bg).convert("RGB")).astype(int); b = np.array(Image.open(win).convert("RGB")).astype(int)
    d = np.abs(a - b).sum(axis=2) > 60
    xs = np.where(d[1000, :1500])[0]; x0, x1 = xs.min(), xs.max()
    xm = (x0 + x1) // 2; ys = np.where(d[:, xm])[0]; ys = ys[ys < 2100]; y0, y1 = ys.min(), ys.max()
    tb = 0
    for y in range(y0, y0 + 160):
        if b[y, xm].sum() < 250 and b[y - 2, xm].sum() >= 250: tb = y - y0; break
    cx, cy, cw, ch = x0 + 1, y0 + tb + 1, x1 - x0 - 1, y1 - y0 - tb - 1
    w = min(cw, int(ch * 9 / 16)); h = int(w * 16 / 9)
    cx += (cw - w) // 2; cw, ch = w // 2 * 2, h // 2 * 2
    print("視窗", (x0, y0, x1, y1), "標題列", tb, "→ 裁切", (cx, cy, cw, ch), flush=True)
    return int(cx), int(cy), int(cw), int(ch)

def record(only=None):
    import http.server
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--directory", SITE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        cx, cy, cw, ch = measure(); marks = json.load(open(MARK)) if only and os.path.exists(MARK) else {}
        marks["crop"] = [cx, cy, cw, ch]
        rawf = RAW.replace(".mkv", f"_{only}.mkv") if only else RAW
        rec = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "gdigrab", "-framerate", str(FPS), "-draw_mouse", "0",
            "-offset_x", str(cx), "-offset_y", str(cy), "-video_size", f"{cw}x{ch}", "-i", "desktop",
            "-vf", f"scale={W}:{H}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p", rawf], stdin=subprocess.PIPE)
        time.sleep(2.0); t0 = time.time()
        def scene(name, qs, length, keys=(), cycle=0):
            if only and name != only: return
            kill_chrome(); time.sleep(0.8); launch(qs); st = time.time(); marks[name] = st - t0 + LOAD
            if only: marks[name + "_file"] = rawf
            time.sleep(3.0); print("  焦點", focus(), flush=True)
            end = st + LOAD + length + 1.0; ev = sorted([(LOAD + t, k) for t, k in keys] + [(LOAD + STEP * i, "n") for i in range(1, cycle)])
            while time.time() < end:
                el = time.time() - st
                while ev and el >= ev[0][0]: press(ev.pop(0)[1])
                time.sleep(0.05)
            print(name, "完成", round(time.time() - t0, 1), flush=True)
        a = INFO[DOM[0]]; scene("boot", "", 9)
        scene("dom", f"?start=0&lat={a[1]}&lon={a[2]}&auto=1", STEP * len(DOM), cycle=len(DOM))
        w0 = DOM and fp.ALL[[x[0] for x in fp.ALL].index(WLD[0])]
        # 世界組：把資料轉到 WLD[0] 起頭（start= 以烘焙陣列序號計）
        idx = len(DOM)
        scene("wld", f"?start={idx}&lat={w0[2]}&lon={w0[3]}&auto=1", STEP * len(WLD), cycle=len(WLD))
        scene("drive", "?lat=24.15226&lon=121.62448&auto=1&drive=321&kmh=100&only=route", 38, keys=[(10, "right"), (20, "right"), (30, "right")])
    finally:
        kill_chrome(); rec.stdin.write(b"q"); rec.stdin.flush(); rec.wait(timeout=60); srv.terminate()
    json.dump({k: (list(map(int, v)) if isinstance(v, (list, tuple)) else (v if isinstance(v, str) else float(v))) for k, v in marks.items()}, open(MARK, "w"))

def frames():
    m = json.load(open(MARK)); os.makedirs(os.path.join(WORK, "chk"), exist_ok=True)
    def sheet(name, start, length, step, cols):
        out = os.path.join(WORK, "chk", f"v_{name}.png")
        subprocess.run([FF, "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{length}", "-i", RAW,
                        "-vf", f"fps=1/{step},scale=240:-1,tile={cols}x{math.ceil(length / step / cols)}", "-frames:v", "1", out])
    sheet("boot", m["boot"], 14, 2, 7); sheet("drive", m["drive"] - 4, 44, 2.5, 9)
    sheet("dom1", m["dom"], STEP * 10, STEP, 10); sheet("dom2", m["dom"] + STEP * 10, STEP * 10, STEP, 10); sheet("wld", m["wld"], STEP * 10, STEP, 10)
    print("已輸出", os.path.join(WORK, "chk"))

# ---------- 剪接 ----------
def font(s, b=True): return ImageFont.truetype("C:/Windows/Fonts/" + ("msjhbd.ttc" if b else "msjh.ttc"), s)
TEAL, WHT, DIM = (111, 211, 192), (240, 244, 248), (140, 155, 172)
def card(sid):
    im = Image.new("RGB", (W, H), (5, 7, 12)); d = ImageDraw.Draw(im)
    if sid == "free":
        d.text((W // 2, 250), "不需要特別的技術費用", font=font(46), fill=WHT, anchor="mm")
        d.text((W // 2, 450), "0 元", font=font(190), fill=TEAL, anchor="mm")
        for n, t in enumerate(["定位：手機現有的 GPS", "照片簡介：維基百科、", "維基共享資源（免費公開）", "網頁：免主機、免後端"]):
            d.text((W // 2, 640 + n * 62), t, font=font(30, False), fill=WHT, anchor="mm")
    else:
        d.text((50, 130), "照片與文字來源", font=font(44), fill=TEAL)
        rows = ["維基百科（中文）", "　簡介文字　CC BY-SA", "維基共享資源", "　公開授權照片", "　授權標示於畫面右下", "BigDataCloud", "　反向地理編碼（免金鑰）", "", "每張照片都附：", "攝影者、年份、授權、", "以及原始頁面連結。"]
        for n, t in enumerate(rows): d.text((50, 240 + n * 58), t, font=font(30, False), fill=WHT)
        d.text((50, 1000), "途中 Wayfarer　製作中", font=font(38), fill=TEAL)
    p = os.path.join(WORK, "v_" + sid + ".png"); im.save(p); return p

def wrapn(text, n=13): return [text[i:i + n] for i in range(0, len(text), n)] or [""]
def subpng(name, text):
    f = font(36); lines = wrapn(text); tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    tw = max(tmp.textlength(l, font=f) for l in lines); h = 26 + 50 * len(lines)
    im = Image.new("RGBA", (int(tw) + 60, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, h - 1), 14, fill=(0, 0, 0, 185))
    for i, l in enumerate(lines): d.text((im.width // 2, 13 + 50 * i + 25), l, font=f, fill=(255, 255, 255), anchor="mm")
    p = os.path.join(WORK, "vs_" + name + ".png"); im.save(p); return p

def probe(p):
    r = subprocess.run([FF, "-hide_banner", "-i", p], capture_output=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr); return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
async def tts_one(text, p):
    if not os.path.exists(p): await edge_tts.Communicate(text, VOICE, rate=RATE).save(p)
def sentences(t): return [s for s in re.findall(r"[^。！？]+[。！？]?", t) if s.strip()]

def coord_text(lat, lon):
    return f"{'北' if lat >= 0 else '南'}緯 {abs(lat):.1f}，{'東' if lon >= 0 else '西'}經 {abs(lon):.1f}"

def make_clip(cid, vin, lines, minlen=0.0, y_sub=690):
    """lines: [{"at":秒,"t":文字}]；回傳 (檔案, 長度)"""
    t = 0.0; items = []
    for ln in lines:
        for i, s in enumerate(sentences(ln["t"])):
            at = max(t, ln.get("at", 0.0)) if i == 0 else t
            h = hashlib.md5((VOICE + RATE + s).encode("utf-8")).hexdigest()[:10]; mp3 = os.path.join(WORK, "audio", f"v{h}.mp3")
            asyncio.run(tts_one(s, mp3)); wav = mp3[:-4] + ".t.wav"
            if not os.path.exists(wav):   # 轉成 wav 並切掉頭尾靜音
                trim = "silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.04,areverse,silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.08,areverse"
                subprocess.run([FF, "-y", "-loglevel", "error", "-i", mp3, "-af", trim, "-ar", "44100", "-ac", "2", wav], check=True)
            d = probe(wav)
            items.append((at, d, s, wav)); t = at + d + GAP
    total = max(t + 0.15, minlen)
    ins, fl = [], []
    for n, (at, d, s, wav) in enumerate(items): ins += ["-i", wav]; fl.append(f"[{n}:a]adelay={int(at * 1000)}|{int(at * 1000)}[a{n}]")
    mix = "".join(f"[a{n}]" for n in range(len(items))) + f"amix=inputs={len(items)}:normalize=0,apad[am]"
    awav = os.path.join(WORK, f"va_{cid}.wav")
    subprocess.run([FF, "-y", "-loglevel", "error", *ins, "-filter_complex", ";".join(fl + [mix]), "-map", "[am]", "-t", f"{total:.3f}", "-ar", "44100", "-ac", "2", awav], check=True)
    subs = []
    for at, d, s, _ in items:
        ch = [c for c in re.split(r"(?<=[，、；：])", s) if c.strip()]; tot = sum(len(c) for c in ch); tt = at
        for c in ch:
            span = d * len(c) / tot; subs.append((tt, tt + span + (GAP if c is ch[-1] else 0), re.sub(r"[，。、；：！？]+$", "", c).strip())); tt += span
    ins2, flt, last = [], [f"[0:v]scale={W}:{H},fps={FPS}[v0]"], "v0"
    for n, (a, b, c) in enumerate(subs):
        p = subpng(f"{cid}_{n}", c); ins2 += ["-i", p]
        flt.append(f"[{last}][{n + 1}:v]overlay=(W-w)/2:{y_sub}:enable='between(t,{a:.2f},{b:.2f})'[v{n + 1}]"); last = f"v{n + 1}"
    out = os.path.join(WORK, f"vc_{cid}.mp4")
    subprocess.run([FF, "-y", "-loglevel", "error", *[x.replace("{T}", f"{total:.3f}") for x in vin], *ins2, "-i", awav, "-filter_complex", ";".join(flt),
        "-map", f"[{last}]", "-map", f"{len(subs) + 1}:a", "-t", f"{total:.3f}", "-c:v", "libx264", "-profile:v", "main", "-pix_fmt", "yuv420p",
        "-crf", "22", "-preset", "medium", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k", out], check=True)
    return out, total

def build():
    m = json.load(open(MARK)); sc = json.load(open(SCRIPT2, encoding="utf-8")); clips = []
    def seg(sid): s = sc[sid]; return (["-ss", f"{m[sid] + s.get('from', 0):.3f}", "-t", "{T}", "-i", m.get(sid + "_file", RAW)], s["lines"], s.get("min", 0))
    for sid in ("boot",):
        vin, lines, mn = seg(sid); clips.append(make_clip(sid, vin, lines, mn)); print(sid, round(clips[-1][1], 1), flush=True)
    for grp, keys in (("dom", DOM), ("wld", WLD)):
        for i, k in enumerate(keys):
            n, la, lo, _ = INFO[k]; line = f"{n}，{coord_text(la, lo)}。"
            vin = ["-ss", f"{m[grp] + OFF + STEP * i + 0.55:.3f}", "-t", "{T}", "-i", RAW]
            lines = [{"at": 0.2, "t": line}] if i else [{"at": 0.2, "t": sc[grp + "_intro"]}, {"t": line}]
            clips.append(make_clip(f"{grp}{i}", vin, lines, 3.0)); print(k, round(clips[-1][1], 1), flush=True)
        if grp == "dom":
            vin, lines, mn = seg("drive"); clips.append(make_clip("drive", vin, lines, mn)); print("drive", round(clips[-1][1], 1), flush=True)
    for sid in ("free", "credit"):
        s = sc[sid]; vin = ["-loop", "1", "-framerate", str(FPS), "-t", "{T}", "-i", card(sid)]
        clips.append(make_clip(sid, vin, s["lines"], s.get("min", 0), y_sub=1090)); print(sid, round(clips[-1][1], 1), flush=True)
    lst = os.path.join(WORK, "vlist.txt")
    open(lst, "w", encoding="utf-8").write("".join("file '" + c.replace(chr(92), "/") + "'" + chr(10) for c, _ in clips))
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", OUT], check=True)
    tot = sum(t for _, t in clips); print("完成", OUT, os.path.getsize(OUT) // 1048576, "MB，長", round(tot, 1), "秒")

if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else ""
    {"--bake": bake, "--record": (lambda: record(sys.argv[2] if len(sys.argv) > 2 else None)), "--frames": frames, "--build": build}.get(a, lambda: print(__doc__))()
