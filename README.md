# 🍵 小山園抹茶補貨 → LINE 通知

監控 Marukyu-Koyamaen 官網，**缺貨→補貨**時自動推播 LINE 給你。
靠 GitHub Actions 免費代跑，每 15 分鐘檢查一次，不用開電腦、不用主機。

**目前監控這 3 個分類底下所有商品**（程式會自動抓，分類新增商品也會自動納入）：

- Principal matcha（精選抹茶）
- Limited Edition Teas（限定）
- Matcha Favored by Tea Schools（茶道流派）

---

## 檔案

| 檔案 | 放哪 |
|------|------|
| `check_stock.py` | repo 根目錄 |
| `stock-check.yml` | 放到 `.github/workflows/stock-check.yml` |

---

## A. 申請 LINE 通知（Messaging API）

> LINE Notify 已停，現在用 Messaging API。免費額度個人用綽綽有餘。

1. 進 **LINE Developers Console** → 登入 → 建一個 Provider（名字隨意）。
2. 在該 Provider 下建 **Messaging API channel**（會同時產生一個 LINE 官方帳號）。
3. **加自己為好友**：channel 的「Messaging API」分頁有 QR code，用手機掃描加入。
4. **拿 Channel access token**：Messaging API 分頁 →「Channel access token (long-lived)」按 Issue → 複製。
5. **拿你的 User ID**：channel 的「Basic settings」分頁最下方「Your user ID」（U 開頭那串）→ 複製。
   - 若沒顯示，先到 LINE 官方帳號管理後台把帳號與此 channel 連動一次即可出現。

這兩個值（**token** 和 **user ID**）等下要用。

---

## B. 放上 GitHub

1. 建一個 repo（Private 即可），把 `check_stock.py` 放根目錄、`stock-check.yml` 放 `.github/workflows/`。
2. **Settings → Secrets and variables → Actions → New repository secret**，新增兩個：
   - `LINE_CHANNEL_ACCESS_TOKEN` = 剛剛的 token
   - `LINE_USER_ID` = 剛剛的 U 開頭 user ID
3. **Settings → Actions → General → Workflow permissions** 改成 **Read and write permissions**（讓它能寫回 state.json）。
4. 到 **Actions** 分頁，若提示啟用就啟用。可先按 **Run workflow** 手動跑一次測試。

第一次跑只會「記錄目前庫存狀態」當基準，不會發通知；之後只要有商品從缺貨變有貨就會推 LINE。

---

## C. 先確認 LINE 會通

本機（或 Actions 手動跑）測一發：

```bash
pip install requests
LINE_CHANNEL_ACCESS_TOKEN=你的token LINE_USER_ID=你的userID python check_stock.py test
```

LINE 有收到「測試訊息」就代表設定成功。

---

## D. 客製

- **加減監控分類**：打開 `check_stock.py`，改 `CATEGORY_URLS`。例如把寺院用一起盯，就加一行
  `".../catalog/matcha/kancho"`。程式會自動抓該分類底下所有商品。
- **單獨盯某一款**（不分分類）：把商品頁網址貼進 `EXTRA_PRODUCTS`。
- **改檢查頻率**：改 `stock-check.yml` 的 cron。`*/15` = 每 15 分；`*/30` = 每 30 分。（GitHub 排程最短約 5 分鐘，且偶有延遲。）
- **間隔禮貌度**：環境變數 `REQUEST_DELAY`（預設 3 秒）控制每次請求間的等待，降低被網站擋的機率。

---

## 已知限制

- 偵測是**整個商品**層級（官網非登入狀態看不到單一尺寸庫存）。只要該商品任一尺寸補貨，缺貨文案就會消失 → 你會收到通知。
- 官網有 bot 偵測，偶爾會擋。程式遇到被擋 / 抓取失敗時會「保留舊狀態、不誤報」，漏一輪沒關係，下一輪會補上。`REQUEST_DELAY` 拉長一點可降低被擋機率。
- 補貨秒殺很常見，收到通知請盡快結帳（建議事先在官網登入好）。
