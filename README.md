# 途中 Wayfarer · GPS 風景輪播

依你所在的 GPS 座標，即時尋找附近的旅遊勝地與風光照片，橫向全螢幕輪播，
每張照片旁附上名稱、距離、方位與文字簡介。

**適合的用法：** 手機放在車上支架或手持，一路移動、一路換風景。橫向、直向都支援。

---

## 它怎麼運作

| 步驟 | 做法 |
|------|------|
| 1. 取得座標 | `watchPosition()` 高精度持續追蹤，交給 `Tracker` 濾波（見下節） |
| 2. 地名 | BigDataCloud 反向地理編碼（免金鑰），顯示「中華民國 · 花蓮縣 · 秀林鄉」 |
| 3. 決定往哪找 | 靜止時用所在位置；**行進中把搜尋中心往前方推** `速度 × 45 秒` |
| 4. 找照片 | Wikipedia `generator=geosearch` → 附近條目的代表照片 + 條目摘要<br>Wikimedia Commons `generator=geosearch` → 標註在該座標附近的公開授權照片 |
| 5. 輪播 | 依「距離 + 來源 + 前方與否」排序，兩種來源交錯，預設每 15 秒淡入淡出 |
| 6. 跟著你走 | 依速度調整重搜門檻：市區 400 m、國道約 2.5 km |

所有 API 都**免金鑰、開放 CORS**，所以這是一個純前端網頁，不需要後端。

### 定位處理（`js/geo.js` 的 `Tracker`）

濾波做法參考同目錄下的**汽車聲浪**作品（`exhaust-note-site/index.html`）。
GPS 大約 1 Hz 且帶雜訊，直接使用會一格一格跳：

- **alpha-beta 濾波器**（等加速度模型的簡化 Kalman）同時維護「平滑速度」與
  「加速度」。`tick()` 以目前加速度外推，`onFix()` 用殘差同時修正兩個狀態。
  加速度是濾波器的內部狀態，不是事後對速度做差分 —— 差分會把量化雜訊放大成尖刺。
- `coords.speed` 為 null 的裝置（部分 Android），**退回用連續兩點 haversine 推算**
  速度，順便從軌跡算出行進方向。
- `heading` 在靜止時依規範是 null，**退回電子羅盤**（iOS 用 `webkitCompassHeading`，
  其他平台用 `alpha` 反推）。
- **stale 偵測**：訊號斷超過 3 秒就讓加速度衰減歸零，不會愈推愈遠。

聲浪作品拿這組速度去驅動音訊；這裡拿它去決定「該往哪裡找風景」。

### 為什麼要往前方搜尋

開車時你想看的是**即將到達**的風景，不是剛開過去的。所以行進中：

- 搜尋中心推到 `速度 × 45 秒` 之後的位置（上限 4 km）
- 身後超過 120° 的景點直接濾掉（濾完剩不到 12 張才放棄這個規則，
  免得在景點稀疏的路段整個清空）
- 每張照片標出它相對於你的位置：**前方 / 側邊 / 已通過**

實測（太魯閣口往西進峽谷，60 km/h）：不考慮方向時前 10 筆有 6 筆是已經開過去的，
開啟前瞻後降到 0 筆，順序變成牌樓 → 砂卡礑步道 → 台 8 線 → 長春祠，就是實際會經過的次序。

> 注意：**只有 GPS 的行進方向能拿來前瞻**。羅盤讀的是「手機朝哪」，車上手機隨便擺，
> 拿它推搜尋中心會整個歪掉 —— 羅盤只用於顯示。
>
> 另外「前方與否」必須以**你的實際位置**判斷，不能用推到前方的搜尋中心，
> 否則介於你與前瞻點之間的景點會被誤判成在身後。

### 照片挑選規則

為了讓畫面真的是「風景」而不是資料圖，做了幾層過濾：

- 剔除由 SVG 轉出的點陣圖（`*.svg.png`）— 幾乎都是標誌、市徽、地圖
- 檔名關鍵字黑名單：logo / emblem / map / flag / diagram / chart / QR code …
- 寬度 < 900px、或直幅比例過窄的不收（橫向版面會被裁掉）
- 同一張底圖在不同條目重複出現時只留一張
- 同一位攝影者連拍上傳的批次照片，每批最多取 2 張
- 清理機器命名：`2010 07 22100 6911 Xinyi District…` → `Xinyi District…`

---

## 執行

因為瀏覽器只允許 **HTTPS 或 localhost** 的網頁使用定位功能，不能直接用
`file://` 開啟 `index.html`。

### 本機測試

```bash
python -m http.server 8123 --directory gps-scenery
```

