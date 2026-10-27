"""RenewFlow on AWS, sized for a hackathon demo that stays up for two weeks on a small budget.

    CloudFront (free HTTPS)  ->  one t4g.micro running the app + SQLite on its EBS volume
    SNS topic  <-  WhatsApp events (End User Messaging Social) and SES events  ->  /webhooks/sns/<token>
    Bedrock, SES and Social Messaging are called straight from the instance role (no keys).

Rough cost: instance ~$6/mo, public IPv4 ~$3.6/mo, EBS ~$0.6/mo, CloudFront/SNS/budget free tier.
A $10 AWS Budget with email alerts is created alongside it.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    Stack,
)
from aws_cdk import (
    aws_budgets as budgets,
)
from aws_cdk import (
    aws_cloudfront as cloudfront,
)
from aws_cdk import (
    aws_cloudfront_origins as origins,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_ses as ses,
)
from aws_cdk import (
    aws_sns as sns,
)
from aws_cdk import (
    aws_ssm as ssm,
)
from constructs import Construct

USER_DATA = """
set -euxo pipefail
dnf install -y python3.11 python3.11-pip git
id renewflow || useradd --system --create-home --home-dir /opt/renewflow renewflow
sudo -u renewflow git clone --depth 1 ${Repo} /opt/renewflow/app
sudo -u renewflow python3.11 -m venv /opt/renewflow/venv
sudo -u renewflow /opt/renewflow/venv/bin/pip install "/opt/renewflow/app[aws]"
# The stack publishes the CloudFront domain once it exists (it depends on this instance).
for i in $(seq 1 90); do
  BASE=$(aws ssm get-parameter --name /renewflow/base-url --query Parameter.Value --output text --region ${Region}) && break
  sleep 10
