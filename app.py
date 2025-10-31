#!/usr/bin/env python3
"""
CDK app entry point for Quip-S3 synchronization system
"""

import aws_cdk as cdk
from infrastructure.quip_sync_stack import QuipSyncStack


app = cdk.App()

# Get parameters from CDK context or environment
quicksight_principal_id = app.node.try_get_context("quicksightPrincipalId")
quicksight_namespace = app.node.try_get_context("quicksightNamespace") or "default"
service_role_arn = app.node.try_get_context("serviceRoleArn")

QuipSyncStack(
    app,
    "QuipSyncStack",
    quicksight_principal_id=quicksight_principal_id,
    quicksight_namespace=quicksight_namespace,
    service_role_arn=service_role_arn,
    description="Quip-to-S3 document synchronization system"
)

app.synth()