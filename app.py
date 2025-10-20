import os
import aws_cdk as cdk

from project1.project1_stack import Project1Stack
from project1.canary_stack import CanaryStack

app = cdk.App()

# Use the account/region from the current CLI credentials.
# This is the safest way while developing locally: it picks up
# CDK_DEFAULT_ACCOUNT and CDK_DEFAULT_REGION at synth/deploy time.
env = cdk.Environment(
    account="209540198451",       # <<< 換成你的 AWS Account ID
    region="ap-southeast-2"       # <<< 換成你要部署的區域
)

# The root stack of this project.
Project1Stack(app, "Project1Stack", env=env)

# 建立 Canary Stack
CanaryStack(
    app,
    "CanaryStack",
    target_url="https://www.bbc.com/",  # 你要測的網址
    env=env
)

app.synth()