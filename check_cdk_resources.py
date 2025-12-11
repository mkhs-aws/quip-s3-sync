#!/usr/bin/env python3
"""
CDK Bootstrap Resource Checker

This script checks for existing CDK bootstrap resources that might be preventing
a fresh CDK bootstrap from deploying. It looks for orphaned or partially deleted
resources from previous bootstrap attempts.
"""

import boto3
import json
from botocore.exceptions import ClientError


def get_account_id():
    """Get the current AWS account ID"""
    sts = boto3.client('sts')
    return sts.get_caller_identity()['Account']


def get_region():
    """Get the current AWS region"""
    session = boto3.session.Session()
    return session.region_name or 'us-east-1'


def check_s3_buckets(account_id, region):
    """Check for CDK staging buckets"""
    print("\n📦 Checking S3 Buckets...")
    s3 = boto3.client('s3')
    
    # CDK bootstrap bucket naming patterns
    patterns = [
        f"cdk-hnb659fds-assets-{account_id}-{region}",
        f"cdktoolkit-stagingbucket-",
        f"cdk-{account_id}-assets-{region}",
    ]
    
    found_buckets = []
    
    try:
        response = s3.list_buckets()
        for bucket in response['Buckets']:
            bucket_name = bucket['Name']
            for pattern in patterns:
                if pattern in bucket_name or bucket_name.startswith(pattern):
                    found_buckets.append(bucket_name)
                    print(f"  ⚠️  Found CDK bucket: {bucket_name}")
                    
                    # Check if bucket is empty
                    try:
                        objects = s3.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
                        if objects.get('KeyCount', 0) > 0:
                            print(f"      └── Bucket contains objects")
                        else:
                            print(f"      └── Bucket is empty")
                    except ClientError as e:
                        print(f"      └── Cannot access bucket: {e}")
                    break
    except ClientError as e:
        print(f"  ❌ Error listing buckets: {e}")
    
    if not found_buckets:
        print("  ✅ No CDK S3 buckets found")
    
    return found_buckets


def check_ecr_repositories(account_id, region):
    """Check for CDK ECR repositories"""
    print("\n🐳 Checking ECR Repositories...")
    ecr = boto3.client('ecr')
    
    patterns = [
        f"cdk-hnb659fds-container-assets-{account_id}-{region}",
        "cdk-",
        "cdktoolkit",
    ]
    
    found_repos = []
    
    try:
        paginator = ecr.get_paginator('describe_repositories')
        for page in paginator.paginate():
            for repo in page['repositories']:
                repo_name = repo['repositoryName']
                for pattern in patterns:
                    if pattern in repo_name.lower():
                        found_repos.append(repo_name)
                        print(f"  ⚠️  Found CDK ECR repo: {repo_name}")
                        print(f"      └── URI: {repo['repositoryUri']}")
                        break
    except ClientError as e:
        print(f"  ❌ Error listing ECR repos: {e}")
    
    if not found_repos:
        print("  ✅ No CDK ECR repositories found")
    
    return found_repos


def check_iam_roles():
    """Check for CDK IAM roles"""
    print("\n👤 Checking IAM Roles...")
    iam = boto3.client('iam')
    
    cdk_role_patterns = [
        "cdk-hnb659fds-",
        "cdk-",
        "CDKToolkit",
        "CloudFormationExecutionRole",
        "DeploymentActionRole",
        "FilePublishingRole",
        "ImagePublishingRole",
        "LookupRole",
    ]
    
    found_roles = []
    
    try:
        paginator = iam.get_paginator('list_roles')
        for page in paginator.paginate():
            for role in page['Roles']:
                role_name = role['RoleName']
                for pattern in cdk_role_patterns:
                    if pattern.lower() in role_name.lower():
                        found_roles.append(role_name)
                        print(f"  ⚠️  Found CDK role: {role_name}")
                        print(f"      └── ARN: {role['Arn']}")
                        break
    except ClientError as e:
        print(f"  ❌ Error listing IAM roles: {e}")
    
    if not found_roles:
        print("  ✅ No CDK IAM roles found")
    
    return found_roles


