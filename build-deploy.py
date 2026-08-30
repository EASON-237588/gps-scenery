#!/usr/bin/env python3
"""組出可以直接拖到靜態主機的 deploy/ 資料夾與壓縮檔。

    python build-deploy.py

產出：
    deploy/index.html     完整版（CSS 與 JS 內嵌，保留 manifest 連結）
    deploy/manifest.json  加到主畫面時全螢幕、鎖橫向
    deploy/demo.html      展示版（可選，照片已內嵌）
    gps-scenery-deploy.zip

用法：把 deploy 資料夾（或這個 zip）拖到 https://app.netlify.com/drop
資料夾內容會成為網站根目錄，所以完整版在 /，展示版在 /demo.html。
"""

import io
import os
import shutil
import sys
import zipfile

import build

ROOT = os.path.dirname(os.path.abspath(__file__))
DEPLOY = os.path.join(ROOT, 'deploy')
ZIP = os.path.join(ROOT, 'gps-scenery-deploy.zip')

DEMO_SRC = os.path.join(ROOT, 'dist', 'demo.html')


def main():
    include_demo = '--no-demo' not in sys.argv

    # 每次重建，免得留下上一次的檔案
    if os.path.isdir(DEPLOY):
        shutil.rmtree(DEPLOY)
    os.makedirs(DEPLOY)

    # 1. 完整版（資料夾部署，manifest 連結保留）
    html = build.bundle(keep_manifest=True)
    with io.open(os.path.join(DEPLOY, 'index.html'), 'w',
                 encoding='utf-8', newline=chr(10)) as f:
        f.write(html)

    # 2. manifest
    shutil.copy(os.path.join(ROOT, 'manifest.json'),
                os.path.join(DEPLOY, 'manifest.json'))

    # 3. 展示版（沒建過就跳過，不擋住主流程）
    if include_demo and os.path.exists(DEMO_SRC):
        shutil.copy(DEMO_SRC, os.path.join(DEPLOY, 'demo.html'))
    elif include_demo:
        print('（找不到 dist/demo.html，略過展示版；先跑 python build-demo.py）')

    # 4. 打包
    if os.path.exists(ZIP):
        os.remove(ZIP)
    with zipfile.ZipFile(ZIP, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(DEPLOY)):
            z.write(os.path.join(DEPLOY, name), name)

    print('deploy/')
    for name in sorted(os.listdir(DEPLOY)):
        size = os.path.getsize(os.path.join(DEPLOY, name))
        print('  %-16s %8.1f KB' % (name, size / 1024))
    print('%s  %.1f MB' % (os.path.basename(ZIP), os.path.getsize(ZIP) / 1024 / 1024))


if __name__ == '__main__':
    main()
