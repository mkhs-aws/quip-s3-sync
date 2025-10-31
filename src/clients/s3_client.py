"""
AWS S3 client interface
"""

import boto3
import re
import time
import uuid
from typing import Dict, Optional
from datetime import datetime
from abc import ABC, abstractmethod
from botocore.exceptions import ClientError, BotoCoreError

from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit

from exceptions import S3OperationError

# Initialize structured logger and metrics
logger = Logger(child=True)
metrics = Metrics()


class S3ClientInterface(ABC):
    """
    Interface for AWS S3 operations
    """
    
    @abstractmethod
    def list_objects(self) -> Dict[str, datetime]:
        """
        List all objects in the bucket with modification times
        
        Returns:
            dict: Mapping of object keys to last modified timestamps
        """
        pass
    
    @abstractmethod
    def upload_document(self, key: str, content: str, metadata: Dict) -> None:
        """
        Upload document to S3 with metadata
        
        Args:
            key: S3 object key
            content: Document content (HTML)
            metadata: Object metadata
        """
        pass
    
    @abstractmethod
    def generate_object_key(self, link: str) -> str:
        """
        Generate S3 object key from Quip link and title
        
        Args:
            link_value: Quip thread link value
            title: Thread title
            
        Returns:
            str: S3 object key
        """
        pass


