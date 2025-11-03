#!/usr/bin/env python3
"""
CDK app entry point for Quip-S3 synchronization system
"""

import aws_cdk as cdk
from infrastructure.quip_sync_stack import QuipSyncStack


app = cdk.App()

# Get parameters from CDK context or environment
custom_name = app.node.try_get_context("customName")
quicksight_principal_id = app.node.try_get_context("quicksightPrincipalId")
quicksight_namespace = app.node.try_get_context("quicksightNamespace") or "default"
service_role_arn = app.node.try_get_context("serviceRoleArn")

# Validate that custom_name is provided
if not custom_name:
    raise ValueError(
        "customName context parameter is required.\n"
        "Use: cdk deploy --context customName=your-name\n"
        "Or use the deployment script: python deploy.py"
    )

# Create stack name in format QuipSyncStack-<custom-name>
stack_name = f"QuipSyncStack-{custom_name}"

# Validate stack name follows CloudFormation naming conventions
def validate_stack_name(name: str) -> str:
    """
    Validate CloudFormation stack name follows AWS naming conventions
    
    Args:
        name: The stack name to validate
        
    Returns:
        str: The validated stack name
        
    Raises:
        ValueError: If stack name doesn't meet CloudFormation requirements
    """
    import re
    
    # CloudFormation stack naming rules:
    # - 1-128 characters
    # - Letters, numbers, and hyphens only
    # - Must start with letter
    # - Cannot end with hyphen
    
    if not name:
        raise ValueError("Stack name cannot be empty")
    
    if len(name) < 1 or len(name) > 128:
        raise ValueError("Stack name must be between 1 and 128 characters long")
    
    # Check for valid characters (letters, numbers, hyphens only)
    if not re.match(r'^[a-zA-Z0-9-]+$', name):
        raise ValueError("Stack name can only contain letters, numbers, and hyphens")
    
    # Must start with letter (this will always pass since we use QuipSyncStack- prefix)
    if not re.match(r'^[a-zA-Z]', name):
        raise ValueError("Stack name must start with a letter")
    
    # Cannot end with hyphen
    if name.endswith('-'):
        raise ValueError("Stack name cannot end with a hyphen")
    
    return name

# Validate the generated stack name
stack_name = validate_stack_name(stack_name)

QuipSyncStack(
    app,
    stack_name,
    custom_name=custom_name,
    quicksight_principal_id=quicksight_principal_id,
    quicksight_namespace=quicksight_namespace,
    service_role_arn=service_role_arn,
    description=f"Quip-to-S3 document synchronization system ({custom_name})"
)

app.synth()