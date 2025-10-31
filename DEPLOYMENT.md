# Deployment Guide

This document provides detailed deployment instructions and configuration examples for the Quip-to-S3 synchronization system.

## Quick Start

### Automated Deployment (Recommended)

Use the interactive deployment scripts for the easiest setup:

```bash
# Option 1: Bash script (Linux/macOS)
./deploy.sh

# Option 2: Python script (cross-platform)
python deploy.py
```

**Features of the deployment scripts:**
- Interactive prompts for all configuration parameters
- Automatic prerequisite checking (AWS CLI, CDK)
- CDK bootstrap handling
- Integrated secrets management
- Deployment verification
- Optional Lambda function testing
- Colored output for better readability

**What the scripts do:**
1. Verify AWS CLI and CDK are installed and configured
2. Bootstrap CDK if needed
3. Collect QuickSight parameters (optional for bucket policy)
4. Collect Quip credentials securely
5. Deploy CDK stack with parameters
6. Create/update AWS Secrets Manager secret
7. Verify deployment success
8. Optionally test the Lambda function

**Example deployment session:**
```bash
$ ./deploy.py

==================================================
    Quip-S3 Sync Deployment Script
==================================================

[INFO] Checking AWS CLI configuration...
[SUCCESS] AWS CLI configured for account: 123456789012 in region: us-east-1
[INFO] Checking CDK installation...
[SUCCESS] CDK installed: 2.100.0
[INFO] CDK already bootstrapped

[INFO] Collecting CDK deployment parameters...

[INFO] QuickSight Configuration (optional - leave empty to skip bucket policy creation):
QuickSight Principal ID (e.g., user/d-xxx/S-1-5-21-xxx): user/d-12345abcde/S-1-2-34-1234567890-1234567890-1234567890-1234567890
QuickSight Namespace [default]: 
QuickSight Service Role ARN: arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0

[INFO] Stack Configuration:
Stack Name [QuipSyncStack]: 

[INFO] Collecting Secrets Manager configuration...

Quip Access Token (token): [hidden input]
Quip Folder IDs (comma-separated): ABC123DEF456,GHI789JKL012
Secret Name [quip-sync-credentials]: 

[INFO] Deployment Summary:
  Stack Name: QuipSyncStack
  AWS Account: 123456789012
  AWS Region: us-east-1
  Secret Name: quip-sync-credentials
  QuickSight Principal: user/d-12345abcde/S-1-2-34-1234567890-1234567890-1234567890-1234567890
  QuickSight Namespace: default
  Service Role ARN: arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0
[INFO] Bucket policy will be created for QuickSight access

Do you want to proceed with this configuration? (y/n) [y]: y

[INFO] Starting CDK deployment...
[SUCCESS] CDK deployment completed successfully!
[SUCCESS] Secret created successfully!
[SUCCESS] CloudFormation stack 'QuipSyncStack' is active
[SUCCESS] S3 bucket policy applied successfully
[SUCCESS] Secret 'quip-sync-credentials' is configured
[SUCCESS] Deployment completed successfully!

Do you want to test the Lambda function? (y/n) [n]: y
[SUCCESS] Lambda function invoked successfully
[SUCCESS] All done! Your Quip-S3 sync system is ready.
```

### Manual Deployment

For immediate deployment with default settings:

```bash
# 1. Install dependencies
pip install -r requirements.txt
npm install -g aws-cdk

# 2. Bootstrap CDK (first time only)
cdk bootstrap

# 3. Deploy with your Quick Suite parameters
cdk deploy \
  --parameters quicksightPrincipalId="YOUR_PRINCIPAL_ID" \
  --parameters quicksightNamespace="default" \
  --parameters serviceRoleArn="YOUR_SERVICE_ROLE_ARN"

# 4. Configure Secrets Manager
aws secretsmanager create-secret \
  --name "quip-sync-credentials" \
  --secret-string '{"quip_access_token":"YOUR_TOKEN","folder_ids":"FOLDER1,FOLDER2"}'
```

