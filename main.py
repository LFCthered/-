import asyncio
import json
import os
import re
import datetime
import pickle
import logging
from datetime import timedelta

# 引入核心库
from crawlee.crawlers._playwright import PlaywrightCrawler, PlaywrightCrawlingContext
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

# 屏蔽干扰日志
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

# ==========================================
# ⚙️ 配置区 (通过 GitHub Secrets 读取)
# ==========================================
FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID', '13Liug6iJ7Q--pap__sScCqP5kH8NpRvt')
DATA_DIR = 'item_data_library'

# 🌟 在这里填入你每天想固定监控的饰品 ID 列表 (示例为：薄荷、元勋、猩红头巾)
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
        headless=True  # ☁️ 云端运行必须开启无头模式
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
                
                # 模拟拖拽解锁长周期历史 (为了获取更多筹码数据)
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
            
            save_path = os.path.join(DATA_DIR, f"{sanitize_filename(item_name)}.json")
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(all_data, f, ensure_ascii=False, indent=4)
            print(f"✅ 抓取成功: {item_name}")
        except Exception as e:
            print(f"❌ 抓取失败 {url}: {e}")

    await crawler.run(urls_to_crawl)

# ==========================================
# ☁️ 模块 2: 云端上传
# ==========================================
def upload_to_drive(file_path):
    print(f"☁️ 正在同步至 Google Drive...")
    try:
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
        
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        service = build('drive', 'v3', credentials=creds)
        file_metadata = {'name': os.path.basename(file_path), 'parents': [FOLDER_ID]}
        media = MediaFileUpload(file_path, mimetype='application/json')
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f"🎉 云端同步圆满成功！文件名: {os.path.basename(file_path)}")
    except Exception as e:
        print(f"❌ 上传至云端失败: {e}")

# ==========================================
# 🚀 模块 3: 汇总与启动
# ==========================================
def generate_report():
    reports = []
    if not os.path.exists(DATA_DIR): return None
    for f in os.listdir(DATA_DIR):
        if f.endswith('.json'):
            file_path = os.path.join(DATA_DIR, f)
            with open(file_path, 'r', encoding='utf-8') as j:
                try:
                    d = json.load(j)
                    info = d.get("details", {}).get("data", {}).get("goods_info", {})
                    reports.append({
                        "name": info.get("name"), 
                        "price": info.get("buff_sell_price"), 
                        "chips": d.get("chipData"),
                        "timestamp": datetime.datetime.now().isoformat()
                    })
                except: pass
    
    if not reports: return None
    report_name = f"Daily_Report_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(report_name, 'w', encoding='utf-8') as r:
        json.dump(reports, r, ensure_ascii=False, indent=2)
    return report_name

async def main():
    urls = [f"https://csqaq.com/goods/{i}" for i in TARGET_IDS]
    if urls:
        await run_scraper(urls)
        report_file = generate_report()
        if report_file:
            upload_to_drive(report_file)
        else:
            print("⚠️ 未发现生成的本地数据，无法上传报告。")

if __name__ == "__main__":
    asyncio.run(main())
