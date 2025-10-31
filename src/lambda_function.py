"""
Main Lambda function handler for Quip-to-S3 synchronization
"""

import os
import time
import logging
from typing import Dict, Any

from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.metrics import MetricUnit

from clients.secrets_client import SecretsClient
from clients.s3_client import S3Client
from clients.quip_client import QuipClient
from services.sync_engine import SyncEngine
from exceptions import QuipSyncError, SecretsManagerError, S3OperationError, QuipAPIError, ConfigurationError

# Initialize structured logger and metrics
logger = Logger()
metrics = Metrics()

# Configure standard logging for other modules
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """
    Main Lambda handler for Quip-S3 synchronization
    
    Orchestrates the complete synchronization workflow:
    1. Initialize AWS clients using environment variables
    2. Retrieve Quip credentials from Secrets Manager
    3. Discover all threads in nominated folders
    4. Inventory existing S3 objects
    5. Detect changed documents
    6. Synchronize updated documents to S3
    7. Return execution summary with statistics
    
    Args:
        event: EventBridge event payload
        context: Lambda runtime context
        
    Returns:
        dict: Execution summary with sync statistics
    """
    execution_start_time = time.time()
    correlation_id = context.aws_request_id
    
    logger.info("Starting Quip-S3 synchronization", extra={
        "correlation_id": correlation_id,
        "event": event
    })
    
    try:
        # Validate required environment variables
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        secret_name = os.environ.get('SECRET_NAME')
        region_name = os.environ.get('AWS_REGION', 'us-east-1')
        
        if not bucket_name:
            raise ConfigurationError("S3_BUCKET_NAME environment variable is required")
        if not secret_name:
            raise ConfigurationError("SECRET_NAME environment variable is required")
        
        logger.info("Environment configuration validated", extra={
            "correlation_id": correlation_id,
            "bucket_name": bucket_name,
            "secret_name": secret_name,
            "region": region_name
        })
        
        # Initialize AWS clients with correlation ID
        logger.info("Initializing AWS clients", extra={"correlation_id": correlation_id})
        
        secrets_client = SecretsClient(secret_name=secret_name, region_name=region_name)
        s3_client = S3Client(bucket_name=bucket_name, region_name=region_name, correlation_id=correlation_id)
        
        # Retrieve Quip credentials and configuration
        logger.info("Retrieving Quip credentials from Secrets Manager", extra={
            "correlation_id": correlation_id
        })
        
        access_token, folder_ids = secrets_client.get_quip_credentials()
        
        logger.info("Quip credentials retrieved successfully", extra={
            "correlation_id": correlation_id,
            "folder_count": len(folder_ids)
        })
        
        # Initialize Quip client and sync engine with correlation ID
        quip_client = QuipClient(access_token=access_token, correlation_id=correlation_id)
        sync_engine = SyncEngine(quip_client=quip_client, s3_client=s3_client, correlation_id=correlation_id)
        
        # Execute synchronization workflow
        logger.info("Starting synchronization workflow", extra={
            "correlation_id": correlation_id,
            "folder_ids": folder_ids
        })
        
        # Step 1: Discover all threads in nominated folders
        logger.info("Step 1: Discovering threads in folders", extra={
            "correlation_id": correlation_id
        })
        discovered_threads = sync_engine.discover_threads(folder_ids)
        
        # Step 2: Inventory existing S3 objects
        logger.info("Step 2: Inventorying S3 objects", extra={
            "correlation_id": correlation_id
        })
        s3_objects = s3_client.list_objects()
        
        logger.info("S3 inventory completed", extra={
            "correlation_id": correlation_id,
            "s3_object_count": len(s3_objects)
        })
        
        # Step 3: Detect changed documents
        logger.info("Step 3: Detecting changed documents", extra={
            "correlation_id": correlation_id
        })
        changed_thread_ids = sync_engine.detect_changes(discovered_threads, s3_objects)
        
        logger.info("Change detection completed", extra={
            "correlation_id": correlation_id,
            "changed_documents": len(changed_thread_ids)
        })
        
        # Step 4: Synchronize changed documents
        logger.info("Step 4: Synchronizing documents to S3", extra={
            "correlation_id": correlation_id
        })
        sync_result = sync_engine.sync_documents(changed_thread_ids)
        
        # Calculate total execution time
        total_execution_time = time.time() - execution_start_time
        
        # Prepare execution summary
        execution_summary = {
            "status": "success",
            "correlation_id": correlation_id,
            "execution_time_seconds": round(total_execution_time, 2),
            "sync_statistics": {
                "total_threads_discovered": sync_result.total_threads_discovered,
                "documents_processed": sync_result.documents_processed,
                "spreadsheets_skipped": sync_result.spreadsheets_skipped,
                "documents_uploaded": sync_result.documents_uploaded,
                "documents_unchanged": sync_result.documents_unchanged,
                "success_rate_percent": round(sync_result.success_rate, 2),
                "errors": sync_result.errors
            },
            "configuration": {
                "bucket_name": bucket_name,
                "folder_count": len(folder_ids),
                "region": region_name
            }
        }
        
        # Record overall execution metrics
        metrics.add_metric(name="LambdaExecutionDuration", unit=MetricUnit.Seconds, value=total_execution_time)
        metrics.add_metric(name="LambdaExecutionSuccess", unit=MetricUnit.Count, value=1)
        
        # Log final summary
        logger.info("Synchronization completed successfully", extra={
            "correlation_id": correlation_id,
            "execution_summary": execution_summary
        })
        
        return execution_summary
        
    except ConfigurationError as e:
        error_msg = f"Configuration error: {str(e)}"
        execution_time = time.time() - execution_start_time
        
        logger.error(error_msg, extra={
            "correlation_id": correlation_id,
            "error_type": "ConfigurationError"
        })
        
        # Record error metrics
        metrics.add_metric(name="LambdaExecutionErrors", unit=MetricUnit.Count, value=1)
        metrics.add_metric(name="ConfigurationErrors", unit=MetricUnit.Count, value=1)
        metrics.add_metric(name="LambdaExecutionDuration", unit=MetricUnit.Seconds, value=execution_time)
        
        return {
            "status": "error",
            "correlation_id": correlation_id,
            "error_type": "ConfigurationError",
            "error_message": error_msg,
            "execution_time_seconds": round(execution_time, 2)
        }
        
    except SecretsManagerError as e:
        error_msg = f"Secrets Manager error: {str(e)}"
        execution_time = time.time() - execution_start_time
        
        logger.error(error_msg, extra={
            "correlation_id": correlation_id,
            "error_type": "SecretsManagerError"
        })
        
        # Record error metrics
        metrics.add_metric(name="LambdaExecutionErrors", unit=MetricUnit.Count, value=1)
        metrics.add_metric(name="SecretsManagerErrors", unit=MetricUnit.Count, value=1)
        metrics.add_metric(name="LambdaExecutionDuration", unit=MetricUnit.Seconds, value=execution_time)
        
        return {
            "status": "error",
            "correlation_id": correlation_id,
            "error_type": "SecretsManagerError",
            "error_message": error_msg,
            "execution_time_seconds": round(execution_time, 2)
        }
        
    except QuipAPIError as e:
        error_msg = f"Quip API error: {str(e)}"
        execution_time = time.time() - execution_start_time
        
        logger.error(error_msg, extra={
            "correlation_id": correlation_id,
            "error_type": "QuipAPIError"
        })
        
        # Record error metrics
        metrics.add_metric(name="LambdaExecutionErrors", unit=MetricUnit.Count, value=1)
        metrics.add_metric(name="QuipAPIErrors", unit=MetricUnit.Count, value=1)
        metrics.add_metric(name="LambdaExecutionDuration", unit=MetricUnit.Seconds, value=execution_time)
        
        return {
            "status": "error",
            "correlation_id": correlation_id,
            "error_type": "QuipAPIError",
            "error_message": error_msg,
            "execution_time_seconds": round(execution_time, 2)
        }
        
    except S3OperationError as e:
        error_msg = f"S3 operation error: {str(e)}"
        execution_time = time.time() - execution_start_time
        
        logger.error(error_msg, extra={
            "correlation_id": correlation_id,
            "error_type": "S3OperationError"
        })
        
        # Record error metrics
        metrics.add_metric(name="LambdaExecutionErrors", unit=MetricUnit.Count, value=1)
        metrics.add_metric(name="S3OperationErrors", unit=MetricUnit.Count, value=1)
        metrics.add_metric(name="LambdaExecutionDuration", unit=MetricUnit.Seconds, value=execution_time)
        
        return {
            "status": "error",
            "correlation_id": correlation_id,
            "error_type": "S3OperationError",
            "error_message": error_msg,
            "execution_time_seconds": round(execution_time, 2)
        }
        
    except QuipSyncError as e:
        error_msg = f"Sync error: {str(e)}"
        execution_time = time.time() - execution_start_time
        
        logger.error(error_msg, extra={
            "correlation_id": correlation_id,
            "error_type": "QuipSyncError"
        })
        
        # Record error metrics
        metrics.add_metric(name="LambdaExecutionErrors", unit=MetricUnit.Count, value=1)
        metrics.add_metric(name="SyncErrors", unit=MetricUnit.Count, value=1)
        metrics.add_metric(name="LambdaExecutionDuration", unit=MetricUnit.Seconds, value=execution_time)
        
        return {
            "status": "error",
            "correlation_id": correlation_id,
            "error_type": "QuipSyncError",
            "error_message": error_msg,
            "execution_time_seconds": round(execution_time, 2)
        }
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        execution_time = time.time() - execution_start_time
        
        logger.error(error_msg, extra={
            "correlation_id": correlation_id,
            "error_type": "UnexpectedError",
            "exception": str(e)
        }, exc_info=True)
        
        # Record error metrics
        metrics.add_metric(name="LambdaExecutionErrors", unit=MetricUnit.Count, value=1)
        metrics.add_metric(name="UnexpectedErrors", unit=MetricUnit.Count, value=1)
        metrics.add_metric(name="LambdaExecutionDuration", unit=MetricUnit.Seconds, value=execution_time)
        
        return {
            "status": "error",
            "correlation_id": correlation_id,
            "error_type": "UnexpectedError",
            "error_message": error_msg,
            "execution_time_seconds": round(execution_time, 2)
        }

if __name__ == "__main__":
    """
    Allow direct execution of lambda_function.py for debugging
    """
    import uuid
    
    class MockContext:
        def __init__(self):
            self.aws_request_id = str(uuid.uuid4())
            self.function_name = "quip-sync-function-debug"
            self.remaining_time_in_millis = 900000
    
    # Create mock event and context
    event = {}
    context = MockContext()
    
    print("🚀 Running Lambda function directly...")
    print("=" * 50)
    
    try:
        result = lambda_handler(event, context)
        print("✅ Lambda execution completed!")
        print("📊 Result:")
        import json
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        print(f"❌ Lambda execution failed: {e}")
        import traceback
        traceback.print_exc()