## Deployment Methods

### Method 1: Command Line Parameters (Recommended)

This method passes parameters directly to the CDK deploy command:

```bash
cdk deploy \
  --parameters quicksightPrincipalId="user/d-12345abcde/S-1-2-34-1234567890-1234567890-1234567890-1234567890" \
  --parameters quicksightNamespace="default" \
  --parameters serviceRoleArn="arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0"
```

**Advantages**:
- Parameters are explicit and visible
- Easy to use different parameters for different deployments
- No file modifications required

### Method 2: CDK Context Configuration

Add parameters to `cdk.json` context section:

```json
{
  "app": "python app.py",
  "context": {
    "quicksightPrincipalId": "user/d-12345abcde/S-1-2-34-1234567890-1234567890-1234567890-1234567890",
    "quicksightNamespace": "default",
    "serviceRoleArn": "arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0",
    "@aws-cdk/aws-lambda:recognizeLayerVersion": true
  }
}
```

Then deploy:
```bash
cdk deploy
```

**Advantages**:
- Parameters stored in version control
- Consistent deployments
- No need to remember parameter values

### Method 3: Environment Variables

Set environment variables before deployment:

```bash
export CDK_QUICKSIGHT_PRINCIPAL_ID="user/d-12345abcde/S-1-2-34-1234567890-1234567890-1234567890-1234567890"
export CDK_QUICKSIGHT_NAMESPACE="default"
export CDK_SERVICE_ROLE_ARN="arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0"

cdk deploy
```

**Note**: This method requires modifying `app.py` to read from environment variables.

## Parameter Configuration

### QuickSight Principal ID

The QuickSight Principal ID identifies the user who can access the S3 bucket through Quick Suite.

**Format**: `user/d-{directory-id}/S-1-5-21-{domain-sid}-{user-rid}`

**How to find**:
1. Go to AWS QuickSight console
2. Navigate to "Manage QuickSight" → "Security & permissions"
3. Find your user in the user list
4. The Principal ID is displayed in the user details

**Example**: `user/d-12345abcde/S-1-2-34-1234567890-1234567890-1234567890-1234567890`

### QuickSight Namespace

The namespace for QuickSight resources.

**Default**: `default`
**Custom**: Use your organization's namespace if configured

### Service Role ARN

The ARN of the QuickSight service role that will access the S3 bucket.

**Format**: `arn:aws:iam::{account-id}:role/service-role/aws-quicksight-service-role-v0`

**How to find**:
1. Go to AWS IAM console
2. Navigate to "Roles"
3. Search for "quicksight"
4. Find the service role (usually named `aws-quicksight-service-role-v0`)
5. Copy the ARN from the role details

**Example**: `arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0`

## Environment-Specific Deployments

### Development Environment

```bash
# Deploy to development with dev-specific parameters
cdk deploy QuipSyncStack-Dev \
  --parameters quicksightPrincipalId="user/d-dev123/S-1-5-21-dev-principal" \
  --parameters quicksightNamespace="dev" \
  --parameters serviceRoleArn="arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-dev"
```

### Production Environment

```bash
# Deploy to production with prod-specific parameters
cdk deploy QuipSyncStack-Prod \
  --parameters quicksightPrincipalId="user/d-prod456/S-1-5-21-prod-principal" \
  --parameters quicksightNamespace="default" \
  --parameters serviceRoleArn="arn:aws:iam::987654321098:role/service-role/aws-quicksight-service-role-v0"
```

## Secrets Manager Configuration

### Secret Structure

The system expects a secret with the following JSON structure:

```json
{
  "quip_access_token": "YOUR_QUIP_ACCESS_TOKEN",
  "folder_ids": "folder1_id,folder2_id,folder3_id"
}
```

### Creating the Secret

#### Method 1: AWS CLI

