"""途中 Wayfarer 操作示範影片：錄真實程式畫面 → 剪接 → 曉臻口白 → 字幕 → LINE 相容 mp4

兩階段：
  python make_video.py --record   只錄畫面（約 8 分鐘；錄的時候不要碰滑鼠鍵盤、右下角不能有通知）
  python make_video.py --frames   從 raw.mkv 抽每個場景的檢查畫面，用來對照寫口白
  python make_video.py --build    讀「腳本.json」做口白＋字幕並剪成成品
字幕 ＝ 口白的同一份文字（逐句產生口白、逐段顯示字幕），所以一定一致。
前置：專案資料夾已用 python -m http.server 8123 開著。
"""
import asyncio, ctypes, hashlib, json, math, os, re, subprocess, sys, time
from PIL import Image, ImageDraw, ImageFont
import edge_tts, imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "_work"); os.makedirs(os.path.join(WORK, "audio"), exist_ok=True)
RAW = os.path.join(WORK, "raw.mkv"); MARK = os.path.join(WORK, "marks.json")
SCRIPT = os.path.join(HERE, "腳本.json")
OUT = os.path.join(HERE, "途中 Wayfarer 操作示範.mp4")
FF = imageio_ffmpeg.get_ffmpeg_exe()
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = os.path.join(os.environ["TEMP"], "wf_chrome")
BASE = "http://localhost:8123/index.html"
SCREEN_W, SCREEN_H = 3840, 2160          # 主螢幕實際像素（只錄這一個螢幕）
W, H, FPS = 1280, 720, 24
VOICE = "zh-TW-HsiaoChenNeural"
LOAD = 16; LOADS = {"boot": 4}           # 開啟後等照片載入的秒數（這段不進成品）
GAP = 0.35                               # 句與句之間的停頓

def drive(lat, lon, head, d=700, kmh=60):
    """從景點『後方』d 公尺起跑，朝景點開過去（行駛模擬）"""
    r = math.radians(head)
    la = lat - d * math.cos(r) / 111320
    lo = lon - d * math.sin(r) / (111320 * math.cos(math.radians(lat)))
    return f"?lat={la:.5f}&lon={lo:.5f}&auto=1&drive={head}&kmh={kmh}"

# (id, 網址參數, 錄影秒數, [(秒數, 按鍵)])；網址 None＝文字卡
SCENES = [
 ("boot",   "", 12, []),
 ("taipei", "?lat=25.0339&lon=121.5645&auto=1", 26, [(10, "right"), (19, "right")]),
 ("taroko", "?lat=24.1580&lon=121.6210&auto=1&drive=270&kmh=60", 40, [(12, "right"), (24, "right"), (33, "right")]),
 ("sunmoon", drive(23.8570, 120.9150, 90), 30, [(12, "right"), (22, "right")]),
 ("alishan", drive(23.5088, 120.8054, 45), 30, [(12, "right"), (22, "right")]),
 ("kenting", drive(21.9446, 120.7980, 180), 30, [(12, "right"), (22, "right")]),
 ("fuji",   "?lat=35.3606&lon=138.7274&auto=1", 22, [(9, "right"), (16, "right")]),
 ("eiffel", "?lat=48.8584&lon=2.2945&auto=1", 22, [(9, "right"), (16, "right")]),
 ("sydney", "?lat=-33.8568&lon=151.2153&auto=1", 22, [(9, "right"), (16, "right")]),
 ("machu",  "?lat=-13.1631&lon=-72.5450&auto=1", 22, [(9, "right"), (16, "right")]),
 ("ctrl",   "?lat=25.0339&lon=121.5645&auto=1", 22, [(5, "space"), (9, "space"), (13, "right")]),
 ("free",   None, 0, []),
 ("credit", None, 0, []),
]

def probe(p):
    r = subprocess.run([FF, "-hide_banner", "-i", p], capture_output=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])

# ---------- 錄影 ----------
VK = {"right": 0x27, "left": 0x25, "space": 0x20}
def press(k):
    u = ctypes.windll.user32
    u.keybd_event(VK[k], 0, 0, 0); time.sleep(0.05); u.keybd_event(VK[k], 0, 2, 0)