def check_ssm_parameters(region):
    """Check for CDK SSM parameters"""
    print("\n📝 Checking SSM Parameters...")
    ssm = boto3.client('ssm')
    
    cdk_param_patterns = [
        "/cdk-bootstrap/",
        "/cdk/",
    ]
    
    found_params = []
    
    try:
        paginator = ssm.get_paginator('describe_parameters')
        for page in paginator.paginate():
            for param in page['Parameters']:
                param_name = param['Name']
                for pattern in cdk_param_patterns:
                    if pattern in param_name:
                        found_params.append(param_name)
                        print(f"  ⚠️  Found CDK parameter: {param_name}")
                        
                        # Get the value
                        try:
                            value_response = ssm.get_parameter(Name=param_name)
                            print(f"      └── Value: {value_response['Parameter']['Value']}")
                        except ClientError:
                            pass
                        break
    except ClientError as e:
        print(f"  ❌ Error listing SSM parameters: {e}")
    
    if not found_params:
        print("  ✅ No CDK SSM parameters found")
    
    return found_params


def check_cloudformation_stacks():
    """Check for CDK-related CloudFormation stacks"""
    print("\n📚 Checking CloudFormation Stacks...")
    cfn = boto3.client('cloudformation')
    
    cdk_stack_patterns = [
        "CDKToolkit",
        "cdk-",
    ]
    
    found_stacks = []
    
    try:
        # Check all stack statuses including deleted
        paginator = cfn.get_paginator('list_stacks')
        for page in paginator.paginate(StackStatusFilter=[
            'CREATE_IN_PROGRESS', 'CREATE_FAILED', 'CREATE_COMPLETE',
            'ROLLBACK_IN_PROGRESS', 'ROLLBACK_FAILED', 'ROLLBACK_COMPLETE',
            'DELETE_IN_PROGRESS', 'DELETE_FAILED',
            'UPDATE_IN_PROGRESS', 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS',
            'UPDATE_COMPLETE', 'UPDATE_FAILED', 'UPDATE_ROLLBACK_IN_PROGRESS',
            'UPDATE_ROLLBACK_FAILED', 'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
            'UPDATE_ROLLBACK_COMPLETE', 'REVIEW_IN_PROGRESS',
            'IMPORT_IN_PROGRESS', 'IMPORT_COMPLETE', 'IMPORT_ROLLBACK_IN_PROGRESS',
            'IMPORT_ROLLBACK_FAILED', 'IMPORT_ROLLBACK_COMPLETE'
        ]):
            for stack in page['StackSummaries']:
                stack_name = stack['StackName']
                for pattern in cdk_stack_patterns:
                    if pattern.lower() in stack_name.lower():
                        found_stacks.append({
                            'name': stack_name,
                            'status': stack['StackStatus']
                        })
                        status_emoji = "🔴" if "FAILED" in stack['StackStatus'] else "🟡" if "IN_PROGRESS" in stack['StackStatus'] else "🟢"
                        print(f"  {status_emoji} Found CDK stack: {stack_name}")
                        print(f"      └── Status: {stack['StackStatus']}")
                        break
    except ClientError as e:
        print(f"  ❌ Error listing stacks: {e}")
    
    if not found_stacks:
        print("  ✅ No CDK CloudFormation stacks found")
    
    return found_stacks


def check_kms_keys(account_id, region):
    """Check for CDK KMS keys"""
    print("\n🔐 Checking KMS Keys...")
    kms = boto3.client('kms')
    
    found_keys = []
    
    try:
        paginator = kms.get_paginator('list_aliases')
        for page in paginator.paginate():
            for alias in page['Aliases']:
                alias_name = alias['AliasName']
                if 'cdk' in alias_name.lower() or 'cdktoolkit' in alias_name.lower():
                    found_keys.append(alias_name)
                    print(f"  ⚠️  Found CDK KMS alias: {alias_name}")
                    if 'TargetKeyId' in alias:
                        print(f"      └── Key ID: {alias['TargetKeyId']}")
    except ClientError as e:
        print(f"  ❌ Error listing KMS keys: {e}")
    
    if not found_keys:
        print("  ✅ No CDK KMS keys found")
    
    return found_keys