然後開 <http://localhost:8123>。

### 用手機測試（同一個 Wi-Fi）

`http://192.168.x.x:8123` 這種區網位址**不算安全來源**，Chrome 會擋掉定位。
兩個做法：

- **ngrok**（最快）：`ngrok http 8123`，用它給的 `https://` 網址開手機瀏覽器
- **部署到靜態主機**：GitHub Pages / Netlify / Cloudflare Pages 拖進去就好，
  它們預設都是 HTTPS

### 桌機模擬座標（不需要 GPS）

網址加上 `lat` / `lon` 參數就會跳過定位，直接用指定座標：

```
http://localhost:8123/index.html?lat=25.0339&lon=121.5645   # 台北 101
http://localhost:8123/index.html?lat=23.4700&lon=120.9570   # 玉山
http://localhost:8123/index.html?lat=24.1580&lon=121.6210   # 太魯閣牌樓
```

再加上 `&auto=1` 會跳過開場畫面直接開始，方便截圖或自動化測試。

**模擬行駛**（桌機驗證前瞻與自動重搜，不用真的開車上路）：

```
index.html?lat=24.1580&lon=121.6210&auto=1&drive=270&kmh=60
```

`drive` 是行進方位角（0=北、90=東、180=南、270=西），`kmh` 是速度。
它會每秒餵一筆合成定位給 `Tracker`，走完整條真實路徑 —— 濾波、前瞻、
到達門檻後自動重新搜尋。

`shots/` 裡是用 headless Chrome 以 844×390（手機橫向）產出的實際畫面。

---

## 上架

### 組出可以直接拖曳的資料夾

```bash
python build.py         # 先產出 dist/index.html
python build-demo.py    # （可選）展示版 → dist/demo.html
python build-deploy.py  # → deploy/ 與 gps-scenery-deploy.zip
```

`deploy/` 裡就是要放上網站根目錄的東西：

| 檔案 | 上線後的網址 |
|------|-------------|
| `index.html` | `/` — 完整版 |
| `demo.html` | `/demo.html` — 展示版（照片已內嵌，不需網路也不需定位） |
| `manifest.json` | 加到主畫面時全螢幕、鎖橫向 |

資料夾部署不受單檔限制，所以 `manifest.json` 會保留；`dist/index.html`
那個單檔版本則會拿掉 manifest 連結以免 404。

### 打包成單檔

```bash
python build.py
```

產出 `dist/index.html`（約 48 KB）：CSS 與三個 JS 模組全部內嵌，除了字型之外
零外部參照。打包方式與同目錄的「汽車聲浪」專案相同 —— 差別在於聲浪專案能把
wav 一起 base64 內嵌成完全離線的單檔，這個作品的照片與簡介來自即時 API，
無法內嵌，所以仍然需要網路。

### 丟到靜態主機（需要 HTTPS）

Geolocation 只在安全來源可用，所以一定要 HTTPS。三個都免費、都預設 HTTPS：

| 主機 | 做法 |
|------|------|
| **Netlify Drop** | 開 <https://app.netlify.com/drop>，把 `deploy` 資料夾（或 `gps-scenery-deploy.zip`）拖進去，馬上拿到網址。不需要先註冊，要保留網址再登入認領。 |
| **Cloudflare Pages** | Workers & Pages → Create → Pages → Upload assets，上傳 `deploy` 資料夾。 |
| **GitHub Pages** | 把 `deploy/` 的內容放進 repo，Settings → Pages → 選分支即可。 |

拿到網址後用手機開啟，按「開始定位」，允許位置權限。

### 展示版：可分享的 Artifact

完整版上不了 Artifact，但可以照聲浪專案的做法把內容內嵌，做成一個零網路的展示版：

```bash
python build-demo.py            # 抓取 + 烘焙 + 打包 → dist/demo.html
python build-demo.py --repack   # 只重組（改前端程式碼時用，不重抓）
```

會做這些事：

1. 對 6 個台灣景點（台北 101、太魯閣、玉山、日月潭、阿里山、墾丁）跑一次
   與線上版**完全相同**的查詢與篩選規則
2. 下載 1100px 寬的縮圖（存在 `.demo-cache/`，重跑不會重抓）
3. 全部 base64 內嵌成單一 `dist/demo.html`

實測 27 張照片、9.1 MB，載入後**零網路請求**（外部與同源都是 0）。

程式碼只有一份：`photos.js` 偵測到 `window.__BAKED__` 就讀內嵌資料，
否則即時查 API。展示版會多出 `⌖` 切換地點按鈕與「直接瀏覽」入口
（大部分人不在台灣），並隱藏沒有作用的搜尋半徑按鈕。

