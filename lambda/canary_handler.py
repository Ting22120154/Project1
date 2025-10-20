# lambda/canary_handler.py
# 功能：量測指定網站的可用性與延遲，並輸出到 CloudWatch Logs。
# 說明：
#   - 以環境變數 TARGET_URL 接收要測試的網址。
#   - 不需外部套件（只用 Python 內建 urllib）。
#   - 只實現最小基本功能，不加入任何額外裝飾或擴充。

import os        # 讀取環境變數用
import time      # 用來計算延遲時間
import urllib.request   # 發送 HTTP 請求
import urllib.error     # 捕捉網路錯誤


def handler(event, context):
    # Lambda 主要進入點，AWS 會自動呼叫這個函式
    target_url = os.environ.get("TARGET_URL", "").strip()  # 從環境變數取得要測的網址

    if not target_url:
        print("[❌] TARGET_URL not set")  # 如果沒有設定網址就報錯
        return {"ok": False, "error": "TARGET_URL not set"}

    start = time.perf_counter()  # 記錄開始時間
    availability = 0             # 預設為不可用
    latency_ms = None            # 延遲時間
    status_code = None           # HTTP 狀態碼
    error_msg = None             # 錯誤訊息

    try:
        # 建立 HTTP 請求
        req = urllib.request.Request(target_url)
        # 發送請求（設定 10 秒逾時）
        with urllib.request.urlopen(req, timeout=10) as resp:
            status_code = resp.getcode()  # 取得 HTTP 狀態碼
            if status_code and status_code < 400:
                availability = 1          # 狀態碼小於400代表網站可用
    except Exception as e:
        # 捕捉所有錯誤，記錄錯誤訊息
        error_msg = str(e)
    finally:
        # 計算延遲（毫秒）
        end = time.perf_counter()
        latency_ms = round((end - start) * 1000, 2)

    # 輸出測試結果到 CloudWatch Logs
    print({
        "target_url": target_url,
        "availability": availability,
        "latency_ms": latency_ms,
        "status_code": status_code,
        "error": error_msg
    })

    # 回傳結果（方便後續測試或串接）
    return {
        "availability": availability,
        "latency_ms": latency_ms,
        "status_code": status_code,
        "error": error_msg
    }
