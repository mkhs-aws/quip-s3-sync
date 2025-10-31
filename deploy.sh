#!/bin/bash

# Quip-S3 Sync Deployment Script
# This script prompts for CDK parameters and secrets, then deploys the infrastructure
# and configures the secrets in AWS Secrets Manager.

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to prompt for input with validation
prompt_input() {
    local prompt="$1"
    local var_name="$2"
    local required="$3"
    local default="$4"
    local hide_input="$5"
    
    while true; do
        if [ "$hide_input" = "true" ]; then
            echo -n "$prompt"
            read -s input
            echo  # Add newline after hidden input
        else
            if [ -n "$default" ]; then
                read -p "$prompt [$default]: " input
                input=${input:-$default}
            else
                read -p "$prompt: " input
            fi
        fi
        
        if [ "$required" = "true" ] && [ -z "$input" ]; then
            print_error "This field is required. Please enter a value."
            continue
        fi
        
        eval "$var_name='$input'"
        break
    done
}

# Function to validate AWS CLI is configured
check_aws_cli() {
    print_info "Checking AWS CLI configuration..."
    
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS CLI is not configured or credentials are invalid."
        print_info "Please run 'aws configure' to set up your credentials."
        exit 1
    fi
    
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    AWS_REGION=$(aws configure get region 2>/dev/null || echo "")
    
    # Use us-east-1 as fallback if no region is configured
    if [ -z "$AWS_REGION" ]; then
        AWS_REGION="us-east-1"
    fi
    
    print_success "AWS CLI configured for account: $AWS_ACCOUNT_ID in region: $AWS_REGION"
}

# Function to validate CDK is installed
check_cdk() {
    print_info "Checking CDK installation..."
    
    if ! command -v cdk &> /dev/null; then
        print_error "AWS CDK is not installed. Please install it first:"
        print_info "npm install -g aws-cdk"
        exit 1
    fi
    
    CDK_VERSION=$(cdk --version)
    print_success "CDK installed: $CDK_VERSION"
}

# Function to bootstrap CDK if needed
bootstrap_cdk() {
    local region="$1"
    print_info "Checking if CDK bootstrap is required..."
    
    # Set region flag if provided
    REGION_FLAG=""
    if [ -n "$region" ]; then
        REGION_FLAG="--region $region"
    fi
    
    # Check if bootstrap stack exists
    if aws cloudformation describe-stacks --stack-name CDKToolkit $REGION_FLAG &> /dev/null; then
        print_success "CDK already bootstrapped"
    else
        print_warning "CDK bootstrap required"
        read -p "Do you want to bootstrap CDK now? (y/n): " bootstrap_choice
        
        if [ "$bootstrap_choice" = "y" ] || [ "$bootstrap_choice" = "Y" ]; then
            print_info "Bootstrapping CDK..."
            if [ -n "$region" ]; then
                AWS_DEFAULT_REGION="$region" cdk bootstrap
            else
                cdk bootstrap
            fi
            print_success "CDK bootstrap completed"
        else
            print_error "CDK bootstrap is required for deployment. Exiting."
            exit 1
        fi
    fi
}

# Function to collect CDK parameters
collect_cdk_parameters() {
    print_info "Collecting CDK deployment parameters..."
    echo
    
    print_info "AWS Configuration:"
    prompt_input "AWS Region for deployment" "AWS_DEPLOY_REGION" "false" "$AWS_REGION"
    
    echo
    print_info "QuickSight Configuration (required for bucket policy creation):"
    prompt_input "QuickSight Principal ID (e.g., user/d-xxx/S-1-5-21-xxx)" "QUICKSIGHT_PRINCIPAL_ID" "true"
    prompt_input "QuickSight Namespace" "QUICKSIGHT_NAMESPACE" "false" "default"
    prompt_input "QuickSight Service Role ARN (e.g., arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0)" "SERVICE_ROLE_ARN" "true"
    
    echo
    print_info "Stack Configuration:"
    prompt_input "Stack Name" "STACK_NAME" "false" "QuipSyncStack"
}