要發佈成 Artifact 得先拆掉外層文件結構（Artifact 會自己包
`<!doctype html><head></head><body>`），見 `dist/demo-artifact.html`。

### 為什麼不能發佈成 Claude Artifact

聲浪專案是發佈成 Artifact 的，但這個作品不行 —— Artifact 的 CSP 會擋掉
**對外部主機的 `fetch()`** 與**遠端圖片**，而這兩樣正是這個作品的內容來源：

| 需求 | Artifact |
|------|----------|
| `fetch()` Wikipedia / Commons API | 被擋 |
| `upload.wikimedia.org` 的照片 | 被擋 |
| Geolocation | 可用 |

聲浪專案能上 Artifact，正是因為它完全不需要網路。

---

## 版面

兩套佈局共用同一份 HTML 與元件，只靠 `@media (orientation:…)` 切換。

**橫向** — 照片滿版，簡介疊在右側，靠漸層壓暗保持可讀。

**直向** — 上下分割：照片占上方 60%，簡介在下方純色底上。
之所以不沿用「照片滿版 + 文字疊上去」，是因為風景照多半是橫幅，
直向若讓照片滿版，`cover` 會把左右各切掉一大塊；壓低照片高度反而看得比較完整。

直向的簡介欄是由上往下堆疊、出處緊接在內文之後（橫向則是固定高、出處釘在底部）。
橫向那種做法在直向會讓短簡介的文字與出處之間留下一大塊空白。
內文真的溢出時才加上底部漸隱遮罩，由 `is-scrollable` 類別控制。

> 直向的覆寫規則必須排在樣式表**最後**。同 specificity 下後面的規則會勝出，
> 曾經因為 `#toast` 的基礎規則排在直向區塊之後，導致 `bottom:auto` 被蓋掉、
> 提示框被拉長成整條。

---

## 操作

| 動作 | 手機 | 桌機 |
|------|------|------|
| 上一張 / 下一張 | 左右滑動，或按 `⟨` `⟩` | `←` `→` |
| 播放 / 暫停 | 按 `❚❚` | `空白鍵` |
| 換間隔（10 / 15 / 20 秒） | 按 `15s` | — |
| 換搜尋半徑（2 / 5 / 10 km） | 按 `10km` | — |
| 重新搜尋附近 | 按 `↻` | — |
| 全螢幕 | 按 `⛶` | `F` |

控制列平常是半透明的，碰一下畫面才會浮出來。播放時會嘗試取得
Screen Wake Lock，讓螢幕不自動熄掉。

---

## 檔案結構

```
gps-scenery/
├── index.html          版面骨架（開發用，載入下面的 css/ 與 js/）
├── build.py            打包成單檔 → dist/index.html
├── build-demo.py       烘焙展示版 → dist/demo.html（零網路，內嵌照片）
├── build-deploy.py     組出 deploy/ 資料夾與 zip ← 上架就用這個
├── deploy/             ← 拖到 Netlify Drop 的就是這個資料夾
├── dist/index.html     ← 上架用的單檔，CSS 與 JS 全部內嵌
├── manifest.json       PWA（加到主畫面後全螢幕、鎖橫向）
├── css/style.css       深色版面、橫向／直向兩套佈局、淡入淡出、Ken Burns
└── js/
    ├── geo.js          Tracker（濾波定位）、幾何計算、羅盤、反向地理編碼
    ├── photos.js       Wikipedia + Commons 查詢、過濾、去重、排序
    └── app.js          主流程：定位 → 抓圖 → 輪播 → 控制項
```

---

## 已知限制

- Wikimedia 的 `geosearch` **半徑上限是 10 公里**，所以最大就只能搜到 10km。
- 偏遠地區或海上可能完全沒有帶座標的公開照片，這時會顯示提示並在下次位置
  更新時自動重試。
- 照片來源是使用者上傳的維基共享資源，品質不齊；過濾規則只能擋掉明顯不是
  風景的東西。
- iOS Safari 不支援 `screen.orientation.lock()` 也不支援 `requestFullscreen()`。
  要真正全螢幕得用 Safari 開啟 →「加入主畫面」→ 從主畫面啟動。
  `⛶` 按鈕會依所在瀏覽器給出對應指示，已從主畫面啟動時會自動隱藏。
- LINE / FB / IG 的內建瀏覽器有自己的工具列，網頁無法移除。

## 授權與出處

照片與文字來自 **Wikipedia**（CC BY-SA）與 **Wikimedia Commons**（各檔案的授權
標示於畫面右下角）。每張照片都附有原始頁面連結，可查看完整授權與攝影者。
