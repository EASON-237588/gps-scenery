#!/usr/bin/env python3
"""把 gps-scenery 打包成單一自足的 index.html。

做法與「汽車聲浪」專案相同：CSS 與 JS 全部內嵌，除了 Google Fonts 之外
零外部參照，產出的檔案可以直接丟到任何靜態主機。

    python build.py          # → dist/index.html

差別在於聲浪專案能把 wav 一起 base64 內嵌，成為完全離線的單檔；
這個作品的照片與簡介來自即時 API，無法內嵌，所以仍然需要網路。
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, 'dist')
OUT = os.path.join(OUT_DIR, 'index.html')

# 依相依順序串接：geo → photos → app
MODULES = ['js/geo.js', 'js/photos.js', 'js/app.js']


def read(rel):
    with io.open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def strip_module_syntax(src):
    """把 ES module 轉成可以直接串接的程式碼。

    模組串成同一個檔案之後就共用同一個作用域，import/export 反而會出錯，
    但每個模組內部的識別字仍然要維持原名，所以只拆掉語法、不改名。
    """
    # import ... from '...';（含跨行的具名匯入區塊）
    src = re.sub(r'^import\s+[\s\S]*?\s+from\s+[\'"][^\'"]+[\'"];[ \t]*\n',
                 '', src, flags=re.M)
    # export { A, B };
    src = re.sub(r'^export\s*\{[^}]*\}\s*;[ \t]*\n', '', src, flags=re.M)
    # export function / const / class / async function / let / var
    src = re.sub(r'^export\s+(?=(?:async\s+)?function|const\s|class\s|let\s|var\s)',
                 '', src, flags=re.M)
    return src


def bundle(keep_manifest=False):
    """回傳打包好的單檔 HTML 字串（不寫檔），供 build-demo.py 再加工。"""
    html = read('index.html')
    css = read('css/style.css')

    parts = []
    for rel in MODULES:
        parts.append('/* ===== %s ===== */\n%s' % (rel, strip_module_syntax(read(rel))))
    js = '\n\n'.join(parts)

    # 內嵌樣式
    before = html
    html = html.replace(
        '<link rel="stylesheet" href="css/style.css">',
        '<style>\n%s\n</style>' % css)
    if html == before:
        sys.exit('找不到 stylesheet 的 <link>，index.html 結構可能改過了')

    # 內嵌腳本
    before = html
    html = html.replace(
        '<script type="module" src="js/app.js"></script>',
        '<script type="module">\n%s\n</script>' % js)
    if html == before:
        sys.exit('找不到 app.js 的 <script>，index.html 結構可能改過了')

    # 單檔沒有辦法附帶 manifest.json，拿掉以免 404（資料夾部署則保留）
    if not keep_manifest:
        html = html.replace('<link rel="manifest" href="manifest.json">\n', '')

    return html


def main():
    html = bundle()

    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(html)

    size = os.path.getsize(OUT)
    leftovers = re.findall(r'(?:src|href)="(?!https://fonts\.)([^"#][^"]*)"', html)
    print('寫出 %s（%.1f KB）' % (os.path.relpath(OUT, ROOT), size / 1024))
    print('殘留的外部參照：%s' % (leftovers or '無（只剩 Google Fonts）'))


if __name__ == '__main__':
    main()
