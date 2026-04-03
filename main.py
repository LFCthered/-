import asyncio
import json
import os
import re
import datetime
import pickle
import logging
import random
from datetime import timedelta

# 引入核心库
from crawlee.crawlers._playwright import PlaywrightCrawler, PlaywrightCrawlingContext
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

# 屏蔽干扰日志
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

# ==========================================
# ⚙️ 配置区
# ==========================================
FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID', '13Liug6iJ7Q--pap__sScCqP5kH8NpRvt')
DATA_DIR = 'item_data_library'
TARGET_IDS = ["24845", "24808", "20225","24774","24770","24810","24761","20139","24776","20111","24765"] 

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]', '_', name)

# ==========================================
# 🕷️ 模块 1: 深度抓取引擎 (修正沙盒与参数)
# ==========================================
async def run_scraper(urls_to_crawl):
    print(f"📡 GitHub 潜行节点启动，目标数量: {len(urls_to_crawl)}")
    
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ]

    # 🌟 核心修复：添加 browser_launch_options 并传入 --no-sandbox
    crawler = PlaywrightCrawler(
        request_handler_timeout=timedelta(seconds=120),
        max_request_retries=5,
        headless=True,
        browser_launch_options={
            "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        }
    )

    @crawler.router.default_handler
    async def request_handler(context: PlaywrightCrawlingContext):
        page, url = context.page, context.request.url
        all_data = {"chartAll": [], "chipData": None, "details": None}
        
        # 随机设置一个 User-Agent
        await page.set_extra_http_headers({"User-Agent": random.choice(user_agents)})
        
        async def handle_response(res):
            try:
                if "chipData" in res.url: all_data["chipData"] = await res.json()
                elif "chartAll" in res.url: all_data["chartAll"].append(await res.json())
                elif "good" in res.url and "info" in res.url: all_data["details"] = await res.json()
            except: pass
        
        page.on("response", handle_response)
        
        try:
            # 随机等待，像个人类在操作
            await asyncio.sleep(random.uniform(2, 5))
            
            # 访问页面，给足加载时间
            print(f"🌐 正在访问: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(10000) 
            
            # 尝试点击筹码按钮
            try:
                btn = page.get_by_text(re.compile(r"筹码.*图"), exact=False).first
                if await btn.is_visible():
                    await btn.click(force=True)
                    await page.wait_for_timeout(3000)
            except:
                pass

            info = all_data.get("details", {}).get("data", {}).get("goods_info", {})
            item_name = info.get("name") or f"ID_{url.split('/')[-1]}"
            
            save_path = os.path.join(DATA_DIR, f"{sanitize_filename(item_name)}.json")
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(all_data, f, ensure_ascii=False, indent=4)
            print(f"✅ 抓取成功: {item_name}")
            
        except Exception as e:
            print(f"❌ 抓取过程中出错 {url}: {e}")

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
        print(f"🎉 云端同步圆满成功！")
    except Exception as e:
        print(f"❌ 上传至云端失败: {e}")

# ==========================================
# 🚀 模块 3: 汇总与启动
# ==========================================
def generate_report():
    reports = []
    if not os.path.exists(DATA_DIR): return None
    files = [f for f in os.listdir(DATA_DIR) if f.endswith('.json')]
    if not files: return None

    for f in files:
        file_path = os.path.join(DATA_DIR, f)
        with open(file_path, 'r', encoding='utf-8') as j:
            try:
                d = json.load(j)
                info = d.get("details", {}).get("data", {}).get("goods_info", {})
                if info and info.get("name"): 
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
            print("⚠️ 报告生成失败：抓取到了页面但未提取到有效数据，或请求被拦截。")

if __name__ == "__main__":
    asyncio.run(main())