# Function to collect secrets
collect_secrets() {
    print_info "Collecting Secrets Manager configuration..."
    echo
    
    prompt_input "Quip Access Token (Bearer token)" "QUIP_ACCESS_TOKEN" "true"
    echo
    prompt_input "Quip Folder IDs (comma-separated)" "FOLDER_IDS" "true"
    
    prompt_input "Secret Name" "SECRET_NAME" "false" "quip-sync-credentials"
}

# Function to run CDK deployment
deploy_cdk() {
    print_info "Starting CDK deployment..."
    
    # Set AWS region environment variable if specified
    if [ -n "$AWS_DEPLOY_REGION" ]; then
        export AWS_DEFAULT_REGION="$AWS_DEPLOY_REGION"
    fi
    
    # Build CDK parameters
    CDK_PARAMS=""
    
    if [ -n "$QUICKSIGHT_PRINCIPAL_ID" ]; then
        CDK_PARAMS="$CDK_PARAMS --parameters quicksightPrincipalId=\"$QUICKSIGHT_PRINCIPAL_ID\""
    fi
    
    if [ -n "$QUICKSIGHT_NAMESPACE" ]; then
        CDK_PARAMS="$CDK_PARAMS --parameters quicksightNamespace=\"$QUICKSIGHT_NAMESPACE\""
    fi
    
    if [ -n "$SERVICE_ROLE_ARN" ]; then
        CDK_PARAMS="$CDK_PARAMS --parameters serviceRoleArn=\"$SERVICE_ROLE_ARN\""
    fi
    
    # Show what will be deployed
    print_info "Running CDK diff to show planned changes..."
    echo "Command: cdk diff $STACK_NAME $CDK_PARAMS"
    eval "cdk diff $STACK_NAME $CDK_PARAMS" || true
    
    echo
    read -p "Do you want to proceed with the deployment? (y/n): " deploy_choice
    
    if [ "$deploy_choice" != "y" ] && [ "$deploy_choice" != "Y" ]; then
        print_warning "Deployment cancelled by user."
        exit 0
    fi
    
    # Deploy the stack
    print_info "Deploying CDK stack..."
    eval "cdk deploy $STACK_NAME $CDK_PARAMS --require-approval never"
    
    print_success "CDK deployment completed successfully!"
}

# Function to update secrets
update_secrets() {
    print_info "Updating AWS Secrets Manager..."
    
    # Create the secret JSON
    SECRET_JSON=$(cat <<EOF
{
    "quip_access_token": "$QUIP_ACCESS_TOKEN",
    "folder_ids": "$FOLDER_IDS"
}
EOF
)
    
    # Set region flag if specified
    REGION_FLAG=""
    if [ -n "$AWS_DEPLOY_REGION" ]; then
        REGION_FLAG="--region $AWS_DEPLOY_REGION"
    fi
    
    # Check if secret exists
    if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" $REGION_FLAG &> /dev/null; then
        print_info "Secret '$SECRET_NAME' exists. Updating..."
        aws secretsmanager update-secret \
            --secret-id "$SECRET_NAME" \
            --secret-string "$SECRET_JSON" \
            $REGION_FLAG
        print_success "Secret updated successfully!"
    else
        print_info "Secret '$SECRET_NAME' does not exist. Creating..."
        aws secretsmanager create-secret \
            --name "$SECRET_NAME" \
            --description "Quip access token and folder IDs for sync system" \
            --secret-string "$SECRET_JSON" \
            $REGION_FLAG
        print_success "Secret created successfully!"
    fi
}

