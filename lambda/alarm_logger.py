# lambda/alarm_logger.py
# 功能：接收 SNS 告警訊息，解析後寫入 DynamoDB。
# 說明：
#   - SNS 事件結構：event["Records"][0]["Sns"]["Message"]
#   - Message 為 JSON 字串，內含 AlarmName、NewStateValue、NewStateReason 等。
#   - 本 Lambda 解析後將資料記錄到 DynamoDB。

import os
import json
import boto3
from datetime import datetime

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])

def handler(event, context):
    # SNS 事件可能包含多筆記錄
    for record in event.get("Records", []):
        try:
            sns_message = record["Sns"]["Message"]
            msg = json.loads(sns_message) if sns_message.startswith("{") else {"RawMessage": sns_message}
        except Exception as e:
            print(f"Failed to parse SNS message: {e}")
            continue

        # 準備寫入 DynamoDB 的項目
        item = {
            "AlarmName": msg.get("AlarmName", "Unknown"),
            "Timestamp": datetime.utcnow().isoformat(),
            "NewStateValue": msg.get("NewStateValue", "UNKNOWN"),
            "Reason": msg.get("NewStateReason", msg.get("RawMessage", ""))[:500]
        }

        try:
            table.put_item(Item=item)
            print(f"✅ Logged alarm: {item}")
        except Exception as e:
            print(f"❌ Failed to write to DynamoDB: {e}")

    return {"ok": True}
