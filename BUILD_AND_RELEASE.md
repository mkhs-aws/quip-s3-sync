# Build and Release Guide

This guide explains how to build and release the Quip-S3 Sync application for distribution to internal users.

## Overview

The application is designed to be deployed without requiring users to clone the Git repository. Instead:

1. **Lambda code** is packaged as a zip file and stored in S3
2. **CloudFormation template** is generated from CDK
3. **Users deploy** directly from the AWS CloudFormation console

## Prerequisites

- AWS CLI configured with credentials
- Python 3.13+
- Node.js 18+ (for CDK)
- AWS CDK installed globally: `npm install -g aws-cdk`

## Build Process

### Step 1: Package Lambda Code

```bash
# Make the build script executable
chmod +x build-lambda.sh

# Run the build script
./build-lambda.sh
```

This creates `quip-sync-lambda.zip` containing:
- All Lambda source code from `src/`
- All Python dependencies from `requirements.txt`
- Optimized for Lambda deployment

### Step 2: Generate CloudFormation Template

```bash
# Activate the virtual environment
source venv/bin/activate

# Synthesize the CDK app to generate CloudFormation template
cdk synth

# This creates the template in: cdk.out/QuipSyncStack-default.template.json
```

The template will be generated with a "default" custom name since no specific name is provided during synthesis. Users will specify their own custom name when deploying.

## Release Process

### Step 1: Create S3 Bucket for Lambda Code

```bash
# Replace <account-id> with your AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
LAMBDA_BUCKET="$ACCOUNT_ID-quip-s3-sync-lambda"

# Create the bucket (if it doesn't exist)
aws s3 mb "s3://$LAMBDA_BUCKET"

# Block public access (recommended)
aws s3api put-public-access-block \
  --bucket "$LAMBDA_BUCKET" \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

### Step 2: Upload Lambda Code to S3

```bash
# Upload the packaged Lambda code
aws s3 cp quip-sync-lambda.zip "s3://$LAMBDA_BUCKET/"

# Verify upload
aws s3 ls "s3://$LAMBDA_BUCKET/"
```

### Step 3: Store CloudFormation Template

Store the CloudFormation template in a location accessible to your users:

```bash
# Option 1: Upload to S3 (if you have a distribution bucket)
aws s3 cp cdk.out/QuipSyncStack.json "s3://your-distribution-bucket/quip-sync-template.json"

# Option 2: Store in OneDrive or internal documentation
# Copy the contents of cdk.out/QuipSyncStack.json to your internal storage

# Option 3: Create a Quick Create URL
# See README.md for instructions on creating a CloudFormation Quick Create link
```

## User Deployment

Users can now deploy without cloning the repository:

### Option 1: AWS CloudFormation Console

1. Go to [AWS CloudFormation Console](https://console.aws.amazon.com/cloudformation)
2. Click "Create Stack"
3. Upload the CloudFormation template
4. Fill in parameters:
   - Custom Name (3-40 characters)
   - QuickSight Principal ID
   - QuickSight Namespace
   - Service Role ARN
5. Click "Create Stack"

### Option 2: AWS CLI

```bash
# Deploy using the template
aws cloudformation create-stack \
  --stack-name QuipSyncStack-my-deployment \
  --template-body file://cdk.out/QuipSyncStack.json \
  --parameters \
    ParameterKey=customName,ParameterValue=my-deployment \
    ParameterKey=quicksightPrincipalId,ParameterValue=user/d-xxx/S-1-5-21-xxx \
    ParameterKey=quicksightNamespace,ParameterValue=default \
    ParameterKey=serviceRoleArn,ParameterValue=arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0 \
  --capabilities CAPABILITY_NAMED_IAM
```

## Versioning

When releasing new versions:

1. Update version in `package.json` or create a git tag
2. Run the build process
3. Upload new `quip-sync-lambda.zip` to S3 (overwrites previous version)
4. Update CloudFormation template if infrastructure changes
5. Document changes in release notes

## Troubleshooting

### Lambda Code Not Found

If users get an error about Lambda code not being found:

1. Verify the S3 bucket exists: `aws s3 ls s3://<account-id>-quip-s3-sync-lambda/`
2. Verify the zip file is uploaded: `aws s3 ls s3://<account-id>-quip-s3-sync-lambda/quip-sync-lambda.zip`
3. Verify the Lambda execution role has S3 read permissions

### CloudFormation Template Issues

If the template fails to deploy:

1. Validate the template: `aws cloudformation validate-template --template-body file://cdk.out/QuipSyncStack.json`
2. Check CloudFormation events for detailed error messages
3. Ensure all required parameters are provided

### Build Script Issues

If the build script fails:

1. Ensure Python 3.13+ is installed: `python --version`
2. Ensure `requirements.txt` exists in the `src/` directory
3. Check disk space for the temporary build directory
4. Run with verbose output: `bash -x build-lambda.sh`

## Security Considerations

- **S3 Bucket**: Keep the Lambda code bucket private (block public access)
- **IAM Permissions**: Users need CloudFormation and IAM permissions to deploy
- **Secrets Manager**: Users must configure Quip credentials after deployment
- **CloudFormation Template**: Store in a secure location accessible only to authorized users

## Maintenance

### Updating Lambda Code

1. Make changes to source code in `src/`
2. Run `./build-lambda.sh` to create new zip
3. Upload to S3: `aws s3 cp quip-sync-lambda.zip s3://<account-id>-quip-s3-sync-lambda/`
4. Users can update their Lambda function by redeploying the CloudFormation stack

### Updating Infrastructure

1. Make changes to CDK stack in `infrastructure/quip_sync_stack.py`
2. Run `cdk synth` to generate new template
3. Update the CloudFormation template in your distribution location
4. Users can update their stack by updating the CloudFormation stack with the new template
