#!/usr/bin/env python3
"""
Local runner for the Quip-S3 sync Lambda function

This script allows you to run the lambda_handler locally for development and testing.
It supports both environment variables and AWS credentials for accessing services.

Usage:
    python local_runner.py

Environment Variables:
    # Quip Configuration (required)
    QUIP_ACCESS_TOKEN=Bearer_your_token_here
    QUIP_FOLDER_IDS=folder1,folder2,folder3
    
    # AWS Configuration (optional - will use default AWS credentials if not set)
    AWS_REGION=us-east-1
    S3_BUCKET_NAME=your-account-id-quip-sync
    SECRET_NAME=quip-sync-credentials
    
    # Logging (optional)
    LOG_LEVEL=DEBUG

Example:
    export QUIP_ACCESS_TOKEN="Bearer abcd1234efgh5678"
    export QUIP_FOLDER_IDS="ABC123DEF456,GHI789JKL012"
    export AWS_REGION="us-east-1"
    export S3_BUCKET_NAME="264148669776-quip-sync"
    export LOG_LEVEL="INFO"
    python local_runner.py
"""

import os
import sys
import json
import logging
from typing import Dict, Any

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import the lambda function
from lambda_function import lambda_handler


class MockLambdaContext:
    """
    Mock Lambda context for local testing
    """
    def __init__(self):
        self.function_name = "quip-sync-function-local"
        self.function_version = "$LATEST"
        self.invoked_function_arn = "arn:aws:lambda:local:123456789012:function:quip-sync-function-local"
        self.memory_limit_in_mb = "1024"
        self.remaining_time_in_millis = 900000  # 15 minutes
        self.log_group_name = "/aws/lambda/quip-sync-function-local"
        self.log_stream_name = "2024/01/01/[$LATEST]local"
        self.aws_request_id = "local-test-request-id"
        
    def get_remaining_time_in_millis(self):
        return self.remaining_time_in_millis


def setup_environment():
    """
    Set up environment variables with defaults for local development
    """
    # Set default AWS region if not specified
    if not os.environ.get('AWS_REGION'):
        os.environ['AWS_REGION'] = 'us-east-1'
    
    # Set default S3 bucket name if not specified
    if not os.environ.get('S3_BUCKET_NAME'):
        # Try to construct from AWS account ID if available
        account_id = os.environ.get('AWS_ACCOUNT_ID')
        if account_id:
            os.environ['S3_BUCKET_NAME'] = f"{account_id}-quip-sync"
        else:
            # Use a placeholder - user will need to set this
            os.environ['S3_BUCKET_NAME'] = "your-account-id-quip-sync"
    
    # Set default secret name if not specified
    if not os.environ.get('SECRET_NAME'):
        os.environ['SECRET_NAME'] = 'quip-sync-credentials'
    
    # Set default log level if not specified
    if not os.environ.get('LOG_LEVEL'):
        os.environ['LOG_LEVEL'] = 'INFO'


def validate_environment():
    """
    Validate that required environment variables are set
    """
    required_vars = []
    
    # Check if we have Quip credentials via environment variables
    if not (os.environ.get('QUIP_ACCESS_TOKEN') and os.environ.get('QUIP_FOLDER_IDS')):
        # If not using env vars, we need AWS credentials and secret name
        if not os.environ.get('SECRET_NAME'):
            required_vars.append('SECRET_NAME (or QUIP_ACCESS_TOKEN + QUIP_FOLDER_IDS)')
    
    if not os.environ.get('S3_BUCKET_NAME'):
        required_vars.append('S3_BUCKET_NAME')
    
    if required_vars:
        print("❌ Missing required environment variables:")
        for var in required_vars:
            print(f"   - {var}")
        print("\nPlease set the required environment variables and try again.")
        print("See the docstring at the top of this file for examples.")
        return False
    
    return True


def print_configuration():
    """
    Print the current configuration for debugging
    """
    print("🔧 Configuration:")
    print(f"   AWS Region: {os.environ.get('AWS_REGION', 'Not set')}")
    print(f"   S3 Bucket: {os.environ.get('S3_BUCKET_NAME', 'Not set')}")
    print(f"   Secret Name: {os.environ.get('SECRET_NAME', 'Not set')}")
    print(f"   Log Level: {os.environ.get('LOG_LEVEL', 'Not set')}")
    
    # Show credential source
    if os.environ.get('QUIP_ACCESS_TOKEN') and os.environ.get('QUIP_FOLDER_IDS'):
        folder_count = len([f.strip() for f in os.environ.get('QUIP_FOLDER_IDS', '').split(',') if f.strip()])
        print(f"   Quip Credentials: Environment variables ({folder_count} folders)")
    else:
        print(f"   Quip Credentials: AWS Secrets Manager")
    print()


def main():
    """
    Main function to run the Lambda handler locally
    """
    print("🚀 Starting Quip-S3 Sync Local Runner")
    print("=" * 50)
    
    # Set up environment
    setup_environment()
    
    # Validate configuration
    if not validate_environment():
        sys.exit(1)
    
    # Print configuration
    print_configuration()
    
    # Create mock context
    context = MockLambdaContext()
    
    # Create empty event (EventBridge doesn't send meaningful data)
    event = {}
    
    try:
        print("📋 Invoking lambda_handler...")
        print("-" * 30)
        
        # Call the lambda handler
        result = lambda_handler(event, context)
        
        print("-" * 30)
        print("✅ Lambda execution completed successfully!")
        print()
        print("📊 Result:")
        print(json.dumps(result, indent=2, default=str))
        
    except KeyboardInterrupt:
        print("\n⚠️  Execution interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Lambda execution failed: {str(e)}")
        print("\n🔍 Full error details:")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()