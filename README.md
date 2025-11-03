# Quick Suite Quip-to-S3 Synchronization System

This application has been developed to allow Amazon staff to use Quip documents as a knowledge base in our internal Quick Suite. Since Quip is being deprecated at Amazon and there are no plans for an offical integration from Quip to Quick Suite, this application provides a DIY alternative. 

It is a serverless application deployed into your Isengard account that automatically synchronizes documents from nominated Quip folders to an AWS S3 bucket. The system runs daily at midnight Sydney time, detecting and syncing only changed documents to minimize processing time and costs.

## Features

- **Automated Daily Sync**: EventBridge triggers Lambda function at midnight Sydney time
- **Change Detection**: Only syncs documents that have been modified since last sync
- **Multiple Knowledge Bases**: Create different knowledge bases focused on different Quip folders
- **Secure Credential Storage**: Quip access tokens stored in AWS Secrets Manager
- **Quick Suite Integration**: S3 bucket configured for Quick Suite access via a bucket policy
- **Comprehensive Logging**: CloudWatch logs with structured JSON logging
- **Infrastructure as Code**: Complete AWS CDK deployment

## Architecture

```
EventBridge Rule → Lambda Function → Quip API
                                  ↓
                   Secrets Manager ← → S3 Bucket → Quick Suite
```

## Project Structure

```
├── src/                          # Lambda function source code
│   ├── lambda_function.py        # Main Lambda handler
│   ├── models/                   # Data models
│   │   ├── thread_metadata.py    # Quip thread metadata model
│   │   ├── s3_object.py          # S3 object model
│   │   └── sync_result.py        # Synchronization result model
│   ├── clients/                  # External service clients
│   │   ├── secrets_client.py     # AWS Secrets Manager client
│   │   ├── quip_client.py        # Quip API client
│   │   └── s3_client.py          # AWS S3 client
│   ├── services/                 # Business logic services
│   │   └── sync_engine.py        # Synchronization engine
│   └── exceptions.py             # Custom exception classes
├── infrastructure/               # CDK infrastructure code
│   └── quip_sync_stack.py        # CDK stack definition
├── app.py                        # CDK app entry point
├── cdk.json                      # CDK configuration
└── requirements.txt              # Python dependencies
```

## Step by Step Guide

Building this application requires some back and forth between Quick Suite, Quip and the deploy script so please follow the step-by-step guide below.

### 1. Clone the Repository and Install the Prerequisites

1. **Clone the repository**:
   ```bash
   git clone https://github.com/mkhs-aws/quip-s3-sync
   cd quip-s3-sync
   ```

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install CDK dependencies**:
   ```bash
   npm install -g aws-cdk
   ```

### 2. Start Creating an Amazon S3 Integration in Quick Suite

We first need to start the process of creating an Amazon S3 integration in Quick Suite in order to get the identifiers required for the bucket policy.

1. Open Quick Suite in your browser and click the Connections > Integrations menu item
2. Create a new Amazon S3 integration by clicking the plus [+] icon
3. Update the Integration name e.g. My Quip Documents
4. Change the AWS Account from the default (Quick Instance Account) to "Other AWS Account"
5. Enter the ID of the account where you want to deploy the application
6. Enter the bucket name as "s3://[Account ID]-quip-sync-[custom-name]" where:
   - `[Account ID]` is the ID of the account where you want to deploy the application
   - `[custom-name]` is the custom name you will choose during deployment
   - Example: "s3://123456789012-quip-sync-my-quip-sync"
7. Click the Copy policy icon in order to copy the bucket policy to your clipboard
8. Paste the bucket policy into a text editor to retrieve the IDs below

NOTE: Do not click "Create and Continue" yet as the integration creation will fail since the bucket has not been created yet.

Identify the following from the bucket policy in the text editor:

