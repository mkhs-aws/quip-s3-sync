#!/usr/bin/env python3
"""
Quip-S3 Sync Deployment Script

This script prompts for CDK parameters and secrets, then deploys the infrastructure
and configures the secrets in AWS Secrets Manager.
"""

import json
import subprocess
import sys
import getpass
from typing import Optional, Dict, Any


class Colors:
    """ANSI color codes for terminal output"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


def print_info(message: str) -> None:
    """Print info message in blue"""
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {message}")


def print_success(message: str) -> None:
    """Print success message in green"""
    print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {message}")


def print_warning(message: str) -> None:
    """Print warning message in yellow"""
    print(f"{Colors.YELLOW}[WARNING]{Colors.NC} {message}")


def print_error(message: str) -> None:
    """Print error message in red"""
    print(f"{Colors.RED}[ERROR]{Colors.NC} {message}")


def run_command(command: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=check
        )
        return result
    except subprocess.CalledProcessError as e:
        if check:
            print_error(f"Command failed: {command}")
            print_error(f"Error: {e.stderr}")
            raise
        return e


def prompt_input(prompt: str, required: bool = False, default: str = "", hide_input: bool = False) -> str:
    """Prompt user for input with validation"""
    while True:
        if hide_input:
            if default:
                value = getpass.getpass(f"{prompt} [hidden, press Enter for default]: ")
                if not value:
                    value = default
            else:
                value = getpass.getpass(f"{prompt}: ")
        else:
            if default:
                value = input(f"{prompt} [{default}]: ").strip()
                if not value:
                    value = default
            else:
                value = input(f"{prompt}: ").strip()
        
        if required and not value:
            print_error("This field is required. Please enter a value.")
            continue
        
        return value


def check_aws_cli() -> Dict[str, str]:
    """Check if AWS CLI is configured and return account info"""
    print_info("Checking AWS CLI configuration...")
    
    # Check if AWS CLI is installed
    try:
        run_command("aws --version")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error("AWS CLI is not installed. Please install it first.")
        sys.exit(1)
    
    # Check if AWS CLI is configured
    try:
        result = run_command("aws sts get-caller-identity")
        identity = json.loads(result.stdout)
        
        account_id = identity['Account']
        
        # Get region - use us-east-1 as fallback if not configured
        try:
            region_result = run_command("aws configure get region", check=False)
            region = region_result.stdout.strip() if region_result.returncode == 0 else ""
            if not region:
                region = "us-east-1"
        except subprocess.CalledProcessError:
            region = "us-east-1"
        
        print_success(f"AWS CLI configured for account: {account_id} in region: {region}")
        
        return {
            'account_id': account_id,
            'region': region
        }
        
    except subprocess.CalledProcessError:
        print_error("AWS CLI is not configured or credentials are invalid.")
        print_info("Please run 'aws configure' to set up your credentials.")
        sys.exit(1)


def check_cdk() -> None:
    """Check if CDK is installed"""
    print_info("Checking CDK installation...")
    
    try:
        result = run_command("cdk --version")
        print_success(f"CDK installed: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error("AWS CDK is not installed. Please install it first:")
        print_info("npm install -g aws-cdk")
        sys.exit(1)


def bootstrap_cdk(region: str) -> None:
    """Bootstrap CDK if needed"""
    print_info("Checking if CDK bootstrap is required...")
    
    region_flag = f"--region {region}" if region else ""
    
    # Check if bootstrap stack exists
    try:
        run_command(f"aws cloudformation describe-stacks --stack-name CDKToolkit {region_flag}")
        print_success("CDK already bootstrapped")
    except subprocess.CalledProcessError:
        print_warning("CDK bootstrap required")
        choice = prompt_input("Do you want to bootstrap CDK now? (y/n)", default="y")
        
        if choice.lower() in ['y', 'yes']:
            print_info("Bootstrapping CDK...")
            bootstrap_cmd = f"cdk bootstrap"
            if region:
                bootstrap_cmd = f"AWS_DEFAULT_REGION={region} {bootstrap_cmd}"
            run_command(bootstrap_cmd)
            print_success("CDK bootstrap completed")
        else:
            print_error("CDK bootstrap is required for deployment. Exiting.")
            sys.exit(1)


def collect_cdk_parameters(current_region: str) -> Dict[str, str]:
    """Collect CDK deployment parameters from user"""
    print_info("Collecting CDK deployment parameters...")
    print()
    
    print_info("AWS Configuration:")
    params = {}
    params['aws_region'] = prompt_input(
        "AWS Region for deployment", 
        default=current_region
    )
    
    print()
    print_info("QuickSight Configuration (required for bucket policy creation):")
    
    params['quicksight_principal_id'] = prompt_input(
        "QuickSight Principal ID (e.g., user/d-xxx/S-1-5-21-xxx)",
        required=True
    )
    params['quicksight_namespace'] = prompt_input(
        "QuickSight Namespace", 
        default="default"
    )
    params['service_role_arn'] = prompt_input(
        "QuickSight Service Role ARN (e.g., arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0)",
        required=True
    )
    
    print()
    print_info("Stack Configuration:")
    params['stack_name'] = prompt_input("Stack Name", default="QuipSyncStack")
    
    return params


def collect_secrets() -> Dict[str, str]:
    """Collect secrets configuration from user"""
    print_info("Collecting Secrets Manager configuration...")
    print()
    
    secrets = {}
    secrets['quip_access_token'] = prompt_input(
        "Quip Access Token (Bearer token)", 
        required=True
    )
    secrets['folder_ids'] = prompt_input(
        "Quip Folder IDs (comma-separated)", 
        required=True
    )
    secrets['secret_name'] = prompt_input(
        "Secret Name", 
        default="quip-sync-credentials"
    )
    
    return secrets


def deploy_cdk(params: Dict[str, str]) -> None:
    """Deploy the CDK stack"""
    print_info("Starting CDK deployment...")
    
    # Set AWS region if different from current
    region_env = ""
    if params['aws_region']:
        region_env = f"AWS_DEFAULT_REGION={params['aws_region']} "
    
    # Build CDK parameters
    cdk_params = []
    
    if params['quicksight_principal_id']:
        cdk_params.append(f'--parameters quicksightPrincipalId="{params["quicksight_principal_id"]}"')
    
    if params['quicksight_namespace']:
        cdk_params.append(f'--parameters quicksightNamespace="{params["quicksight_namespace"]}"')
    
    if params['service_role_arn']:
        cdk_params.append(f'--parameters serviceRoleArn="{params["service_role_arn"]}"')
    
    cdk_params_str = ' '.join(cdk_params)
    
    # Show what will be deployed
    print_info("Running CDK diff to show planned changes...")
    diff_command = f"{region_env}cdk diff {params['stack_name']} {cdk_params_str}"
    print(f"Command: {diff_command}")
    
    try:
        run_command(diff_command, check=False)
    except Exception:
        pass  # CDK diff might fail, but that's okay
    
    print()
    choice = prompt_input("Do you want to proceed with the deployment? (y/n)", default="y")
    
    if choice.lower() not in ['y', 'yes']:
        print_warning("Deployment cancelled by user.")
        sys.exit(0)
    
    # Deploy the stack
    print_info("Deploying CDK stack...")
    deploy_command = f"{region_env}cdk deploy {params['stack_name']} {cdk_params_str} --require-approval never"
    run_command(deploy_command)
    
    print_success("CDK deployment completed successfully!")


def update_secrets(secrets: Dict[str, str], region: str) -> None:
    """Update AWS Secrets Manager"""
    print_info("Updating AWS Secrets Manager...")
    
    # Create the secret JSON
    secret_json = {
        "quip_access_token": secrets['quip_access_token'],
        "folder_ids": secrets['folder_ids']
    }
    
    secret_string = json.dumps(secret_json)
    region_flag = f"--region {region}" if region else ""
    
    # Check if secret exists
    try:
        run_command(f'aws secretsmanager describe-secret --secret-id "{secrets["secret_name"]}" {region_flag}')
        print_info(f"Secret '{secrets['secret_name']}' exists. Updating...")
        
        run_command(f'''aws secretsmanager update-secret \
            --secret-id "{secrets['secret_name']}" \
            --secret-string '{secret_string}' {region_flag}''')
        
        print_success("Secret updated successfully!")
        
    except subprocess.CalledProcessError:
        print_info(f"Secret '{secrets['secret_name']}' does not exist. Creating...")
        
        run_command(f'''aws secretsmanager create-secret \
            --name "{secrets['secret_name']}" \
            --description "Quip access token and folder IDs for sync system" \
            --secret-string '{secret_string}' {region_flag}''')
        
        print_success("Secret created successfully!")


def verify_deployment(stack_name: str, secret_name: str, aws_info: Dict[str, str], region: str, service_role_arn: str = "") -> None:
    """Verify the deployment"""
    print_info("Verifying deployment...")
    
    region_flag = f"--region {region}" if region else ""
    
    # Check if stack exists
    try:
        run_command(f'aws cloudformation describe-stacks --stack-name "{stack_name}" {region_flag}')
        print_success(f"CloudFormation stack '{stack_name}' is active")
        
        # Check if bucket policy exists (if QuickSight parameters were provided)
        if service_role_arn:
            bucket_name = f"{aws_info['account_id']}-quip-sync"
            try:
                run_command(f'aws s3api get-bucket-policy --bucket "{bucket_name}" {region_flag}')
                print_success("S3 bucket policy applied successfully")
            except subprocess.CalledProcessError:
                print_warning("S3 bucket policy not found (this may be expected if parameters were not provided)")
        
    except subprocess.CalledProcessError:
        print_error(f"CloudFormation stack '{stack_name}' not found")
        return
    
    # Check secret
    try:
        run_command(f'aws secretsmanager describe-secret --secret-id "{secret_name}" {region_flag}')
        print_success(f"Secret '{secret_name}' is configured")
    except subprocess.CalledProcessError:
        print_error(f"Secret '{secret_name}' not found")


def test_deployment(region: str) -> None:
    """Test the Lambda function"""
    print_info("Testing Lambda function...")
    
    lambda_function_name = "quip-sync-function"
    region_flag = f"--region {region}" if region else ""
    
    try:
        print_info("Invoking Lambda function for test...")
        
        result = run_command(f'''aws lambda invoke \
            --function-name "{lambda_function_name}" \
            --payload '{{}}' \
            --cli-binary-format raw-in-base64-out \
            {region_flag} \
            response.json''')
        
        print_success("Lambda function invoked successfully")
        
        # Show response
        try:
            with open('response.json', 'r') as f:
                response = json.load(f)
                print_info("Lambda response:")
                print(json.dumps(response, indent=2))
        except (FileNotFoundError, json.JSONDecodeError):
            print_warning("Could not read Lambda response")
        finally:
            # Clean up response file
            try:
                import os
                os.remove('response.json')
            except FileNotFoundError:
                pass
                
    except subprocess.CalledProcessError:
        print_warning("Lambda function test failed (this may be expected if Quip credentials are not valid yet)")


def main() -> None:
    """Main deployment flow"""
    print("=" * 50)
    print("    Quip-S3 Sync Deployment Script")
    print("=" * 50)
    print()
    
    # Pre-flight checks
    aws_info = check_aws_cli()
    check_cdk()
    bootstrap_cdk(aws_info['region'])
    
    print()
    print_info("Starting interactive deployment configuration...")
    print()
    
    # Collect parameters
    cdk_params = collect_cdk_parameters(aws_info['region'])
    secrets = collect_secrets()
    
    # Confirmation
    print()
    print_info("Deployment Summary:")
    print(f"  Stack Name: {cdk_params['stack_name']}")
    print(f"  AWS Account: {aws_info['account_id']}")
    print(f"  AWS Region: {cdk_params['aws_region']}")
    print(f"  Secret Name: {secrets['secret_name']}")
    
    print(f"  QuickSight Principal: {cdk_params['quicksight_principal_id']}")
    print(f"  QuickSight Namespace: {cdk_params['quicksight_namespace']}")
    print(f"  Service Role ARN: {cdk_params['service_role_arn']}")
    print_info("Bucket policy will be created for QuickSight access")
    
    print()
    final_confirm = prompt_input("Do you want to proceed with this configuration? (y/n)", default="y")
    
    if final_confirm.lower() not in ['y', 'yes']:
        print_warning("Deployment cancelled by user.")
        sys.exit(0)
    
    # Execute deployment
    print()
    try:
        deploy_cdk(cdk_params)
        update_secrets(secrets, cdk_params['aws_region'])
        verify_deployment(
            cdk_params['stack_name'], 
            secrets['secret_name'], 
            aws_info,
            cdk_params['aws_region'], 
            cdk_params['service_role_arn']
        )
        
        print()
        print_success("Deployment completed successfully!")
        
        # Optional testing
        print()
        test_choice = prompt_input("Do you want to test the Lambda function? (y/n)", default="n")
        if test_choice.lower() in ['y', 'yes']:
            test_deployment(cdk_params['aws_region'])
        
        print()
        print_success("All done! Your Quip-S3 sync system is ready.")
        print_info("The system will run automatically based on the EventBridge schedule.")
        print_info("Check CloudWatch logs for execution details.")
        
    except Exception as e:
        print_error(f"Deployment failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()