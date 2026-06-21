#!/usr/bin/env python3
"""
小山園 (Marukyu-Koyamaen) 抹茶補貨監控 → LINE 通知（自動抓取分類版）

做法：
  1. 給定幾個「分類頁」網址，程式自動抓出底下所有商品。
  2. 逐一檢查商品頁是否含 "This product is currently out of stock and unavailable."
     有這句 = 缺貨；消失 = 補貨。
  3. 只在「缺貨 → 有貨」的轉換時發 LINE，避免洗版。
  分類有新品也會自動納入，不用手動維護商品清單。

用法：
  python check_stock.py          # 正常檢查
  python check_stock.py test     # 發一則測試訊息，確認 LINE 設定 OK
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

# ─────────────────────────────────────────────────────────────
# 要監控的「分類頁」。想加減分類就改這裡（例如把寺院用 kancho 也加進來）。
# ─────────────────────────────────────────────────────────────
CATEGORY_URLS = [
    "https://www.marukyu-koyamaen.co.jp/english/shop/products/catalog/matcha/principal",     # 精選
    "https://www.marukyu-koyamaen.co.jp/english/shop/products/catalog/matcha/gentei",        # 限定
    "https://www.marukyu-koyamaen.co.jp/english/shop/products/catalog/matcha/tea-schools",   # 茶道流派
]

# 額外想單獨盯、但不屬於上面分類的商品，貼這裡（沒有就留空）：
EXTRA_PRODUCTS = {
    # "顯示名稱": "https://www.marukyu-koyamaen.co.jp/english/shop/products/xxxx",
}

# 缺貨判斷字串（小山園英文站固定文案）
OOS_MARKER = "This product is currently out of stock and unavailable."
# 確認商品頁確實抓成功（避免被擋／錯誤頁被誤判成「補貨」）
SANITY_MARKERS = ("Product Detail", "SKU")

BASE = "https://www.marukyu-koyamaen.co.jp"
# 只抓 /english/shop/products/{商品ID}，自動排除 /products/catalog/... 等分類連結
PRODUCT_PATH_RE = re.compile(r"^/english/shop/products/([0-9a-zA-Z]+)/?$")
ANCHOR_RE = re.compile(r"<a\b([^>]*)>", re.IGNORECASE)
HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)
TITLE_RE = re.compile(r'title="([^"]+)"', re.IGNORECASE)

STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))
REQUEST_DELAY = float(os.environ.get("REQUEST_DELAY", "3"))  # 每次請求間隔秒數（對伺服器客氣、降低被擋機率）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "")


def http_get(url: str):
    try:
        return requests.get(url, headers=HEADERS, timeout=20)
    except requests.RequestException as e:
        print(f"  ⚠️ 連線失敗：{e}")
        return None


def discover_products(category_urls) -> dict:
    """從分類頁自動抓出 {商品網址: 名稱}。"""
    found = {}
    for cat in category_urls:
        before = len(found)
        r = http_get(cat)
        if r is None or r.status_code != 200 or "shop/products" not in r.text:
            print(f"⚠️ 分類頁抓取異常，略過：{cat}")
            time.sleep(REQUEST_DELAY)
            continue

        for attrs in ANCHOR_RE.findall(r.text):
            href_m = HREF_RE.search(attrs)
            if not href_m:
                continue
            href = href_m.group(1)
            path = re.sub(r"^https?://[^/]+", "", href)  # 轉成路徑（去掉網域）
            pm = PRODUCT_PATH_RE.match(path)
            if not pm:
                continue
            url = BASE + path
            title_m = TITLE_RE.search(attrs)
            name = title_m.group(1).strip() if title_m else pm.group(1)
            found.setdefault(url, name)

        print(f"  分類 {cat.rsplit('/', 1)[-1]}：新增 {len(found) - before} 項")
        time.sleep(REQUEST_DELAY)
    return found


def fetch_status(url: str) -> str:
    """回傳 'in_stock' / 'out_of_stock' / 'unknown'。"""
    r = http_get(url)
    if r is None:
        return "unknown"
    if r.status_code != 200:
        print(f"  ⚠️ HTTP {r.status_code}")
        return "unknown"
    html = r.text
    if not any(m in html for m in SANITY_MARKERS):
        print("  ⚠️ 頁面格式不符（可能被擋），保留舊狀態")
        return "unknown"
    return "out_of_stock" if OOS_MARKER in html else "in_stock"


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def send_line(text: str) -> None:
    if not LINE_TOKEN or not LINE_USER_ID:
        print("❌ 未設定 LINE_CHANNEL_ACCESS_TOKEN / LINE_USER_ID，跳過發送")
        return
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_TOKEN}",
        },
        json={"to": LINE_USER_ID, "messages": [{"type": "text", "text": text}]},
        timeout=20,
    )
    if resp.status_code == 200:
        print("✅ LINE 已送出")
    else:
        print(f"❌ LINE 發送失敗：{resp.status_code} {resp.text}")


def main() -> None:
    # 測試模式
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        send_line("🍵 測試訊息：小山園補貨通知設定成功！")
        return

    # 1) 自動抓商品（分類 + 額外指定）
    products = discover_products(CATEGORY_URLS)
    for name, url in EXTRA_PRODUCTS.items():
        products.setdefault(url, name)
    print(f"共監控 {len(products)} 項商品\n")

    if not products:
        print("⚠️ 這次沒抓到任何商品（可能整批被擋），保留舊狀態，下輪再試。")
        return

    # 2) 逐一檢查
    state = load_state()
    restocked = []
    for url, name in products.items():
        status = fetch_status(url)
        prev = state.get(url, "unknown")
        print(f"{name}: {prev} → {status}")

        if status == "unknown":
            time.sleep(REQUEST_DELAY)
            continue  # 抓失敗就保留舊狀態，不誤報

        if prev == "out_of_stock" and status == "in_stock":
            restocked.append((name, url))

        state[url] = status
        time.sleep(REQUEST_DELAY)

    save_state(state)

    # 3) 有補貨才通知
    if restocked:
        lines = ["🍵 小山園補貨啦！"]
        for name, url in restocked:
            lines.append(f"\n• {name}\n{url}")
        lines.append("\n要登入才買得到，手刀結帳 👉")
        send_line("\n".join(lines))
    else:
        print("這次沒有新補貨。")


if __name__ == "__main__":
    main()
