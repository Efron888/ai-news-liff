/**
 * ====================================================================
 * 每日 AI 新聞專刊 — Google Apps Script (GAS) 核心後端
 * 100% 免費無伺服器架構 (Google Sheets + Google News RSS + Gemini Flash)
 * ====================================================================
 */

// 系統預設環境變數 (亦可設定於 Apps Script 的 專案設定 -> 指令碼屬性)
const CONFIG = {
  GEMINI_API_KEY: "", // 請填入 Google AI Studio 免費申請的 API Key
  LINE_CHANNEL_ACCESS_TOKEN: "", // 請填入 LINE Messaging API Channel Access Token
  DEFAULT_KEYWORDS: "具身機器人, 製造業 AI, 智慧工廠",
  NEWS_FETCH_LIMIT: 5 // 每次抓取新聞篇數
};

/**
 * 第一次使用時執行：自動初始化 Google 試算表結構
 */
function setupSheets() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  
  // 1. 初始化 Users 表
  let usersSheet = ss.getSheetByName("Users");
  if (!usersSheet) {
    usersSheet = ss.insertSheet("Users");
    usersSheet.appendRow(["userId", "用戶名稱", "關鍵字", "最後更新時間"]);
    usersSheet.getRange("A1:D1").setBackground("#0F3B82").setFontColor("#FFFFFF").setFontWeight("bold");
    usersSheet.setFrozenRows(1);
  }

  // 2. 初始化 DailyNews 表
  let newsSheet = ss.getSheetByName("DailyNews");
  if (!newsSheet) {
    newsSheet = ss.insertSheet("DailyNews");
    newsSheet.appendRow(["日期", "userId", "關鍵字", "新聞JSON", "建立時間"]);
    newsSheet.getRange("A1:E1").setBackground("#0F3B82").setFontColor("#FFFFFF").setFontWeight("bold");
    newsSheet.setFrozenRows(1);
  }

  Logger.log("✅ 試算表初始化完成！已建立 Users 與 DailyNews 工作表。");
}

/**
 * HTTP GET 處理函式：提供 LIFF 前端資料讀取
 * - action=getNews&userId=xxx
 * - action=getUserSettings&userId=xxx
 */
