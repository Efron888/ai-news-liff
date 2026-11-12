# 每日 AI 新聞專刊 (LINE LIFF + GAS + Gemini 免費整合方案)

本專案提供完全 **0 元終身免費** 的 LINE 個人化 AI 新聞日報解決方案。避開 LINE 官方帳號每月 200 則的主動推播限制，採用 **LIFF 長網頁（個人數位報紙）** 搭配 **被動式關鍵字設定**，支援無限次閱讀與全自動定時 AI 摘要。

---

## 專案結構

```text
├── gas/
│   └── Code.gs                  # Google Apps Script 核心後端 (Google Sheet DB + RSS + Gemini API + LINE Webhook)
├── public/
│   └── index.html               # LINE LIFF 前端長網頁 (科技藍高質感卡片、關鍵字設定抽屜、響應式排版)
└── scripts/
    ├── verify_rss_and_digest.py # RSS 擷取與繁中解析驗證腳本
    └── test_pipeline.py         # 端到端自動化單元測試腳本 (已通過驗證)
```

---

## 3 步極簡啟用流程

### 步驟 1：部署後端（Google 試算表 + Apps Script）
1. 在 Google 雲端硬碟新增一張空的 **Google 試算表**。
2. 點選上方選單 **擴充功能 $\rightarrow$ Apps Script**。
3. 將本專案 `gas/Code.gs` 的完整程式碼複製並貼上取代原本內容。
4. 點選上方函式選單，選擇 `setupSheets` 並點擊「**執行**」（系統會自動為您建好 `Users` 與 `DailyNews` 兩張資料表）。
5. 點選右上角「**部署 $\rightarrow$ 新部署**」：
   - 種類選擇：**網頁應用程式 (Web App)**
   - 誰可以存取：**所有人 (Anyone)**
   - 點擊部署後複製產生的 **網頁應用程式網址 (Web App URL)**。
6. *(選用)* 設定每日清晨自動更新：在 Apps Script 左側點擊「鬧鐘圖示（觸發條件）」$\rightarrow$ 新增觸發條件 $\rightarrow$ 選擇函式 `dailyBatchUpdate` $\rightarrow$ 時間驅動（每天早上 6:00 至 7:00）。

---

### 步驟 2：部署前端 LIFF 長網頁
1. 將 `public/index.html` 中的 `APP_CONFIG.GAS_EXEC_URL` 換成您在步驟 1 取得的網址。
2. 將 `public/index.html` 免費託管至 **GitHub Pages** 或 **Vercel**（直接將檔案上傳即可取得公開網址）。
3. 前往 [LINE Developers 控制台](https://developers.line.biz/)：
   - 進入您的 Provider $\rightarrow$ Messaging API 或 LINE Login 頻道。
   - 點選 **LIFF** 標籤頁 $\rightarrow$ 新增一個 LIFF App。
   - **Size** 選擇 **Full**。
   - **Endpoint URL** 填入您託管的網址。
   - 複製取得的 `LIFF ID`，回填到 `index.html` 的 `APP_CONFIG.LIFF_ID`。

---

### 步驟 3：掛載至 LINE 官方帳號
1. 前往 LINE Official Account Manager，在「**圖文選單 (Rich Menu)**」新增一塊按鈕，動作選擇「**開啟連結**」，填入您的 LIFF 網址：`https://liff.line.me/{您的LIFF_ID}`。
2. 使用者在官方帳號對話框內傳送：`關鍵字: 具身機器人, 製造業 AI`，即可自動綁定主題！
3. 任何時候點擊選單即可直接開啟精美的個人化數位日報。