```bash
aws secretsmanager create-secret \
  --name "quip-sync-credentials" \
  --description "Quip access token and folder IDs for sync system" \
  --secret-string '{
    "quip_access_token": "abcd1234efgh5678ijkl9012mnop3456",
    "folder_ids": "ABC123DEF456,GHI789JKL012,MNO345PQR678"
  }'
```

#### Method 2: AWS Console

1. Navigate to AWS Secrets Manager
2. Click "Store a new secret"
3. Select "Other type of secret"
4. Add key-value pairs:
   - Key: `quip_access_token`, Value: `YOUR_TOKEN`
   - Key: `folder_ids`, Value: `folder1,folder2,folder3`
5. Name the secret: `quip-sync-credentials`
6. Complete the creation process

### Environment-Specific Secrets

#### Development Secret

```bash
aws secretsmanager create-secret \
  --name "quip-sync-credentials-dev" \
  --secret-string '{
    "quip_access_token": "dev_token_here",
    "folder_ids": "DEV_FOLDER_ID"
  }'
```

#### Production Secret

```bash
aws secretsmanager create-secret \
  --name "quip-sync-credentials-prod" \
  --secret-string '{
    "quip_access_token": "prod_token_here",
    "folder_ids": "PROD_FOLDER_1,PROD_FOLDER_2,PROD_FOLDER_3"
  }'
```

## Deployment Validation

### 1. Verify Stack Deployment

```bash
# Check if stack was deployed successfully
aws cloudformation describe-stacks --stack-name QuipSyncStack

# List stack resources
aws cloudformation list-stack-resources --stack-name QuipSyncStack
```

### 2. Verify Lambda Function

```bash
# Check Lambda function configuration
aws lambda get-function --function-name QuipSyncStack-QuipSyncFunction

# Test Lambda function
aws lambda invoke \
  --function-name QuipSyncStack-QuipSyncFunction \
  --payload '{}' \
  response.json && cat response.json
```

### 3. Verify S3 Bucket

```bash
# Check if S3 bucket exists
aws s3 ls | grep quip-sync

# Check bucket policy (will only exist if QuickSight parameters were provided during deployment)
aws s3api get-bucket-policy --bucket YOUR-ACCOUNT-ID-quip-sync
```

### 4. Verify EventBridge Rule

```bash
# Check EventBridge rule
aws events describe-rule --name QuipSyncStack-QuipSyncSchedule

# List rule targets
aws events list-targets-by-rule --rule QuipSyncStack-QuipSyncSchedule
```

### 5. Verify Secrets Manager

```bash
# Check if secret exists
aws secretsmanager describe-secret --secret-id quip-sync-credentials

# Test secret retrieval (be careful in production)
aws secretsmanager get-secret-value --secret-id quip-sync-credentials
```

## Rollback Procedures

### Complete Stack Rollback

```bash
# Delete the entire stack
cdk destroy

# Confirm deletion
aws cloudformation describe-stacks --stack-name QuipSyncStack
```

### Partial Rollback

```bash
# Disable EventBridge rule (stops automatic execution)
aws events disable-rule --name QuipSyncStack-QuipSyncSchedule

# Delete specific resources if needed
aws lambda delete-function --function-name QuipSyncStack-QuipSyncFunction
```

## Monitoring Setup

### CloudWatch Dashboard

Create a custom dashboard to monitor the sync system:

```bash
# Create dashboard JSON configuration
cat > dashboard.json << 'EOF'
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/Lambda", "Duration", "FunctionName", "QuipSyncStack-QuipSyncFunction"],
          ["AWS/Lambda", "Errors", "FunctionName", "QuipSyncStack-QuipSyncFunction"],
          ["AWS/Lambda", "Invocations", "FunctionName", "QuipSyncStack-QuipSyncFunction"]
        ],
        "period": 300,
        "stat": "Average",
        "region": "us-east-1",
        "title": "Lambda Metrics"
      }
    }
  ]
}
EOF

# Create the dashboard
aws cloudwatch put-dashboard \
  --dashboard-name "QuipSyncMonitoring" \
  --dashboard-body file://dashboard.json
```

