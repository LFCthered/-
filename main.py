import asyncio
import json
import os
import re
import random
import datetime
import pickle
import httplib2
import logging
import base64
from datetime import timedelta

# 引入核心库
from crawlee.crawlers._playwright import PlaywrightCrawler, PlaywrightCrawlingContext
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_httplib2 import AuthorizedHttp
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# 屏蔽干扰日志
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

# ==========================================
# ⚙️ 配置区 (通过 GitHub Secrets 读取)
# ==========================================
FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID', '13Liug6iJ7Q--pap__sScCqP5kH8NpRvt')
DATA_DIR = 'item_data_library'
# 在这里填入你每天想固定监控的饰品 ID 列表
TARGET_IDS = ["23199", "23200", "23198"] 

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]', '_', name)

# ==========================================
# 🕷️ 模块 1: 深度抓取引擎
# ==========================================
async def run_scraper(urls_to_crawl):
    print(f"📡 GitHub 节点启动，目标数量: {len(urls_to_crawl)}")
    crawler = PlaywrightCrawler(
        request_handler_timeout=timedelta(seconds=300),
        max_request_retries=2,
        headless=True # 云端必须为 True
    )

    @crawler.router.default_handler
    async def request_handler(context: PlaywrightCrawlingContext):
        page, url = context.page, context.request.url
        all_data = {"chartAll": [], "chipData": None, "details": None}
        
        async def handle_response(res):
            try:
                if "chipData" in res.url: all_data["chipData"] = await res.json()
                elif "chartAll" in res.url: all_data["chartAll"].append(await res.json())
                elif "good" in res.url and "info" in res.url: all_data["details"] = await res.json()
            except: pass
        
        page.on("response", handle_response)
        
        try:
            await page.goto(url, wait_until='networkidle')
            await page.wait_for_timeout(5000)
            # 点击筹码图
            btn = page.get_by_text(re.compile(r"筹码.*图"), exact=False).first
            if await btn.count() > 0:
                await btn.click(force=True)
                await page.wait_for_timeout(2000)
                # 模拟拖拽解锁长周期历史
                chart = page.locator('canvas').first 
                if await chart.is_visible():
                    box = await chart.bounding_box()
                    sx, sy = box['x'] + box['width'] * 0.8, box['y'] + box['height'] / 2
                    for _ in range(3):
                        await page.mouse.move(sx, sy); await page.mouse.down()
                        await page.mouse.move(sx + 350, sy, steps=15); await page.mouse.up()
                        await asyncio.sleep(1.5)
            
            info = all_data.get("details", {}).get("data", {}).get("goods_info", {})
            item_name = info.get("name") or f"ID_{url.split('/')[-1]}"
            with open(os.path.join(DATA_DIR, f"{sanitize_filename(item_name)}.json"), "w", encoding="utf-8") as f:
                json.dump(all_data, f, ensure_ascii=False, indent=4)
            print(f"✅ 抓取成功: {item_name}")
        except Exception as e: print(f"❌ 抓取失败 {url}: {e}")

    await crawler.run(urls_to_crawl)

# ==========================================
# ☁️ 模块 2: 云端上传 (GitHub 专用)
# ==========================================
def upload_to_drive(file_path):
    print(f"☁️ 正在同步至 Google Drive...")
    try:
        # 直接从当前目录加载被 GitHub Action 还原出来的 token.pickle
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
        
        if creds and creds.expired and cred