# Function to verify deployment
verify_deployment() {
    print_info "Verifying deployment..."
    
    # Check if stack exists
    if aws cloudformation describe-stacks --stack-name "$STACK_NAME" &> /dev/null; then
        print_success "CloudFormation stack '$STACK_NAME' is active"
        
        # Get stack outputs
        BUCKET_NAME=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" --output text 2>/dev/null || echo "")
        LAMBDA_FUNCTION=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='LambdaFunction'].OutputValue" --output text 2>/dev/null || echo "")
        
        if [ -n "$BUCKET_NAME" ]; then
            print_success "S3 Bucket: $BUCKET_NAME"
        fi
        
        if [ -n "$LAMBDA_FUNCTION" ]; then
            print_success "Lambda Function: $LAMBDA_FUNCTION"
        fi
        
        # Check if bucket policy exists (if QuickSight parameters were provided)
        if [ -n "$SERVICE_ROLE_ARN" ]; then
            BUCKET_NAME_ACTUAL="$AWS_ACCOUNT_ID-quip-sync"
            REGION_FLAG=""
            if [ -n "$AWS_DEPLOY_REGION" ]; then
                REGION_FLAG="--region $AWS_DEPLOY_REGION"
            fi
            if aws s3api get-bucket-policy --bucket "$BUCKET_NAME_ACTUAL" $REGION_FLAG &> /dev/null; then
                print_success "S3 bucket policy applied successfully"
            else
                print_warning "S3 bucket policy not found (this may be expected if parameters were not provided)"
            fi
        fi
    else
        print_error "CloudFormation stack '$STACK_NAME' not found"
        return 1
    fi
    
    # Check secret
    REGION_FLAG=""
    if [ -n "$AWS_DEPLOY_REGION" ]; then
        REGION_FLAG="--region $AWS_DEPLOY_REGION"
    fi
    if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" $REGION_FLAG &> /dev/null; then
        print_success "Secret '$SECRET_NAME' is configured"
    else
        print_error "Secret '$SECRET_NAME' not found"
        return 1
    fi
}

# Function to test the deployment
test_deployment() {
    print_info "Testing Lambda function..."
    
    LAMBDA_FUNCTION_NAME="quip-sync-function"
    
    # Test invoke the Lambda function
    print_info "Invoking Lambda function for test..."
    
    REGION_FLAG=""
    if [ -n "$AWS_DEPLOY_REGION" ]; then
        REGION_FLAG="--region $AWS_DEPLOY_REGION"
    fi
    
    INVOKE_RESULT=$(aws lambda invoke \
        --function-name "$LAMBDA_FUNCTION_NAME" \
        --payload '{}' \
        --cli-binary-format raw-in-base64-out \
        $REGION_FLAG \
        response.json 2>&1)
    
    if [ $? -eq 0 ]; then
        print_success "Lambda function invoked successfully"
        
        # Show response
        if [ -f "response.json" ]; then
            print_info "Lambda response:"
            cat response.json | jq . 2>/dev/null || cat response.json
            rm -f response.json
        fi
    else
        print_warning "Lambda function test failed (this may be expected if Quip credentials are not valid yet)"
        print_info "Error: $INVOKE_RESULT"
    fi
}

# Main deployment flow
main() {
    echo "=============================================="
    echo "    Quip-S3 Sync Deployment Script"
    echo "=============================================="
    echo
    
    # Pre-flight checks
    check_aws_cli
    check_cdk
    bootstrap_cdk "$AWS_REGION"
    
    echo
    print_info "Starting interactive deployment configuration..."
    echo
    
    # Collect parameters
    collect_cdk_parameters
    collect_secrets
    
    # Confirmation
    echo
    print_info "Deployment Summary:"
    echo "  Stack Name: $STACK_NAME"
    echo "  AWS Account: $AWS_ACCOUNT_ID"
    echo "  AWS Region: $AWS_DEPLOY_REGION"
    echo "  Secret Name: $SECRET_NAME"
    
    echo "  QuickSight Principal: $QUICKSIGHT_PRINCIPAL_ID"
    echo "  QuickSight Namespace: $QUICKSIGHT_NAMESPACE"
    echo "  Service Role ARN: $SERVICE_ROLE_ARN"
    print_info "Bucket policy will be created for QuickSight access"
    
    echo
    read -p "Do you want to proceed with this configuration? (y/n): " final_confirm
    
    if [ "$final_confirm" != "y" ] && [ "$final_confirm" != "Y" ]; then
        print_warning "Deployment cancelled by user."
        exit 0
    fi
    
    # Execute deployment
    echo
    deploy_cdk
    update_secrets
    verify_deployment
    
    echo
    print_success "Deployment completed successfully!"
    
    # Optional testing
    echo
    read -p "Do you want to test the Lambda function? (y/n): " test_choice
    if [ "$test_choice" = "y" ] || [ "$test_choice" = "Y" ]; then
        test_deployment
    fi
    
    echo
    print_success "All done! Your Quip-S3 sync system is ready."
    print_info "The system will run automatically based on the EventBridge schedule."
    print_info "Check CloudWatch logs for execution details."
}

# Run main function
main "$@"