class S3Client(S3ClientInterface):
    """
    AWS S3 client implementation with comprehensive logging and metrics
    """
    
    def __init__(self, bucket_name: str, region_name: str = 'us-east-1', correlation_id: Optional[str] = None):
        """
        Initialize S3 client
        
        Args:
            bucket_name: S3 bucket name
            region_name: AWS region name
            correlation_id: Request correlation ID for tracing
        """
        self.bucket_name = bucket_name
        self.region_name = region_name
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self._s3_client = boto3.client('s3', region_name=region_name)
    
    def list_objects(self) -> Dict[str, datetime]:
        """
        List all objects in the bucket with modification times
        Handles pagination for buckets with more than 1000 objects
        
        Returns:
            dict: Mapping of object keys to last modified timestamps
            
        Raises:
            S3OperationError: If S3 operation fails
        """
        logger.info("Starting S3 object listing", extra={
            "correlation_id": self.correlation_id,
            "bucket_name": self.bucket_name,
            "operation": "list_objects"
        })
        start_time = time.time()
        objects = {}
        pages_processed = 0
        
        try:
            # Use paginator to handle buckets with more than 1000 objects
            paginator = self._s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=self.bucket_name)
            
            for page in page_iterator:
                pages_processed += 1
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects[obj['Key']] = obj['LastModified']
                        
            duration = time.time() - start_time
            
            logger.info("S3 object listing completed", extra={
                "correlation_id": self.correlation_id,
                "bucket_name": self.bucket_name,
                "operation": "list_objects",
                "duration_seconds": round(duration, 3),
                "objects_found": len(objects),
                "pages_processed": pages_processed
            })
            
            # Record metrics
            metrics.add_metric(name="S3ListObjectsDuration", unit=MetricUnit.Seconds, value=duration)
            metrics.add_metric(name="S3ObjectsListed", unit=MetricUnit.Count, value=len(objects))
            metrics.add_metric(name="S3ListPagesProcessed", unit=MetricUnit.Count, value=pages_processed)
                        
        except ClientError as e:
            duration = time.time() - start_time
            error_code = e.response['Error']['Code']
            
            logger.error("S3 client error during object listing", extra={
                "correlation_id": self.correlation_id,
                "bucket_name": self.bucket_name,
                "operation": "list_objects",
                "error_code": error_code,
                "error_message": str(e),
                "duration_seconds": round(duration, 3)
            })
            
            metrics.add_metric(name="S3ListObjectsErrors", unit=MetricUnit.Count, value=1)
            
            if error_code == 'NoSuchBucket':
                raise S3OperationError(f"Bucket '{self.bucket_name}' does not exist")
            elif error_code == 'AccessDenied':
                raise S3OperationError(f"Access denied to bucket '{self.bucket_name}'")
            else:
                raise S3OperationError(f"Failed to list objects in bucket '{self.bucket_name}': {str(e)}")
        except BotoCoreError as e:
            duration = time.time() - start_time
            logger.error("AWS service error during object listing", extra={
                "correlation_id": self.correlation_id,
                "bucket_name": self.bucket_name,
                "operation": "list_objects",
                "error_type": "BotoCoreError",
                "error_message": str(e),
                "duration_seconds": round(duration, 3)
            })
            metrics.add_metric(name="S3ListObjectsErrors", unit=MetricUnit.Count, value=1)
            raise S3OperationError(f"AWS service error while listing objects: {str(e)}")
        except Exception as e:
            duration = time.time() - start_time
            logger.error("Unexpected error during object listing", extra={
                "correlation_id": self.correlation_id,
                "bucket_name": self.bucket_name,
                "operation": "list_objects",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "duration_seconds": round(duration, 3)
            }, exc_info=True)
            metrics.add_metric(name="S3ListObjectsErrors", unit=MetricUnit.Count, value=1)
            raise S3OperationError(f"Unexpected error while listing objects: {str(e)}")
            
        return objects
    
    def upload_document(self, key: str, content: str, metadata: Dict) -> None:
        """
        Upload document to S3 with metadata and comprehensive logging
        
        Args:
            key: S3 object key
            content: Document content (HTML)
            metadata: Object metadata including original Quip modification timestamps
            
        Raises:
            S3OperationError: If S3 upload fails
        """
        content_size = len(content.encode('utf-8'))
        
        logger.debug("Starting S3 document upload", extra={
            "correlation_id": self.correlation_id,
            "bucket_name": self.bucket_name,
            "s3_key": key,
            "content_size_bytes": content_size,
            "metadata_keys": list(metadata.keys()),
            "operation": "upload_document"
        })
        start_time = time.time()
        
        try:
            # Convert metadata values to strings as S3 metadata must be strings
            string_metadata = {k: str(v) for k, v in metadata.items()}
            
            self._s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=content.encode('utf-8'),
                ContentType='text/html',
                Metadata=string_metadata
            )
            
            duration = time.time() - start_time
            
            logger.info("S3 document upload successful", extra={
                "correlation_id": self.correlation_id,
                "bucket_name": self.bucket_name,
                "s3_key": key,
                "content_size_bytes": content_size,
                "upload_duration_seconds": round(duration, 3),
                "operation": "upload_document"
            })
            
            # Record successful upload metrics
            metrics.add_metric(name="S3UploadDuration", unit=MetricUnit.Seconds, value=duration)
            metrics.add_metric(name="S3UploadsSuccessful", unit=MetricUnit.Count, value=1)
            metrics.add_metric(name="S3UploadSizeBytes", unit=MetricUnit.Bytes, value=content_size)
            
        except ClientError as e:
            duration = time.time() - start_time
            error_code = e.response['Error']['Code']
            
            logger.error("S3 client error during document upload", extra={
                "correlation_id": self.correlation_id,
                "bucket_name": self.bucket_name,
                "s3_key": key,
                "content_size_bytes": content_size,
                "error_code": error_code,
                "error_message": str(e),
                "upload_duration_seconds": round(duration, 3),
                "operation": "upload_document"
            })
            
            metrics.add_metric(name="S3UploadErrors", unit=MetricUnit.Count, value=1)
            
            if error_code == 'NoSuchBucket':
                raise S3OperationError(f"Bucket '{self.bucket_name}' does not exist")
            elif error_code == 'AccessDenied':
                raise S3OperationError(f"Access denied to bucket '{self.bucket_name}'")
            else:
                raise S3OperationError(f"Failed to upload object '{key}': {str(e)}")
        except BotoCoreError as e:
            duration = time.time() - start_time
            logger.error("AWS service error during document upload", extra={
                "correlation_id": self.correlation_id,
                "bucket_name": self.bucket_name,
                "s3_key": key,
                "content_size_bytes": content_size,
                "error_type": "BotoCoreError",
                "error_message": str(e),
                "upload_duration_seconds": round(duration, 3),
                "operation": "upload_document"
            })
            metrics.add_metric(name="S3UploadErrors", unit=MetricUnit.Count, value=1)
            raise S3OperationError(f"AWS service error while uploading object '{key}': {str(e)}")
        except Exception as e:
            duration = time.time() - start_time
            logger.error("Unexpected error during document upload", extra={
                "correlation_id": self.correlation_id,
                "bucket_name": self.bucket_name,
                "s3_key": key,
                "content_size_bytes": content_size,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "upload_duration_seconds": round(duration, 3),
                "operation": "upload_document"
            }, exc_info=True)
            metrics.add_metric(name="S3UploadErrors", unit=MetricUnit.Count, value=1)
            raise S3OperationError(f"Unexpected error while uploading object '{key}': {str(e)}")
    
    def generate_object_key(self, link: str) -> str:
        """
        Generate S3 object key based on the Quip thread URL (link) without the "https://" as per requirements
        
        Args:
            link_value: Quip thread link (URL for the Quip document from Get Threads V2 API)
            
        Returns:
            str: S3 object key in format: {link_value}_{sanitized_title}.html
        """
        # Remove "https://" or "http://"
        base_link = link.split("//")[1:]
        
        return f"{''.join(base_link)}.html"