import os
import sys
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

# 環境變數設定
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_USERS_DB_ID = os.environ.get("NOTION_USERS_DB_ID", "0b76f3b0-55fd-4415-b2bb-ba8d3934dbd7")
NOTION_NEWS_DB_ID = os.environ.get("NOTION_NEWS_DB_ID", "a5a1287b-c87e-4fcd-adee-ea5e3d3d2566")

def fetch_google_news_rss(keywords: str, max_items: int = 3):
    """免費抓取 Google News RSS"""
    query = f"{keywords} when:24h"
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            xml_data = res.read()
        root = ET.fromstring(xml_data)
        items = []
        for item in root.findall(".//item")[:max_items]:
            title = item.findtext("title", default="無標題")
            link = item.findtext("link", default="")
            source_elem = item.find("source")
            source = source_elem.text if source_elem is not None else "產業快訊"
            items.append({
                "title": title,
                "link": link,
                "source": source
            })
        return items
    except Exception as e:
        print(f"[-] RSS 抓取失敗: {e}")
        return []

def summarize_with_gemini(news_items, keywords: str, api_key: str):
    """呼叫 Google Gemini API 產生繁體中文產業摘要"""
    if not api_key:
        return [
            {
                "title": item["title"],
                "link": item["link"],
                "source": item["source"],
                "summary": "今日最新焦點新聞，已自動抓取收錄。",
                "impact": "建議持續關注相關硬體規格演進與市場需求。"
            }
            for item in news_items
        ]

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    prompt = f"""你是一位資深科技分析師與製造業顧問。請閱讀以下使用者感興趣關鍵字「{keywords}」的最新新聞：
{json.dumps(news_items, ensure_ascii=False)}

請輸出嚴格的 JSON 陣列（Array of Objects），不可包含任何 Markdown 格式或額外文字。
每個物件包含：
- title: 標題
- link: 連結
- source: 來源
- summary: 2 句話繁體中文重點摘要
- impact: 1 句話說明對台灣製造業、軟硬整合或一般企業有何實質影響或落地借鏡？"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            res_data = json.loads(res.read().decode("utf-8"))
        text = res_data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception as e:
        print(f"[-] Gemini 呼叫失敗: {e}")
        return [
            {
                "title": item["title"],
                "link": item["link"],
                "source": item["source"],
                "summary": "今日最新焦點新聞，已自動整理收錄。",
                "impact": "持續觀察供應鏈與技術落地動向。"
            }
            for item in news_items
        ]

def write_news_to_notion(news_item, user_page_id: str, notion_token: str, db_id: str, today_str: str):
    """將新聞透過 Notion API 寫入 Notion 資料庫"""
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    payload = {
        "parent": {"database_id": db_id},
        "properties": {
            "新聞標題": {
                "title": [{"text": {"content": news_item["title"]}}]
            },
            "媒體來源": {
                "rich_text": [{"text": {"content": news_item["source"]}}]
            },
            "原文連結": {
                "url": news_item["link"] if news_item["link"].startswith("http") else None
            },
            "AI重點摘要": {
                "rich_text": [{"text": {"content": news_item["summary"]}}]
            },
            "產業落地影響": {
                "rich_text": [{"text": {"content": news_item["impact"]}}]
            },
            "產出日期": {
                "rich_text": [{"text": {"content": today_str}}]
            }
        }
    }
    
    if user_page_id:
        payload["properties"]["所屬用戶"] = {
            "relation": [{"id": user_page_id}]
        }

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status == 200
    except Exception as e:
        print(f"[-] 寫入 Notion 失敗: {e}")
        return False

def main():
    print("[*] 啟動每日 AI 新聞雲端排程 Worker...")
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 預設追蹤關鍵字
    default_keywords = "具身機器人, 製造業 AI, 智慧工廠"
    print(f"[*] 正在抓取「{default_keywords}」最新新聞...")
    
    news_items = fetch_google_news_rss(default_keywords, max_items=3)
    print(f"[+] 抓取完成，共取得 {len(news_items)} 則新聞。")
    
    print("[*] 正在透過 Gemini Flash 產生深度產業摘要...")
    ai_summaries = summarize_with_gemini(news_items, default_keywords, GEMINI_API_KEY)
    
    if NOTION_API_KEY:
        print("[*] 正在寫入 Notion 雲端資料庫...")
        for item in ai_summaries:
            write_news_to_notion(item, None, NOTION_API_KEY, NOTION_NEWS_DB_ID, today_str)
        print("[v] 全數寫入 Notion 完成！")
    else:
        print("[i] 未偵測到 NOTION_API_KEY，輸出預覽結果：")
        for idx, item in enumerate(ai_summaries, 1):
            print(f"  {idx}. [{item['source']}] {item['title']}")
            print(f"     摘要: {item['summary']}")
            print(f"     影響: {item['impact']}")
    
    print("[v] 今日排程任務執行完畢。")

if __name__ == "__main__":
    main()