def kill_chrome():
    subprocess.run(["powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*wf_chrome*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        capture_output=True)

def record():
    marks = {}
    rec = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "gdigrab", "-framerate", str(FPS), "-draw_mouse", "0",
        "-offset_x", "0", "-offset_y", "0", "-video_size", f"{SCREEN_W}x{SCREEN_H}", "-i", "desktop",
        "-vf", "scale=1920:1080", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p", RAW],
        stdin=subprocess.PIPE)
    time.sleep(2.0); t0 = time.time()
    try:
        for sid, qs, length, keys in SCENES:
            if qs is None: continue
            kill_chrome(); time.sleep(0.8)
            launch = time.time() - t0
            subprocess.Popen([CHROME, "--kiosk", "--window-position=0,0", f"--user-data-dir={PROFILE}", "--no-first-run",
                "--disable-notifications", "--disable-infobars", "--disable-session-crashed-bubble", BASE + qs])
            ld = LOADS.get(sid, LOAD); marks[sid] = launch + ld
            st = time.time(); end = st + ld + length + 1.0; pend = sorted(keys)
            while time.time() < end:
                el = time.time() - st - ld
                while pend and el >= pend[0][0]:
                    press(pend.pop(0)[1])
                time.sleep(0.1)
            print(sid, "完成", round(time.time() - t0, 1), flush=True)
    finally:
        kill_chrome()
        rec.stdin.write(b"q"); rec.stdin.flush(); rec.wait(timeout=60)
    json.dump(marks, open(MARK, "w"))

def frames():
    """每個場景每 3 秒抽一張，每個場景拼成一張總覽，方便對照寫口白"""
    marks = json.load(open(MARK)); os.makedirs(os.path.join(WORK, "chk"), exist_ok=True)
    for sid, qs, length, _ in SCENES:
        if qs is None: continue
        subprocess.run([FF, "-y", "-loglevel", "error", "-ss", f"{marks[sid]:.2f}", "-t", f"{length}", "-i", RAW,
            "-vf", "fps=1/3,scale=480:-1,tile=4x3", "-frames:v", "1", os.path.join(WORK, "chk", sid + ".png")])
    print("已輸出到", os.path.join(WORK, "chk"))

# ---------- 文字卡 ----------
def font(s, b=False): return ImageFont.truetype("C:/Windows/Fonts/" + ("msjhbd.ttc" if b else "msjh.ttc"), s)
TEAL, WHT, DIM = (111, 211, 192), (240, 244, 248), (140, 155, 172)
def card(sid):
    im = Image.new("RGB", (W, H), (5, 7, 12)); d = ImageDraw.Draw(im)
    if sid == "free":
        d.text((W // 2, 120), "不需要特別的技術費用", font=font(52, True), fill=WHT, anchor="mm")
        d.text((W // 2, 280), "0 元", font=font(150, True), fill=TEAL, anchor="mm")
        for n, t in enumerate(["定位：手機、電腦現有的 GPS", "照片與簡介：維基百科、維基共享資源（免費公開）", "執行：純網頁，免主機、免後端"]):
            d.text((W // 2, 420 + n * 56), "●  " + t, font=font(28), fill=WHT, anchor="mm")
    else:
        d.text((70, 60), "照片與文字來源", font=font(40, True), fill=TEAL)
        rows = ["維基百科（中文）　　　　簡介文字　　CC BY-SA", "維基共享資源　　　　　　　公開授權照片　各檔案授權標示於畫面右下角",
                "BigDataCloud　　　　　　反向地理編碼（免金鑰）", "", "每張照片都附：攝影者、年份、授權，以及原始頁面連結。",
                "所有查詢都免金鑰，所以不需要後端。"]
        for n, t in enumerate(rows): d.text((70, 150 + n * 62), t, font=font(27), fill=WHT if t else DIM)
        d.text((70, 560), "途 中 Wayfarer　製作中", font=font(34, True), fill=TEAL)
    p = os.path.join(WORK, sid + ".png"); im.save(p); return p

def wrap(text, n=26):
    return [text[i:i + n] for i in range(0, len(text), n)]

def subpng(name, text):
    f = font(30, True); lines = wrap(text); tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    tw = max(tmp.textlength(l, font=f) for l in lines); h = 22 + 42 * len(lines)
    im = Image.new("RGBA", (int(tw) + 56, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, h - 1), 12, fill=(0, 0, 0, 178))
    for i, l in enumerate(lines): d.text((im.width // 2, 11 + 42 * i + 21), l, font=f, fill=(255, 255, 255), anchor="mm")
    p = os.path.join(WORK, name + ".png"); im.save(p); return p, h

# ---------- 口白（逐句）----------
async def tts_one(text, p):
    if not os.path.exists(p): await edge_tts.Communicate(text, VOICE, rate="-4%").save(p)

def sentences(text):
    return [s for s in re.findall(r"[^。！？]+[。！？]?", text) if s.strip()]

def build():
    """腳本.json 每個場景：{"from": 起點偏移秒(相對切點，可為負), "lines": [{"at": 秒, "t": 文字}, ...], "min": 最短秒數}
    口白逐句生成；每句從 at 秒開始（前面不足就補靜音）；字幕 = 同一句文字。"""
    script = json.load(open(SCRIPT, encoding="utf-8")); marks = json.load(open(MARK)); clips = []
    for sid, qs, length, _ in SCENES:
        sc = script[sid]; frm = sc.get("from", 0.0); lines = sc["lines"]
        t = 0.0; items = []   # (起點, 長度, 句子, wav)
        for ln in lines:
            for s in sentences(ln["t"]):
                at = max(t, ln.get("at", 0.0)) if s is sentences(ln["t"])[0] else t
                h = hashlib.md5(s.encode("utf-8")).hexdigest()[:10]
                mp3 = os.path.join(WORK, "audio", f"{h}.mp3"); asyncio.run(tts_one(s, mp3))
                wav = os.path.join(WORK, "audio", f"{h}.wav"); d = probe(mp3)
                subprocess.run([FF, "-y", "-loglevel", "error", "-i", mp3, "-ar", "44100", "-ac", "2", wav], check=True)
                items.append((at, d, s, wav)); t = at + d + GAP
        total = max(t + 0.8, sc.get("min", 0))
        if qs is not None and frm + total > length + 1: print("警告：", sid, "需要", round(frm + total, 1), "秒 > 錄影", length)
        # 音訊：每句用 adelay 放到指定時間，再混合
        ins = []; fl = []
        for n, (at, d, s, wav) in enumerate(items):
            ins += ["-i", wav]; fl.append(f"[{n}:a]adelay={int(at * 1000)}|{int(at * 1000)}[a{n}]")
        mix = "".join(f"[a{n}]" for n in range(len(items))) + f"amix=inputs={len(items)}:normalize=0,apad[am]"
        awav = os.path.join(WORK, f"a_{sid}.wav")
        subprocess.run([FF, "-y", "-loglevel", "error", *ins, "-filter_complex", ";".join(fl + [mix]), "-map", "[am]",
                        "-t", f"{total:.3f}", "-ar", "44100", "-ac", "2", awav], check=True)
        # 字幕：每句依逗號再切段，時間依字數分配
        subs = []
        for at, d, s, _ in items:
            chunks = [c for c in re.split(r"(?<=[，、；：])", s) if c.strip()]; tot = sum(len(c) for c in chunks); tt = at
            for c in chunks:
                span = d * len(c) / tot
                subs.append((tt, tt + span + (GAP if c is chunks[-1] else 0), re.sub(r"[，。、；：！？]+$", "", c).strip())); tt += span
        vin = (["-loop", "1", "-framerate", str(FPS), "-t", f"{total:.3f}", "-i", card(sid)] if qs is None
               else ["-ss", f"{marks[sid] + frm:.3f}", "-t", f"{total:.3f}", "-i", RAW])
        ins2, flt, last = [], [f"[0:v]scale={W}:{H},fps={FPS}[v0]"], "v0"
        for n, (a, b, c) in enumerate(subs):
            p, hh = subpng(f"sub_{sid}_{n}", c); ins2 += ["-i", p]
            flt.append(f"[{last}][{n + 1}:v]overlay=(W-w)/2:H-h-34:enable='between(t,{a:.2f},{b:.2f})'[v{n + 1}]"); last = f"v{n + 1}"
        out = os.path.join(WORK, f"clip_{sid}.mp4")
        subprocess.run([FF, "-y", "-loglevel", "error", *vin, *ins2, "-i", awav, "-filter_complex", ";".join(flt),
            "-map", f"[{last}]", "-map", f"{len(subs) + 1}:a", "-t", f"{total:.3f}", "-c:v", "libx264", "-profile:v", "main",
            "-pix_fmt", "yuv420p", "-crf", "22", "-preset", "medium", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k", out], check=True)
        clips.append((out, total)); print(sid, round(total, 1), "秒", flush=True)
    lst = os.path.join(WORK, "list.txt")
    open(lst, "w", encoding="utf-8").write("".join(f"file '{c.replace(chr(92), '/')}'\n" for c, _ in clips))
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                    "-movflags", "+faststart", OUT], check=True)
    print("完成", OUT, os.path.getsize(OUT) // 1024, "KB，長", round(sum(t for _, t in clips), 1), "秒")

if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else ""
    if a == "--record": record()
    elif a == "--frames": frames()
    elif a == "--build": build()
    else: print(__doc__)