### Custom Alarms

```bash
# Create alarm for Lambda errors
aws cloudwatch put-metric-alarm \
  --alarm-name "QuipSync-LambdaErrors" \
  --alarm-description "Alert when Lambda function has errors" \
  --metric-name "Errors" \
  --namespace "AWS/Lambda" \
  --statistic "Sum" \
  --period 300 \
  --threshold 1 \
  --comparison-operator "GreaterThanOrEqualToThreshold" \
  --dimensions Name=FunctionName,Value=QuipSyncStack-QuipSyncFunction \
  --evaluation-periods 1
```

## Troubleshooting Deployment Issues

### Common CDK Errors

1. **Bootstrap Required**:
   ```
   Error: This stack uses assets, so the toolkit stack must be deployed
   ```
   **Solution**: Run `cdk bootstrap`

2. **Insufficient Permissions**:
   ```
   Error: User is not authorized to perform: iam:CreateRole
   ```
   **Solution**: Ensure AWS credentials have sufficient IAM permissions

3. **Resource Already Exists**:
   ```
   Error: Bucket already exists
   ```
   **Solution**: Use `cdk deploy --force` or delete existing resources

### Lambda Deployment Issues

1. **Package Too Large**:
   ```
   Error: Unzipped size must be smaller than 262144000 bytes
   ```
   **Solution**: Optimize dependencies or use Lambda layers

2. **Runtime Not Supported**:
   ```
   Error: The runtime parameter of python3.13 is not supported
   ```
   **Solution**: Update to supported Python runtime in CDK stack

### S3 Bucket Issues

1. **Bucket Name Conflict**:
   ```
   Error: Bucket name already exists
   ```
   **Solution**: Bucket names are globally unique; the system uses account ID prefix to avoid conflicts

2. **Policy Validation Error**:
   ```
   Error: Invalid bucket policy
   ```
   **Solution**: Verify QuickSight parameters are correct

3. **No Bucket Policy Created**:
   ```
   Error: NoSuchBucketPolicy when checking bucket policy
   ```
   **Solution**: Bucket policy is only created when `serviceRoleArn` parameter is provided during deployment. If you need QuickSight access, redeploy with the required parameters.

## Advanced Configuration

### Custom Secret Names

To use a different secret name, modify the Lambda environment variables:

```python
# In quip_sync_stack.py
lambda_function = _lambda.Function(
    # ... other configuration
    environment={
        "SECRET_NAME": "my-custom-secret-name",
        "S3_BUCKET_NAME": bucket.bucket_name
    }
)
```

### Custom S3 Bucket Names

To use a custom bucket name pattern:

```python
# In quip_sync_stack.py
bucket = s3.Bucket(
    self, "QuipSyncBucket",
    bucket_name=f"my-custom-prefix-{self.account}-quip-sync",
    # ... other configuration
)
```

### Custom Schedule

To change the sync schedule:

```python
# In quip_sync_stack.py
schedule_rule = events.Rule(
    self, "QuipSyncSchedule",
    schedule=events.Schedule.cron(
        minute="0",
        hour="6",  # 6 AM UTC instead of 2 PM UTC (midnight Sydney)
        day="*",
        month="*",
        year="*"
    )
)
```

## Performance Optimization

### Lambda Configuration Tuning

```python
# Optimize for large document sets
lambda_function = _lambda.Function(
    # ... other configuration
    memory_size=2048,  # Increase memory for faster processing
    timeout=Duration.minutes(15),  # Maximum timeout
    reserved_concurrent_executions=1  # Prevent concurrent executions
)
```

### Batch Processing

For very large folder structures, consider implementing batch processing:

```python
# Environment variable for batch size
environment={
    "BATCH_SIZE": "50",  # Process 50 documents at a time
    "MAX_RETRIES": "3"
}
```

This completes the comprehensive deployment documentation with detailed configuration examples and troubleshooting guidance.