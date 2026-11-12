import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import sys

def fetch_google_news_rss(keywords: str, max_items: int = 5):
    """
    透過 Google News RSS 抓取 24 小時內之相關繁體中文新聞
    """
    encoded_query = urllib.parse.quote(f"{keywords} when:24h")
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    req = urllib.request.Request(
        rss_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    
    with urllib.request.urlopen(req, timeout=10) as response:
        xml_content = response.read()
        
    root = ET.fromstring(xml_content)
    channel = root.find("channel")
    if channel is None:
        return []
    
    items = []
    for item in channel.findall("item")[:max_items]:
        title = item.findtext("title", default="無標題")
        link = item.findtext("link", default="")
        pub_date = item.findtext("pubDate", default="")
        source_elem = item.find("source")
        source = source_elem.text if source_elem is not None else "新聞來源"
        
        items.append({
            "title": title,
            "link": link,
            "pub_date": pub_date,
            "source": source
        })
    return items

if __name__ == "__main__":
    test_keywords = "具身機器人 製造業"
    print(f"[*] 測試檢索關鍵字: '{test_keywords}'...")
    try:
        results = fetch_google_news_rss(test_keywords)
        print(f"[+] 成功取得 {len(results)} 則新聞:")
        for idx, news in enumerate(results, 1):
            print(f"  {idx}. [{news['source']}] {news['title']}")
            print(f"     連結: {news['link']}")
        assert len(results) > 0, "檢索結果不應為空"
        print("[v] RSS 爬蟲與解析邏輯驗證通過！")
    except Exception as e:
        print(f"[-] 發生錯誤: {e}", file=sys.stderr)
        sys.exit(1)
