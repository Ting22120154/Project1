# project1/canary_stack.py
# 功能：建立一個基本的 Lambda 函數，用於測試網站可用性與延遲。

from aws_cdk import (
    Stack,
    Duration,
    aws_iam as iam,
    aws_lambda as _lambda,
    CfnOutput,
    aws_events as events,             # ← 新增：EventBridge
    aws_events_targets as targets,
    
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

        CfnOutput(self, "CanaryFunctionName", value=self.canary_fn.function_name)