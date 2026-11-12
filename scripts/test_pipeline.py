import os
import unittest
import urllib.request
import xml.etree.ElementTree as ET

class TestNewsDigestPipeline(unittest.TestCase):
    def test_frontend_file_exists(self):
        """驗證前端網頁檔案存在且具備核心元素"""
        html_path = os.path.join("public", "index.html")
        self.assertTrue(os.path.exists(html_path), "前端 index.html 必須存在")
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("liff.init", content, "必須包含 LIFF SDK 初始化邏輯")
        self.assertIn("settings-modal", content, "必須包含主題設定彈窗")
        self.assertIn("AI 核心洞察摘要", content, "必須包含 AI 摘要呈現元件")

    def test_gas_backend_file_exists(self):
        """驗證 Google Apps Script 後端腳本完整性"""
        gas_path = os.path.join("gas", "Code.gs")
        self.assertTrue(os.path.exists(gas_path), "後端 Code.gs 必須存在")
        with open(gas_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("setupSheets", content, "必須具備一鍵資料庫初始化")
        self.assertIn("doGet", content, "必須具備 GET API")
        self.assertIn("doPost", content, "必須具備 Webhook POST API")
        self.assertIn("dailyBatchUpdate", content, "必須具備定時排程邏輯")
        self.assertIn("summarizeWithGemini", content, "必須具備 Gemini 摘要邏輯")

    def test_real_rss_feed(self):
        """驗證真實 Google News RSS 網路連線與 XML 結構"""
        query = "具身機器人"
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as res:
            self.assertEqual(res.status, 200)
            xml_data = res.read()
        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        self.assertGreater(len(items), 0, "Google News RSS 必須能檢索到相關條目")

if __name__ == "__main__":
    unittest.main()
