import sys
from pathlib import Path

import pytest

cdk = pytest.importorskip("aws_cdk")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "infra"))


def test_stack_synthesizes_with_the_expected_guardrails():
    from stack import RenewFlowStack

    app = cdk.App()
    RenewFlowStack(app, "T", env=cdk.Environment(region="us-east-1", account="123456789012"))
    template = app.synth().stacks[0].template
    resources = template["Resources"].values()
    kinds = {r["Type"] for r in resources}
    assert {"AWS::EC2::Instance", "AWS::CloudFront::Distribution", "AWS::SNS::Topic", "AWS::Budgets::Budget"} <= kinds
    assert "AWS::EC2::NatGateway" not in kinds  # a NAT gateway alone would blow the $10 cap
    budget = next(r for r in template["Resources"].values() if r["Type"] == "AWS::Budgets::Budget")
    assert budget["Properties"]["Budget"]["BudgetLimit"]["Amount"] == 10
