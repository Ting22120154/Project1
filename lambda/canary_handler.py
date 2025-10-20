# lambda/canary_handler.py
# 功能：讀取同資料夾的 sites.json，逐一量測每個網站的可用性與延遲，
#      並將結果輸出到 CloudWatch Logs，同時寫入 CloudWatch Metrics。
# 說明：
#   - 只使用 Python 內建模組與 boto3（Lambda 內建提供）。
#   - 若 sites.json 不存在或格式錯誤，會在日誌中顯示錯誤並結束。

import os          # 讀取檔案路徑用
import time        # 計時用
import json        # 解析 JSON 用
import urllib.request   # 發送 HTTP 請求
import urllib.error     # 捕捉網路錯誤
import boto3       # AWS SDK（Lambda 內建提供）

# 在全域初始化 CloudWatch client（效能較好）
CW = boto3.client("cloudwatch")


def check_one(url):
    # 量測單一網址：回傳 availability / latency_ms / status_code / error
    start = time.perf_counter()  # 開始計時
    availability = 0
    latency_ms = None
    status_code = None
    error_msg = None

    try:
        # 建立一個 HTTP 請求物件
        req = urllib.request.Request(url)
        # 發送請求（設定逾時 10 秒）
        with urllib.request.urlopen(req, timeout=10) as resp:
            status_code = resp.getcode()
            if status_code and status_code < 400:
                availability = 1  # 網站可用
    except Exception as e:
        error_msg = str(e)
    finally:
        # 無論成功與否都計算延遲時間
        end = time.perf_counter()
        latency_ms = round((end - start) * 1000, 2)

    return {
        "target_url": url,
        "availability": availability,
        "latency_ms": latency_ms,
        "status_code": status_code,
        "error": error_msg
    }


def put_metrics(namespace, url, availability, latency_ms):
    # 將兩個指標寫入 CloudWatch：
    #   - Availability：0/1（Count）
    #   - Latency：毫秒（Milliseconds）
    CW.put_metric_data(
        Namespace=namespace,
        MetricData=[
            {
                "MetricName": "Availability",
                "Dimensions": [{"Name": "Site", "Value": url}],
                "Value": float(availability),
                "Unit": "Count"
            },
            {
                "MetricName": "Latency",
                "Dimensions": [{"Name": "Site", "Value": url}],
                "Value": float(latency_ms) if latency_ms is not None else 0.0,
                "Unit": "Milliseconds"
            }
        ]
    )


def handler(event, context):
    # Lambda 主要進入點：讀 sites.json，逐一檢查每個網址
    here = os.path.dirname(__file__)                 # 取得目前檔案所在資料夾
    sites_path = os.path.join(here, "sites.json")    # 組出 sites.json 路徑

    if not os.path.exists(sites_path):
        # 沒有網站清單檔案，直接回報錯誤
        msg = "sites.json not found under /lambda"
        print({"ok": False, "error": msg})
        return {"ok": False, "error": msg}

    try:
        # 讀取並解析 JSON
        with open(sites_path, "r", encoding="utf-8") as f:
            sites = json.load(f)
        # 確認資料型態是陣列
        if not isinstance(sites, list):
            raise ValueError("sites.json must be a JSON array of URLs")
    except Exception as e:
        print({"ok": False, "error": f"failed to load sites.json: {e}"})
        return {"ok": False, "error": f"failed to load sites.json: {e}"}

    results = []  # 收集所有網站的量測結果

    #--------------------執行 寫入 CloudWatch------------------------------------------------
    for url in sites:  # 逐一讀取 JSON 裡的網址
        # 略過不是字串的項目，避免壞資料造成錯誤
        if not isinstance(url, str) or not url.strip():
            continue
        url = url.strip()  # 去除空白
        result = check_one(url)  # 測試網站
        print(result)  # 每個結果都印到 CloudWatch Logs

        # 🟢 把量測結果寫入 CloudWatch Metrics
        try:
            namespace = os.environ.get("METRIC_NAMESPACE", "WebHealth")
            put_metrics(namespace, url, result["availability"], result["latency_ms"])
        except Exception as e:
            # 若發送 Metrics 失敗，記錄錯誤但不中斷
            print({"metric_error": str(e), "site": url})

        # 將結果加入總表
        results.append(result)

    # 回傳彙總結果（方便測試/除錯）
    return {"ok": True, "count": len(results), "results": results}