def check_cloudformation_hooks():
    """Check for CloudFormation hooks that might block deployment"""
    print("\n🪝 Checking CloudFormation Hooks...")
    cfn = boto3.client('cloudformation')
    
    found_hooks = []
    
    try:
        # List type configurations for hooks
        response = cfn.list_types(
            Visibility='PRIVATE',
            Type='HOOK'
        )
        
        for type_summary in response.get('TypeSummaries', []):
            found_hooks.append(type_summary)
            print(f"  ⚠️  Found Hook: {type_summary['TypeName']}")
            print(f"      └── ARN: {type_summary.get('TypeArn', 'N/A')}")
        
        # Also check public hooks
        response = cfn.list_types(
            Visibility='PUBLIC',
            Type='HOOK'
        )
        
        for type_summary in response.get('TypeSummaries', []):
            if 'EarlyValidation' in type_summary.get('TypeName', ''):
                found_hooks.append(type_summary)
                print(f"  ⚠️  Found Hook: {type_summary['TypeName']}")
                
    except ClientError as e:
        print(f"  ❌ Error listing hooks: {e}")
    
    if not found_hooks:
        print("  ✅ No CloudFormation hooks found (or no permission to list)")
    
    return found_hooks


def generate_cleanup_commands(buckets, repos, roles, params, stacks, keys):
    """Generate cleanup commands for found resources"""
    print("\n" + "=" * 60)
    print("🧹 CLEANUP COMMANDS")
    print("=" * 60)
    print("\n⚠️  WARNING: Review these commands carefully before running!")
    print("    Some resources may be in use by other stacks.\n")
    
    if stacks:
        print("# Delete CloudFormation stacks first:")
        for stack in stacks:
            if stack['status'] != 'DELETE_COMPLETE':
                print(f"aws cloudformation delete-stack --stack-name {stack['name']}")
        print()
    
    if params:
        print("# Delete SSM parameters:")
        for param in params:
            print(f"aws ssm delete-parameter --name '{param}'")
        print()
    
    if roles:
        print("# Delete IAM roles (may need to detach policies first):")
        for role in roles:
            print(f"# aws iam delete-role --role-name {role}")
        print()
    
    if buckets:
        print("# Empty and delete S3 buckets:")
        for bucket in buckets:
            print(f"aws s3 rm s3://{bucket} --recursive")
            print(f"aws s3 rb s3://{bucket}")
        print()
    
    if repos:
        print("# Delete ECR repositories:")
        for repo in repos:
            print(f"aws ecr delete-repository --repository-name {repo} --force")
        print()
    
    if keys:
        print("# Delete KMS key aliases (keys will be scheduled for deletion):")
        for key in keys:
            print(f"aws kms delete-alias --alias-name {key}")
        print()


def main():
    print("=" * 60)
    print("🔍 CDK Bootstrap Resource Checker")
    print("=" * 60)
    
    try:
        account_id = get_account_id()
        region = get_region()
        
        print(f"\n📋 Account: {account_id}")
        print(f"📍 Region:  {region}")
        
        # Run all checks
        buckets = check_s3_buckets(account_id, region)
        repos = check_ecr_repositories(account_id, region)
        roles = check_iam_roles()
        params = check_ssm_parameters(region)
        stacks = check_cloudformation_stacks()
        keys = check_kms_keys(account_id, region)
        hooks = check_cloudformation_hooks()
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        
        total_issues = len(buckets) + len(repos) + len(roles) + len(params) + len(stacks) + len(keys)
        
        if total_issues == 0:
            print("\n✅ No orphaned CDK resources found!")
            print("   The bootstrap failure is likely due to CloudFormation hooks")
            print("   or permission issues, not orphaned resources.")
        else:
            print(f"\n⚠️  Found {total_issues} potential CDK resources:")
            print(f"   - S3 Buckets: {len(buckets)}")
            print(f"   - ECR Repos:  {len(repos)}")
            print(f"   - IAM Roles:  {len(roles)}")
            print(f"   - SSM Params: {len(params)}")
            print(f"   - CF Stacks:  {len(stacks)}")
            print(f"   - KMS Keys:   {len(keys)}")
            
            generate_cleanup_commands(buckets, repos, roles, params, stacks, keys)
        
        if hooks:
            print("\n🪝 CloudFormation Hooks detected!")
            print("   These hooks may be blocking CDK bootstrap.")
            print("   Contact your AWS administrator to review hook configurations.")
        
    except ClientError as e:
        print(f"\n❌ AWS Error: {e}")
        print("   Make sure your AWS credentials are configured correctly.")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()