1. **QuickSight Principal ID**: The user principal ID for Quick Suite access
   - The value associated with "aws:PrincipalTag/QuickSightDataSourceCreatorPrincipalId"
   - Format: `user/d-xxxxxxxxxx/S-1-5-21-xxxxxxxxxx-xxxxxxxxxx-xxxxxxxxxx-xxxxxxxx`

2. **QuickSight Namespace**: The QuickSight namespace (
    - The value associated with "aws:PrincipalTag/QuickSightNamespace" (usually "default")

3. **Service Role ARN**: The QuickSight service role ARN
   - The value associated with "Principal" > "AWS" (usually "arn:aws:iam::<Account ID>:role/service-role/aws-quicksight-service-role-v0")
   - Format: `arn:aws:iam::ACCOUNT-ID:role/service-role/aws-quicksight-service-role-v0`

### 3. Create a Quip Personal Access Token

The Quip Personal Access Token provides programmatic access to your Quip documents using the [Quip Automation APIs](https://quip.com/dev/automation/documentation/current). 

This can be generated by authenticating your browser via Midway and going to https://quip-amazon.com/dev/token

NOTE: Every time you go to this web page a new personal access token is generated and the previous token is deleted.

### 4. Retrieve the Quip Folder IDs

You can nominated 1 or more Quip folders to be added to the Quick Suite knowledge base. You can get this by opening the folder in Quip and copying the 12 character identifier in the URL just after "https://quip-amazon.com/".

If you want more than 1 folder in your knowledge base then provide them as a comma separated list in the step below.

### 5. Add your Isengard account credentials

Navigate to https://isengard.amazon.com and generate a set of temporary credentials for the account you want to deploy the application into.

Paste these into your terminal window.

### 6. Run the Automated Deployment Script

Use the interactive deployment script for the easiest setup:

```bash
# Option 1: Bash script (Linux/macOS)
./deploy.sh

# Option 2: Python script (cross-platform)
python deploy.py
```

The deployment script will:
1. Check prerequisites (AWS CLI, CDK)
2. **Prompt for a custom name** for resource naming (used for all AWS resources)
3. Prompt for the region you wish to deploy the application into e.g. us-east-1
4. Prompt for the Quick Suite IDs for the S3 bucket policy
5. Prompt for the Quip personal access token
6. Prompt for the Quip folder/s as a comma separated list of folder IDs
7. Deploy the CDK stack with bucket policy
8. Configure AWS Secrets Manager
9. Verify the deployment
10. Run the Lambda function to do the initial document sync

**Custom Name Requirements:**
- Must be 3-40 characters long (to accommodate S3 bucket naming with account ID and "quip-sync" prefix)
- Can only contain lowercase letters, numbers, and hyphens
- Must start and end with a letter or number
- Cannot contain consecutive hyphens
- Cannot be formatted as an IP address
- Cannot contain AWS reserved words (aws, amazon, amzn)

**Examples of valid custom names:**
- `accounts`
- `partner-meetings`
- `engineering-kb`
- `sales-materials`

**Resource Naming Convention:**
All AWS resources will be named using the custom name:
- CloudFormation Stack: `QuipSyncStack-<custom-name>`
- S3 Bucket: `<account-id>-quip-sync-<custom-name>`
- Secret: `quip-sync-<custom-name>-credentials`
- Lambda Function: `quip-sync-<custom-name>-function`
- IAM Role: `quip-sync-<custom-name>-lambda-execution-role`
- EventBridge Rule: `quip-sync-<custom-name>-daily-schedule`
- CloudWatch Alarms: `quip-sync-<custom-name>-*`
- SNS Topic: `quip-sync-<custom-name>-alarms`
- Log Group: `/aws/lambda/quip-sync-<custom-name>-function`

### 7. Complete Creation of the Amazon S3 Integration in Quick Suite

Once the application has been successfully deployed and the Lambda funtion has finished the initial document sync you can return to Quick Suite and click the "Create and continue" button.

After a few minutes your knowledge base should be ready!

## Manual Deployment

If you prefer manual deployment, see the [DEPLOYMENT.md](DEPLOYMENT.md) guide.

## Prerequisites

### Software Requirements

- **Python 3.13+**: Required for Lambda runtime compatibility
- **Node.js 18+**: Required for AWS CDK
- **AWS CLI**: Configured with appropriate credentials
- **AWS CDK**: Install globally with `npm install -g aws-cdk`

### AWS Account Setup

1. **AWS Account**: Active AWS account with appropriate permissions
2. **CDK Bootstrap**: Run `cdk bootstrap` in your target region
3. **IAM Permissions**: Ensure your AWS credentials have permissions to create:
   - Lambda functions
   - S3 buckets
   - EventBridge rules
   - IAM roles and policies
   - Secrets Manager secrets
   - CloudWatch log groups

### Quip Setup

1. **Personal Access Token**: Generate a Quip personal access token
   - Go to Quip → Account Settings → Developer Tools
   - Generate new token with appropriate permissions
2. **Folder IDs**: Identify the Quip folder IDs you want to sync
   - Navigate to each folder in Quip
   - Extract folder ID from URL (e.g., `https://quip.com/folder/ABC123DEF456`)


## Deployment

### Method 1: Command Line Context Parameters

Deploy with custom name and Quick Suite parameters as context arguments:

```bash
# Deploy with all parameters (custom name is required)
# Stack name will be automatically generated as QuipSyncStack-<custom-name>
cdk deploy QuipSyncStack-my-quip-sync \
  --context customName="my-quip-sync" \
  --context quicksightPrincipalId="user/d-12345abcde/S-1-2-34-1234567890-1234567890-1234567890-1234567890" \
  --context quicksightNamespace="default" \
  --context serviceRoleArn="arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0"

# Deploy with minimal parameters (only custom name required)
cdk deploy QuipSyncStack-team-docs --context customName="team-docs"
```

### Method 2: CDK Context

Set parameters in `cdk.json` context and deploy:

```json
{
  "context": {
    "customName": "my-quip-sync",
    "quicksightPrincipalId": "user/d-12345abcde/S-1-2-34-1234567890-1234567890-1234567890-1234567890",
    "quicksightNamespace": "default",
    "serviceRoleArn": "arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0"
  }
}
```

Then deploy (stack name will be automatically generated as QuipSyncStack-<custom-name>):
```bash
cdk deploy QuipSyncStack-my-quip-sync
```

### Method 3: Interactive Deployment Script (Recommended)

Use the deployment script which prompts for all required parameters:

```bash
# Python script (cross-platform)
python deploy.py

# Bash script (Linux/macOS)
./deploy.sh
```

The script will prompt for:
- Custom name (required)
- AWS region
- QuickSight configuration
- Quip credentials

**Example deployment session:**
```
Custom name for resources: my-quip-sync
AWS Region for deployment [us-east-1]: us-east-1
QuickSight Principal ID: user/d-12345abcde/S-1-2-34-1234567890-1234567890-1234567890-1234567890
QuickSight Namespace [default]: default
QuickSight Service Role ARN: arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0
```

## Post-Deployment Setup

### 1. Configure Secrets Manager

After deployment, create the required secret:

```bash
# Create the secret with your Quip credentials
# Note: Replace CUSTOM-NAME with your actual custom name
aws secretsmanager create-secret \
  --name "quip-sync-CUSTOM-NAME-credentials" \
  --description "Quip access token and folder IDs for sync system" \
  --secret-string '{
    "quip_access_token": "YOUR_ACTUAL_TOKEN_HERE",
    "folder_ids": "folder1_id,folder2_id,folder3_id"
  }'

# Example with actual values:
aws secretsmanager create-secret \
  --name "quip-sync-my-quip-sync-credentials" \
  --description "Quip access token and folder IDs for sync system" \
  --secret-string '{
    "quip_access_token": "YOUR_ACTUAL_TOKEN_HERE",
    "folder_ids": "folder1_id,folder2_id,folder3_id"
  }'
```

Or use the AWS Console:
1. Go to AWS Secrets Manager
2. Create new secret
3. Choose "Other type of secret"
4. Add the key-value pairs as shown above
5. Name the secret using format: `quip-sync-CUSTOM-NAME-credentials` (e.g., `quip-sync-my-quip-sync-credentials`)

### 2. Test the Deployment

Test the Lambda function manually:

```bash
# Invoke the Lambda function (replace CUSTOM-NAME with your actual custom name)
aws lambda invoke \
  --function-name quip-sync-CUSTOM-NAME-function \
  --payload '{}' \
  response.json

# Example with actual custom name:
aws lambda invoke \
  --function-name quip-sync-my-quip-sync-function \
  --payload '{}' \
  response.json

# Check the response
cat response.json
```

### 3. Monitor Execution

Check CloudWatch logs for execution details:

```bash
# View recent log events (replace CUSTOM-NAME with your actual custom name)
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/quip-sync-CUSTOM-NAME"

# Tail logs in real-time during execution
aws logs tail /aws/lambda/quip-sync-CUSTOM-NAME-function --follow

# Example with actual custom name:
aws logs tail /aws/lambda/quip-sync-my-quip-sync-function --follow
```

## Configuration Examples

### Example 1: Single Folder Sync

```json
{
  "quip_access_token": "abcd1234efgh5678ijkl9012mnop3456",
  "folder_ids": "ABC123DEF456"
}
```

### Example 2: Multiple Folders Sync

```json
{
  "quip_access_token": "abcd1234efgh5678ijkl9012mnop3456",
  "folder_ids": "ABC123DEF456,GHI789JKL012,MNO345PQR678"
}
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**:
   - Verify Quip access token is valid and regenerate if necessary
   - Ensure Secrets Manager secret exists and is accessible

2. **Folder Not Found Errors**:
   - Verify folder IDs are correct
   - Check folder permissions in Quip
   - Ensure folders contain documents (not just subfolders)

3. **S3 Upload Failures**:
   - Check Lambda execution role has S3 permissions
   - Verify S3 bucket exists and is accessible
   - Check CloudWatch logs for detailed error messages

4. **EventBridge Not Triggering**:
   - Verify EventBridge rule is enabled
   - Check rule schedule expression
   - Ensure Lambda function has proper permissions

### Debugging Commands

```bash
# Check Lambda function configuration (replace CUSTOM-NAME with your actual custom name)
aws lambda get-function --function-name quip-sync-CUSTOM-NAME-function

# Example:
aws lambda get-function --function-name quip-sync-my-quip-sync-function

# List S3 bucket contents (replace with your actual account ID and custom name)
aws s3 ls s3://YOUR-ACCOUNT-ID-quip-sync-YOUR-CUSTOM-NAME/

# Example:
aws s3 ls s3://123456789012-quip-sync-my-quip-sync/

# Check secret value (be careful with this in production)
aws secretsmanager get-secret-value --secret-id quip-sync-YOUR-CUSTOM-NAME-credentials

# Example:
aws secretsmanager get-secret-value --secret-id quip-sync-my-quip-sync-credentials

# View CloudWatch alarms (replace CUSTOM-NAME with your actual custom name)
aws cloudwatch describe-alarms --alarm-names quip-sync-CUSTOM-NAME-lambda-errors

# Example:
aws cloudwatch describe-alarms --alarm-names quip-sync-my-quip-sync-lambda-errors
```

## Monitoring

### CloudWatch Metrics

The system automatically creates the following metrics:
- Lambda execution duration
- Lambda error rate
- S3 upload success/failure rates
- API call latencies

### CloudWatch Alarms

Automatic alarms are created for:
- Lambda function failures
- Execution timeout warnings
- High error rates from Quip API
- S3 upload failures

### Log Analysis

Logs are structured in JSON format with correlation IDs:

```json
{
  "timestamp": "2024-01-15T14:00:00Z",
  "level": "INFO",
  "correlation_id": "abc123-def456-ghi789",
  "message": "Synchronization completed",
  "metrics": {
    "threads_discovered": 45,
    "documents_processed": 12,
    "documents_uploaded": 3,
    "execution_time_seconds": 127.5
  }
}
```

## Maintenance

### Regular Tasks

1. **Monitor Execution**: Check CloudWatch logs weekly for errors
2. **Review Costs**: Monitor S3 storage and Lambda execution costs
3. **Update Dependencies**: Keep Python packages and CDK updated
4. **Rotate Credentials**: Rotate Quip access tokens periodically

### Scaling Considerations

- **Large Folders**: System handles up to 1000 documents per folder efficiently
- **Memory Usage**: Lambda configured with 1GB memory for large document processing
- **Timeout**: 15-minute timeout allows for processing large document sets
- **Rate Limits**: Built-in retry logic handles Quip API rate limits

## Security

### Best Practices

1. **Credential Rotation**: Regularly rotate Quip access tokens
2. **Least Privilege**: IAM roles follow least-privilege principle
3. **Encryption**: All data encrypted in transit and at rest
4. **Audit Logging**: Comprehensive CloudWatch logging for audit trails

### Compliance

- **Data Residency**: Documents stored in specified AWS region
- **Access Control**: S3 bucket access restricted to Quick Suite service role
- **Encryption**: Server-side encryption enabled on S3 bucket
- **Logging**: All API calls and data access logged

## Local Development

For development and testing, you can run the Lambda function locally:

### Setup Local Environment

1. **Copy environment template**:
   ```bash
   cp .env.example .env
   ```

2. **Configure your credentials** in `.env`:
   ```bash
   # Required: Your Quip credentials
   QUIP_ACCESS_TOKEN=your_actual_token_here
   QUIP_FOLDER_IDS=folder1_id,folder2_id,folder3_id
   
   # Optional: AWS configuration (uses defaults if not set)
   AWS_REGION=us-east-1
   S3_BUCKET_NAME=your-account-id-quip-sync-your-custom-name
   LOG_LEVEL=INFO
   ```

3. **Get your Quip credentials**:
   - **Access Token**: Go to Quip → Account Settings → Developer Tools → Generate Token
   - **Folder IDs**: Navigate to folders in Quip, extract IDs from URLs like `https://platform.quip-amazon.com/folder/ABC123DEF456`

### Run Locally

```bash
# Method 1: Using the convenience script (loads .env automatically)
python run_local.py

# Method 2: Using environment variables directly
export QUIP_ACCESS_TOKEN="Bearer your_token_here"
export QUIP_FOLDER_IDS="folder1,folder2,folder3"
export S3_BUCKET_NAME="your-account-id-quip-sync-your-custom-name"
python local_runner.py
```

### Local Development Features

- **Environment Variable Support**: Use local credentials instead of Secrets Manager
- **AWS Integration**: Still connects to real S3 and AWS services
- **Full Logging**: See detailed DEBUG logs in your terminal
- **Mock Lambda Context**: Simulates Lambda execution environment
- **Error Handling**: Clear error messages and stack traces

### Prerequisites for Local Development

- **Python 3.13+**: Same as Lambda runtime
- **AWS Credentials**: Configured via AWS CLI, environment variables, or IAM roles
- **S3 Bucket**: Must exist and be accessible
- **Quip Access**: Valid access token and folder permissions

## Support

For issues and questions:
1. Check CloudWatch logs for detailed error messages
2. Review this documentation for configuration examples
3. Verify all prerequisites are met
4. Test with a single folder before scaling to multiple folders
5. Use local development mode for debugging

## Dependencies

- **boto3**: AWS SDK for Python
- **requests**: HTTP client for Quip API
- **aws-lambda-powertools**: Lambda utilities and logging
- **aws-cdk-lib**: AWS CDK for infrastructure as code
- **pytest**: Testing framework (development)
- **moto**: AWS service mocking for tests (development)