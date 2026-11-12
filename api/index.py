from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import os
from datetime import datetime

app = FastAPI(title="Daily AI News API")

# 記憶體快取 (Serverless 生命週期內重複使用)
NEWS_CACHE = {}
USER_KEYWORDS = {
    "default": "具身機器人, 製造業 AI, 智慧工廠"
}

def fetch_google_news(keywords: str, max_items: int = 5):
    """免費抓取 Google News RSS"""
    query = f"{keywords} when:24h"
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            xml_data = res.read()
        root = ET.fromstring(xml_data)
        items = []
        for item in root.findall(".//item")[:max_items]:
            title = item.findtext("title", default="無標題")
            link = item.findtext("link", default="")
            source_elem = item.find("source")
            source = source_elem.text if source_elem is not None else "科技新聞"
            items.append({
                "title": title,
                "link": link,
                "source": source
            })
        return items
    except Exception as e:
        print(f"RSS 錯誤: {e}")
        return []

def summarize_with_gemini(news_items, keywords: str):
    """呼叫 Google Gemini API 產生繁體中文摘要"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        # Fallback 預設摘要
        return [
            {
                "title": n["title"],
                "link": n["link"],
                "source": n["source"],
                "summary": "最新產業科技新聞，已成功抓取並收錄。",
                "impact": "建議持續追蹤相關硬體與演算法升級進展。"
            }
            for n in news_items
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
        with urllib.request.urlopen(req, timeout=10) as res:
            res_data = json.loads(res.read().decode("utf-8"))
        text = res_data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception as e:
        print(f"Gemini 呼叫失敗: {e}")
        return [
            {
                "title": n["title"],
                "link": n["link"],
                "source": n["source"],
                "summary": "今日最新焦點新聞。",
                "impact": "觀察市場供應鏈動態。"
            }
            for n in news_items
        ]

@app.get("/api/user-settings")
def get_user_settings(userId: str = "default"):
    kw = USER_KEYWORDS.get(userId, USER_KEYWORDS["default"])
    return {"success": True, "userId": userId, "keywords": kw}

@app.get("/api/news")
def get_news(userId: str = "default"):
    today_str = datetime.now().strftime("%Y-%m-%d")
    cache_key = f"{userId}_{today_str}"
    
    if cache_key in NEWS_CACHE:
        return {"success": True, "date": today_str, "data": NEWS_CACHE[cache_key]}
    
    keywords = USER_KEYWORDS.get(userId, USER_KEYWORDS["default"])
    raw_news = fetch_google_news(keywords)
    ai_digest = summarize_with_gemini(raw_news, keywords)
    
    NEWS_CACHE[cache_key] = ai_digest
    return {"success": True, "date": today_str, "data": ai_digest}

@app.post("/api/update-keywords")
async def update_keywords(req: Request):
    data = await req.json()
    user_id = data.get("userId", "default")
    keywords = data.get("keywords", USER_KEYWORDS["default"])
    USER_KEYWORDS[user_id] = keywords
    
    # 清除今日快取以利重新整理
    today_str = datetime.now().strftime("%Y-%m-%d")
    NEWS_CACHE.pop(f"{user_id}_{today_str}", None)
    
    return {"success": True, "message": "關鍵字已更新"}

@app.post("/api/webhook")
async def line_webhook(req: Request):
    """處理 LINE 對話框設定關鍵字 (免費 Reply API)"""
    body = await req.body()
    data = json.loads(body.decode("utf-8"))
    line_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    
    events = data.get("events", [])
    if events and line_token:
        event = events[0]
        reply_token = event.get("replyToken")
        user_id = event.get("source", {}).get("userId", "default")
        
        if event.get("type") == "message" and event.get("message", {}).get("type") == "text":
            text = event["message"]["text"].strip()
            if text.startswith("關鍵字") or text.startswith("設定關鍵字"):
                raw_kw = text.replace("設定關鍵字", "").replace("關鍵字", "").strip(":： ")
                USER_KEYWORDS[user_id] = raw_kw
                msg = f"✅ 專屬新聞關鍵字已設為：\n「{raw_kw}」\n\n點開下方圖文選單隨時瀏覽專屬日報！"
            else:
                msg = "您好！在對話框輸入「關鍵字: 機器人, 半導體」即可自訂追蹤主題，或點擊選單開啟日報。"
                
            reply_url = "https://api.line.me/v2/bot/message/reply"
            reply_payload = {
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": msg}]
            }
            urllib.request.urlopen(
                urllib.request.Request(
                    reply_url,
                    data=json.dumps(reply_payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {line_token}"
                    }
                )
            )
    return "OK"
