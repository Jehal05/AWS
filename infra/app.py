import aws_cdk as cdk
from stack import RenewFlowStack

app = cdk.App()
RenewFlowStack(app, "RenewFlow", env=cdk.Environment(region=app.node.try_get_context("region") or "us-east-1"))
app.synth()