function doGet(e) {
  const params = e ? e.parameter : {};
  const action = params.action || "getNews";
  const userId = params.userId || "demo_user";

  let responseData = {};

  try {
    if (action === "getUserSettings") {
      const user = getUserRecord(userId);
      responseData = {
        success: true,
        userId: userId,
        keywords: user ? user.keywords : CONFIG.DEFAULT_KEYWORDS
      };
    } else if (action === "getNews") {
      const todayStr = Utilities.formatDate(new Date(), "Asia/Taipei", "yyyy-MM-dd");
      let newsItems = getCachedNews(userId, todayStr);

      // 若今日尚未產生快取，按需 (On-Demand) 即時生成
      if (!newsItems || newsItems.length === 0) {
        const user = getUserRecord(userId);
        const keywords = user ? user.keywords : CONFIG.DEFAULT_KEYWORDS;
        newsItems = generateAndCacheNews(userId, keywords, todayStr);
      }

      responseData = {
        success: true,
        date: todayStr,
        userId: userId,
        data: newsItems
      };
    } else {
      responseData = { success: false, message: "無效的 action 操作" };
    }
  } catch (err) {
    responseData = { success: false, error: err.toString() };
  }

  return ContentService.createTextOutput(JSON.stringify(responseData))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * HTTP POST 處理函式：
 * 1. 處理 LINE Webhook 被動訊息回覆 (免費無限次)
 * 2. 處理 LIFF 前端儲存個人關鍵字
 */
function doPost(e) {
  try {
    const postData = JSON.parse(e.postData.contents);

    // 情況 A: LINE Webhook 事件
    if (postData.events && postData.events.length > 0) {
      const event = postData.events[0];
      const replyToken = event.replyToken;
      const userId = event.source.userId;

      if (event.type === "message" && event.message.type === "text") {
        const text = event.message.text.trim();

        // 判斷指令：設定關鍵字
        if (text.startsWith("關鍵字") || text.startsWith("設定關鍵字")) {
          const rawKeywords = text.replace(/^(關鍵字|設定關鍵字)[:：\s]*/, "").trim();
          if (rawKeywords) {
            saveOrUpdateUser(userId, "LINE用戶", rawKeywords);
            replyLineMessage(replyToken, `✅ 您的專屬關鍵字已成功更新！\n\n📌 目前追蹤：\n「${rawKeywords}」\n\n每日 AI 將根據這些主題為您濃縮重要情報。點擊下方圖文選單即可開啟專屬日報！`);
          } else {
            replyLineMessage(replyToken, `請輸入欲設定的關鍵字，例如：\n關鍵字: 具身機器人, 製造業 AI, 智慧工廠`);
          }
        } else {
          replyLineMessage(replyToken, `您好！我是您的 AI 新聞秘書 🤖\n\n您可以隨時在此傳送：\n「關鍵字: 機器人, 半導體」\n即可自訂專屬新聞主題；或點擊下方選單隨時開啟今日 LIFF 數位日報！`);
        }
      }
      return ContentService.createTextOutput("OK");
    }

    // 情況 B: LIFF 前端更新關鍵字 API
    if (postData.action === "updateKeywords") {
      const userId = postData.userId || "demo_user";
      const userName = postData.userName || "LIFF用戶";
      const keywords = postData.keywords || CONFIG.DEFAULT_KEYWORDS;

      saveOrUpdateUser(userId, userName, keywords);
      
      // 當日快取重置，讓下次開啟能依新關鍵字重抓
      const todayStr = Utilities.formatDate(new Date(), "Asia/Taipei", "yyyy-MM-dd");
      deleteTodayCache(userId, todayStr);

      return ContentService.createTextOutput(JSON.stringify({ success: true, message: "關鍵字已成功儲存" }))
        .setMimeType(ContentService.MimeType.JSON);
    }

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ success: false, error: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * 每日定時批次排程：由 GAS 定時觸發器在每天清晨執行
 */
function dailyBatchUpdate() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const usersSheet = ss.getSheetByName("Users");
  if (!usersSheet) return;

  const data = usersSheet.getDataRange().getValues();
  if (data.length <= 1) return; // 無用戶資料

  const todayStr = Utilities.formatDate(new Date(), "Asia/Taipei", "yyyy-MM-dd");

  for (let i = 1; i < data.length; i++) {
    const userId = data[i][0];
    const keywords = data[i][2] || CONFIG.DEFAULT_KEYWORDS;
    try {
      generateAndCacheNews(userId, keywords, todayStr);
      Utilities.sleep(1000); // 避免觸發 API 頻率限制
    } catch (e) {
      Logger.log("更新用戶 " + userId + " 失敗: " + e.toString());
    }
  }
}

/**
 * 核心處理：抓取 RSS -> 透過 Gemini Flash 產生重點摘要 -> 寫入快取
 */
function generateAndCacheNews(userId, keywords, dateStr) {
  // 1. 抓取 Google News RSS
  const rawNews = fetchGoogleNewsRSS(keywords);
  if (!rawNews || rawNews.length === 0) {
    return [];
  }

  // 2. 呼叫 Gemini API 產出繁體中文摘要
  const apiKey = getApiKey();
  let aiNewsList = [];

  if (apiKey) {
    aiNewsList = summarizeWithGemini(rawNews, keywords, apiKey);
  } else {
    // 若未填入 API Key，提供優雅的預設摘要呈現
    aiNewsList = rawNews.map(item => ({
      title: item.title,
      link: item.link,
      source: item.source,
      pubDate: item.pubDate,
      summary: "已即時擷取該領域最新消息。設定 Gemini API Key 後將自動提供 3 點深度洞察分析。",
      impact: "追蹤最新科技動向，有助於企業評估技術落地時機。"
    }));
  }

  // 3. 儲存至 DailyNews 表
  saveNewsToCache(userId, dateStr, keywords, aiNewsList);

  return aiNewsList;
}

/**
 * 透過 Google News RSS 抓取新聞
 */
function fetchGoogleNewsRSS(keywords) {
  const encodedQuery = encodeURIComponent(keywords + " when:24h");
  const rssUrl = "https://news.google.com/rss/search?q=" + encodedQuery + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant";

  try {
    const response = UrlFetchApp.fetch(rssUrl, { muteHttpExceptions: true });
    if (response.getResponseCode() !== 200) return [];

    const xml = response.getContentText();
    const document = XmlService.parse(xml);
    const root = document.getRootElement();
    const channel = root.getChild("channel");
    if (!channel) return [];

    const items = channel.getChildren("item");
    const results = [];
    const limit = Math.min(items.length, CONFIG.NEWS_FETCH_LIMIT);

    for (let i = 0; i < limit; i++) {
      const item = items[i];
      const title = item.getChildText("title") || "無標題";
      const link = item.getChildText("link") || "";
      const pubDate = item.getChildText("pubDate") || "";
      const sourceElem = item.getChild("source");
      const source = sourceElem ? sourceElem.getText() : "科技綜合";

      results.push({
        title: title,
        link: link,
        pubDate: pubDate,
        source: source
      });
    }
    return results;
  } catch (err) {
    Logger.log("RSS 解析錯誤: " + err.toString());
    return [];
  }
}

/**
 * 呼叫 Google Gemini API 產生結構化繁體中文摘要
 */
function summarizeWithGemini(newsItems, keywords, apiKey) {
  const url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=" + apiKey;

  const prompt = `你是一位資深科技分析師與製造業顧問。請閱讀以下使用者感興趣關鍵字「${keywords}」的最新新聞列表：
${JSON.stringify(newsItems, null, 2)}

請為每篇新聞進行深度分析，嚴格輸出 JSON 陣列（Array of Objects），不可輸出任何 Markdown 標籤或額外文字。
每個物件結構如下：
[
  {
    "title": "新聞標題",
    "link": "新聞原始連結",
    "source": "媒體來源",
    "summary": "以 2 句話繁體中文濃縮最核心的事實與進展",
    "impact": "以 1 句話針鋒相對指出：這對台灣製造業、軟硬整合或一般企業有何實質影響或落地借鏡？"
  }
]`;

  const payload = {
    contents: [{
      parts: [{ text: prompt }]
    }],
    generationConfig: {
      temperature: 0.2,
      responseMimeType: "application/json"
    }
  };

  const options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };

  try {
    const res = UrlFetchApp.fetch(url, options);
    const json = JSON.parse(res.getContentText());
    if (json.candidates && json.candidates[0].content.parts[0].text) {
      const text = json.candidates[0].content.parts[0].text;
      return JSON.parse(text);
    }
  } catch (e) {
    Logger.log("Gemini 呼叫失敗: " + e.toString());
  }

  // Fallback 回退
  return newsItems.map(item => ({
    title: item.title,
    link: item.link,
    source: item.source,
    summary: "今日重點新聞，已自動整理收錄。",
    impact: "建議關注相關技術發展動態。"
  }));
}

/**
 * LINE 免費 Reply Message (不消耗 200 則 Push 額度)
 */
function replyLineMessage(replyToken, text) {
  const token = getLineToken();
  if (!token) {
    Logger.log("未設定 LINE Token，跳過回覆");
    return;
  }

  const url = "https://api.line.me/v2/bot/message/reply";
  const payload = {
    replyToken: replyToken,
    messages: [{
      type: "text",
      text: text
    }]
  };

  UrlFetchApp.fetch(url, {
    method: "post",
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + token
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
}

// ----------------- 資料庫存取輔助函式 -----------------

function getUserRecord(userId) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName("Users");
  if (!sheet) return null;

  const data = sheet.getDataRange().getValues();
  for (let i = 1; i < data.length; i++) {
    if (data[i][0] === userId) {
      return { userId: data[i][0], name: data[i][1], keywords: data[i][2] };
    }
  }
  return null;
}

function saveOrUpdateUser(userId, name, keywords) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName("Users");
  if (!sheet) {
    setupSheets();
    sheet = ss.getSheetByName("Users");
  }

  const data = sheet.getDataRange().getValues();
  const nowStr = Utilities.formatDate(new Date(), "Asia/Taipei", "yyyy-MM-dd HH:mm:ss");

  for (let i = 1; i < data.length; i++) {
    if (data[i][0] === userId) {
      sheet.getRange(i + 1, 2).setValue(name);
      sheet.getRange(i + 1, 3).setValue(keywords);
      sheet.getRange(i + 1, 4).setValue(nowStr);
      return;
    }
  }

  // 新用戶新增一列
  sheet.appendRow([userId, name, keywords, nowStr]);
}

function getCachedNews(userId, dateStr) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName("DailyNews");
  if (!sheet) return null;

  const data = sheet.getDataRange().getValues();
  for (let i = data.length - 1; i >= 1; i--) {
    if (data[i][0] === dateStr && data[i][1] === userId) {
      try {
        return JSON.parse(data[i][3]);
      } catch (e) {
        return null;
      }
    }
  }
  return null;
}

function saveNewsToCache(userId, dateStr, keywords, newsArray) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName("DailyNews");
  if (!sheet) {
    setupSheets();
    sheet = ss.getSheetByName("DailyNews");
  }

  const nowStr = Utilities.formatDate(new Date(), "Asia/Taipei", "yyyy-MM-dd HH:mm:ss");
  sheet.appendRow([dateStr, userId, keywords, JSON.stringify(newsArray), nowStr]);
}

function deleteTodayCache(userId, dateStr) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName("DailyNews");
  if (!sheet) return;

  const data = sheet.getDataRange().getValues();
  for (let i = data.length - 1; i >= 1; i--) {
    if (data[i][0] === dateStr && data[i][1] === userId) {
      sheet.deleteRow(i + 1);
    }
  }
}

function getApiKey() {
  const props = PropertiesService.getScriptProperties();
  return props.getProperty("GEMINI_API_KEY") || CONFIG.GEMINI_API_KEY;
}

function getLineToken() {
  const props = PropertiesService.getScriptProperties();
  return props.getProperty("LINE_CHANNEL_ACCESS_TOKEN") || CONFIG.LINE_CHANNEL_ACCESS_TOKEN;
}
