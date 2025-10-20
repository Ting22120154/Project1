# project1/canary_stack.py
# 功能：建立一個基本的 Lambda 函數，用於測試網站可用性與延遲。

from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    CfnOutput,
)
from constructs import Construct


class CanaryStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, *, target_url: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 建立 Lambda 函數
        self.canary_fn = _lambda.Function(
            self,
            "CanaryLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="canary_handler.handler",       # lambda/canary_handler.py 的 handler 函式
            code=_lambda.Code.from_asset("lambda"),  # 指向 lambda/ 資料夾
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={
                "TARGET_URL": target_url
            }
        )

        # 輸出 Lambda 名稱，方便在部署後查找
        CfnOutput(
            self,
            "CanaryFunctionName",
            value=self.canary_fn.function_name,
            description="部署出的 Canary Lambda 名稱"
        )