done
cat > /etc/renewflow.env <<ENV
RENEWFLOW_MODE=aws
RENEWFLOW_MODEL=bedrock
RENEWFLOW_CHANNELS=whatsapp,email
RENEWFLOW_LOCAL_CHANNELS=${LocalChannels}
RENEWFLOW_DB=/opt/renewflow/renewflow.db
RENEWFLOW_BASE_URL=https://$BASE
RENEWFLOW_SES_FROM=${SesFrom}
RENEWFLOW_SES_CONFIG_SET=${ConfigSet}
RENEWFLOW_WA_PHONE_ID=${WaPhone}
RENEWFLOW_WEBHOOK_TOKEN=${Token}
RENEWFLOW_ADMIN_TOKEN=${AdminToken}
RENEWFLOW_SNS_TOPIC_ARNS=${Topic}
AWS_REGION=${Region}
ENV
chmod 600 /etc/renewflow.env
cat > /etc/systemd/system/renewflow.service <<'UNIT'
[Unit]
Description=RenewFlow
After=network-online.target
[Service]
User=renewflow
EnvironmentFile=/etc/renewflow.env
ExecStart=/opt/renewflow/venv/bin/python -m renewflow --host 0.0.0.0 --port 80
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now renewflow
"""


class RenewFlowStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        repo = cdk.CfnParameter(self, "RepoUrl", default="https://github.com/Jehal05/AWS.git")
        token = cdk.CfnParameter(
            self, "WebhookToken", no_echo=True, min_length=24,
            description="Secret path segment for the SNS webhook. Generate with: openssl rand -hex 24",
        )
        admin_token = cdk.CfnParameter(
            self, "AdminToken", no_echo=True, default="",
            description="Optional. Enables Reset/Run simulation (X-Admin-Token header). Empty keeps them disabled.",
        )
        ses_from = cdk.CfnParameter(
            self, "SesFromAddress", description="A verified SES identity to send from",
        )
        alert_email = cdk.CfnParameter(self, "AlertEmail", description="Receives budget alerts")
        local_channels = cdk.CfnParameter(
            self, "LocalChannels", default="whatsapp",
            description="Channels that stay simulated. Set to 'none' once WhatsApp is live.",
        )
        wa_phone = cdk.CfnParameter(
            self, "WhatsAppPhoneNumberId", default="",
            description="phone-number-id-... from End User Messaging Social. Leave empty to simulate WhatsApp.",
        )

        # --- events: one topic for WhatsApp and SES notifications
        topic = sns.Topic(self, "Events", topic_name="renewflow-events")
        topic.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["sns:Publish"],
                resources=[topic.topic_arn],
                principals=[iam.ServicePrincipal("social-messaging.amazonaws.com")],
                conditions={"StringEquals": {"aws:SourceAccount": self.account}},
            )
        )
        config_set = ses.ConfigurationSet(self, "ConfigSet", configuration_set_name="renewflow")
        ses.CfnConfigurationSetEventDestination(
            self, "SesEvents",
            configuration_set_name=config_set.configuration_set_name,
            event_destination=ses.CfnConfigurationSetEventDestination.EventDestinationProperty(
                enabled=True,
                matching_event_types=["delivery", "bounce", "complaint", "reject", "click"],
                sns_destination=ses.CfnConfigurationSetEventDestination.SnsDestinationProperty(
                    topic_arn=topic.topic_arn
                ),
            ),
        )
        topic.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["sns:Publish"],
                resources=[topic.topic_arn],
                principals=[iam.ServicePrincipal("ses.amazonaws.com")],
                conditions={"StringEquals": {"aws:SourceAccount": self.account}},
            )
        )

        # --- network: a single public subnet, no NAT gateway (they cost ~$32/mo)
        vpc = ec2.Vpc(
            self, "Vpc", max_azs=1, nat_gateways=0,
            subnet_configuration=[ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC)],
        )
        sg = ec2.SecurityGroup(self, "Web", vpc=vpc, description="HTTP from CloudFront and the internet")
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "CloudFront origin fetches")

        role = iam.Role(self, "InstanceRole", assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"))
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"))
        role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Converse"],
            resources=["*"],
        ))
        role.add_to_policy(iam.PolicyStatement(actions=["ses:SendEmail", "sesv2:SendEmail"], resources=["*"]))
        role.add_to_policy(iam.PolicyStatement(actions=["social-messaging:SendWhatsAppMessage"], resources=["*"]))

        instance = ec2.Instance(
            self, "App", vpc=vpc, security_group=sg, role=role,
            instance_type=ec2.InstanceType("t4g.micro"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(cpu_type=ec2.AmazonLinuxCpuType.ARM_64),
            associate_public_ip_address=True,
            block_devices=[ec2.BlockDevice(device_name="/dev/xvda", volume=ec2.BlockDeviceVolume.ebs(8, encrypted=True))],
            require_imdsv2=True,
        )

        # --- HTTPS front door. CloudFront gives a free *.cloudfront.net certificate.
        cdn = cloudfront.Distribution(
            self, "Cdn",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.HttpOrigin(instance.instance_public_dns_name, protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY),
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
        )

        role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter/renewflow/base-url"],
        ))
        base_url = ssm.StringParameter(
            self, "BaseUrl", parameter_name="/renewflow/base-url", string_value=cdn.distribution_domain_name
        )
        base_url.node.add_dependency(cdn)
        instance.add_user_data(
            cdk.Fn.sub(
                USER_DATA,
                {
                    "Repo": repo.value_as_string,
                    "Region": self.region,
                    "LocalChannels": local_channels.value_as_string,
                    "SesFrom": ses_from.value_as_string,
                    "ConfigSet": config_set.configuration_set_name,
                    "WaPhone": wa_phone.value_as_string,
                    "Token": token.value_as_string,
                    "AdminToken": admin_token.value_as_string,
                    "Topic": topic.topic_arn,
                },
            )
        )

        subscription = sns.CfnSubscription(
            self, "Webhook", topic_arn=topic.topic_arn, protocol="https",
            endpoint=cdk.Fn.join("", ["https://", cdn.distribution_domain_name, "/webhooks/sns/", token.value_as_string]),
        )
        subscription.node.add_dependency(instance)

        # --- the CEO's cap: warn at 50%, 80% and 100% of $10
        budgets.CfnBudget(
            self, "Cap",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_type="COST", time_unit="MONTHLY", budget_name="renewflow-10-usd",
                budget_limit=budgets.CfnBudget.SpendProperty(amount=10, unit="USD"),
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="ACTUAL", comparison_operator="GREATER_THAN",
                        threshold=pct, threshold_type="PERCENTAGE",
                    ),
                    subscribers=[budgets.CfnBudget.SubscriberProperty(subscription_type="EMAIL", address=alert_email.value_as_string)],
                )
                for pct in (50, 80, 100)
            ],
        )

        cdk.CfnOutput(self, "DashboardUrl", value=f"https://{cdn.distribution_domain_name}")
        cdk.CfnOutput(self, "EventsTopicArn", value=topic.topic_arn, description="Pick this as the WhatsApp event destination")
        cdk.CfnOutput(self, "InstanceId", value=instance.instance_id, description="Connect with SSM Session Manager")
