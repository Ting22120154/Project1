import os
import aws_cdk as cdk

from project1.project1_stack import Project1Stack

app = cdk.App()

# Use the account/region from the current CLI credentials.
# This is the safest way while developing locally: it picks up
# CDK_DEFAULT_ACCOUNT and CDK_DEFAULT_REGION at synth/deploy time.
env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION"),
)

# The root stack of this project.
Project1Stack(app, "Project1Stack", env=env)

app.synth()