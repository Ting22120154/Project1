# project1/canary_stack.py
# 功能：建立一個基本的 Lambda 函數，用於測試網站可用性與延遲。

import os   # ← 讀本機 sites.json 用
import json

from aws_cdk import (
    Stack,
    Duration,
    aws_iam as iam,
    aws_lambda as _lambda,
    CfnOutput,
    aws_events as events,             # ← 新增：EventBridge
    aws_events_targets as targets,
    aws_cloudwatch as cloudwatch, # ← 新增：CloudWatch Dashboard / Metric
    aws_sns as sns,                           # ← 新增：SNS
    aws_sqs as sqs,                           # ← 新增：SQS
    aws_sns_subscriptions as subs,            # ← 新增：SNS 訂閱（SQS/E-mail 等）
    aws_cloudwatch_actions as cw_actions,     # ← 新增：把 Alarm 連到 SNS
    aws_dynamodb as dynamodb,          # ← 新增：NoSQL 資料表
    RemovalPolicy,
)

from constructs import Construct


class CanaryStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, target_url: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.canary_fn = _lambda.Function(
            self,
            "CanaryLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="canary_handler.handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={
                "TARGET_URL": target_url,          # 仍保留（雖然第二階段用不到）
                "METRIC_NAMESPACE": "WebHealth"    # ← 新增：自訂 CloudWatch Namespace
            }
        )

        # 允許這支 Lambda 發佈自訂 Metrics
        self.canary_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"]   # PutMetricData 只能是 *，AWS 對此 API 不支援資源級限制
            )
        )

        # 每 5 分鐘觸發一次這支 Lambda
        # 說明：使用 EventBridge Rule 以固定頻率觸發；不用另外給權限。
        events.Rule(
            self,
            "CanaryEvery5Min",
            schedule=events.Schedule.rate(Duration.minutes(5)),   # ← 每 5 分鐘
            targets=[targets.LambdaFunction(self.canary_fn)]      # ← 目標是上面的 Lambda
        )



 # ---------------- CloudWatch Dashboard（最小可用版）----------------
        # 說明：
        # 1) 讀取 lambda/sites.json（與 Lambda 同目錄的網站清單）
        # 2) 為每個 Site 建立兩個 Metric：Availability（Count）、Latency（Milliseconds）
        # 3) 建一個 Dashboard，含兩個圖表：Availability 折線圖、Latency 折線圖

        # 讀取網站清單（在 cdk synth/deploy 時於本機讀檔）
        sites: list[str] = []
        sites_file = os.path.join(os.path.dirname(__file__), "..", "lambda", "sites.json")
        try:
            with open(sites_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    # 僅保留非空白字串
                    sites = [s.strip() for s in data if isinstance(s, str) and s.strip()]
        except Exception:
            # 若讀不到檔案也不阻擋部署，只是 Dashboard 會沒資料線
            sites = []

        # 建立 Dashboard
        dashboard = cloudwatch.Dashboard(
            self,
            "WebHealthDashboard",
            dashboard_name="WebHealth-Dashboard"  # 你在 Console 會看到的名稱
        )

        # 準備兩組 metric 清單：左圖 Availability、右圖 Latency
        availability_metrics: list[cloudwatch.IMetric] = []
        latency_metrics: list[cloudwatch.IMetric] = []

        # 將每個網站加到圖表系列
        for site in sites:
            # Availability（0/1），以 5 分鐘為區間做平均
            availability_metrics.append(
                cloudwatch.Metric(
                    namespace="WebHealth",                # 與 Lambda 上報的 METRIC_NAMESPACE 一致
                    metric_name="Availability",
                    dimensions_map={"Site": site},        # 維度：Site=網址
                    statistic="Average",
                    period=Duration.minutes(5),
                    unit=cloudwatch.Unit.COUNT
                )
            )
            # Latency（毫秒），以 5 分鐘為區間做平均
            latency_metrics.append(
                cloudwatch.Metric(
                    namespace="WebHealth",
                    metric_name="Latency",
                    dimensions_map={"Site": site},
                    statistic="Average",
                    period=Duration.minutes(5),
                    unit=cloudwatch.Unit.MILLISECONDS
                )
            )

        # 圖表 1：Availability 折線圖（0~1）
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Availability (0 or 1) by Site",  # 圖表標題
                left=availability_metrics,               # 多條線：每個 Site 一條
                left_y_axis=cloudwatch.YAxisProps(min=0, max=1),  # 固定 0~1
                width=24
            )
        )

        # 圖表 2：Latency 折線圖（毫秒）
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Latency (ms) by Site",
                left=latency_metrics,        # 多條線：每個 Site 一條
                width=24
            )
        )



 # ---------------- CloudWatch Alarms（最小可用版）----------------
        # 說明：
        # - 每個 Site 建立兩個告警：
        #   1) Availability < 1  → 視為站點不可用（當期 5 分鐘平均）
        #   2) Latency > 1000ms → 視為延遲過高
        # - 先不串 SNS / SQS（之後階段再加），這裡只做最小告警並放到 Dashboard。

        LATENCY_THRESHOLD_MS = 1000  # ← 之後可改：延遲門檻（毫秒）

        availability_alarms: list[cloudwatch.Alarm] = []
        latency_alarms: list[cloudwatch.Alarm] = []

        for site in sites:
            # 重新建立對應 Site 的 metric（和上面的圖表一致）
            m_avail = cloudwatch.Metric(
                namespace="WebHealth",
                metric_name="Availability",
                dimensions_map={"Site": site},
                statistic="Average",
                period=Duration.minutes(5),
                unit=cloudwatch.Unit.COUNT,
            )
            m_latency = cloudwatch.Metric(
                namespace="WebHealth",
                metric_name="Latency",
                dimensions_map={"Site": site},
                statistic="Average",
                period=Duration.minutes(5),
                unit=cloudwatch.Unit.MILLISECONDS,
            )

            # 告警 1：Availability < 1（當期 5 分鐘平均）
            a1 = cloudwatch.Alarm(
                self,
                f"AvailAlarm-{site}",
                metric=m_avail,
                threshold=1.0,
                evaluation_periods=1,  # 只看最近一個 period（5 分鐘）
                comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,  # 沒資料不當作告警
                alarm_description=f"Availability below 1 for {site}",
            )
            availability_alarms.append(a1)

            # 告警 2：Latency > 門檻
            a2 = cloudwatch.Alarm(
                self,
                f"LatencyAlarm-{site}",
                metric=m_latency,
                threshold=LATENCY_THRESHOLD_MS,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
                alarm_description=f"Latency above {LATENCY_THRESHOLD_MS} ms for {site}",
            )
            latency_alarms.append(a2)

        # 把告警小工具放到 Dashboard（每個告警一個卡片）
        for alarm in availability_alarms:
            dashboard.add_widgets(
                cloudwatch.AlarmWidget(
                    title=f"DOWN: {alarm.alarm_name}",  # 告警卡片標題
                    alarm=alarm,
                    width=12
                )
            )
        for alarm in latency_alarms:
            dashboard.add_widgets(
                cloudwatch.AlarmWidget(
                    title=f"SLOW: {alarm.alarm_name}",
                    alarm=alarm,
                    width=12
                )
            )


        # ---------------- SNS + SQS wiring for Alarms（最小可用）----------------
        # 說明：
        # - 以「指標類型」分流建立兩個 Topic：Availability / Latency
        # - 各自建立一個 SQS 佇列並訂閱對應的 Topic（方便程式消費或日後擴充）
        # - 將 CloudWatch Alarms 動作指到對應的 SNS Topic
        # - 這種設計天然就能「用 Topic 名稱」區分 metric type（相當於分類 tag）

        # 1) SNS Topics
        availability_topic = sns.Topic(
            self,
            "AvailabilityTopic",
            display_name="WebHealth Availability Alerts",  # Console 顯示名稱
            topic_name="webhealth-availability-alerts"     # 可選，指定 Topic 名稱
        )
        latency_topic = sns.Topic(
            self,
            "LatencyTopic",
            display_name="WebHealth Latency Alerts",
            topic_name="webhealth-latency-alerts"
        )

        # 2) SQS Queues（各自訂閱對應 Topic）
        availability_queue = sqs.Queue(
            self,
            "AvailabilityAlertsQueue",
            visibility_timeout=Duration.seconds(60)  # 消費者處理時間緩衝
        )
        latency_queue = sqs.Queue(
            self,
            "LatencyAlertsQueue",
            visibility_timeout=Duration.seconds(60)
        )

        # 訂閱：讓 Topic 發佈的訊息流入對應的 Queue
        availability_topic.add_subscription(subs.SqsSubscription(availability_queue))
        latency_topic.add_subscription(subs.SqsSubscription(latency_queue))

        # 3) 將 Alarm 綁定到對應 SNS Topic
        #    - Availability 類型的告警 → 發布到 availability_topic
        #    - Latency 類型的告警     → 發布到 latency_topic
        for alarm in availability_alarms:
            alarm.add_alarm_action(cw_actions.SnsAction(availability_topic))
            # 可選：恢復 OK 時也通知
            alarm.add_ok_action(cw_actions.SnsAction(availability_topic))

        for alarm in latency_alarms:
            alarm.add_alarm_action(cw_actions.SnsAction(latency_topic))
            # 可選：恢復 OK 時也通知
            alarm.add_ok_action(cw_actions.SnsAction(latency_topic))

        # 4)（可見性）輸出 Topic / Queue 的 ARN
        CfnOutput(self, "AvailabilityTopicArn", value=availability_topic.topic_arn)
        CfnOutput(self, "LatencyTopicArn", value=latency_topic.topic_arn)
        CfnOutput(self, "AvailabilityQueueArn", value=availability_queue.queue_arn)
        CfnOutput(self, "LatencyQueueArn", value=latency_queue.queue_arn)

        # ---------------- DynamoDB (NoSQL) + Logger Lambda ----------------
        # 說明：
        # - DynamoDB 用來記錄告警事件（Alarm name、Metric、Timestamp、Message）
        # - Lambda 由 SNS 觸發，解析告警訊息後寫入資料表
        # - 這是最小可用版本（不考慮批次、重試、格式化）

        # 1️⃣ 建立 DynamoDB 資料表
        alarm_table = dynamodb.Table(
            self,
            "AlarmLogTable",
            partition_key=dynamodb.Attribute(
                name="AlarmName", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="Timestamp", type=dynamodb.AttributeType.STRING
            ),
            removal_policy=RemovalPolicy.DESTROY,   # 方便開發重建（正式環境應改成 RETAIN）
            table_name="WebHealth_AlarmLogs"
        )

        # 2️⃣ 建立 Lambda：從 SNS 取得訊息，寫入 DynamoDB
        alarm_logger_fn = _lambda.Function(
            self,
            "AlarmLoggerFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="alarm_logger.handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(10),
            memory_size=128,
            environment={
                "TABLE_NAME": alarm_table.table_name
            }
        )

        # 3️⃣ 給 Lambda 權限寫入 DynamoDB
        alarm_table.grant_write_data(alarm_logger_fn)

        # 4️⃣ 讓 SNS 觸發這支 Lambda（兩個 Topic 都連進來）
        availability_topic.add_subscription(subs.LambdaSubscription(alarm_logger_fn))
        latency_topic.add_subscription(subs.LambdaSubscription(alarm_logger_fn))

        # 5️⃣ 輸出 DynamoDB Table 名稱
        CfnOutput(self, "AlarmLogTableName", value=alarm_table.table_name)




        CfnOutput(self, "CanaryFunctionName", value=self.canary_fn.function_name)