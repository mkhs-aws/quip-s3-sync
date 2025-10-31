"""
Synchronization engine for Quip-to-S3 operations
"""

import logging
import time
import uuid
from typing import Dict, List, Optional
from abc import ABC, abstractmethod
from datetime import datetime

from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit

from models.sync_result import SyncResult
from models.thread_metadata import ThreadMetadata
from exceptions import QuipAPIError, S3OperationError

# Initialize structured logger and metrics
logger = Logger(child=True)
metrics = Metrics()


class SyncEngineInterface(ABC):
    """
    Interface for synchronization operations
    """
    
    @abstractmethod
    def discover_threads(self, folder_ids: List[str]) -> Dict:
        """
        Recursively discover all threads in folders
        
        Args:
            folder_ids: List of Quip folder IDs
            
        Returns:
            dict: Discovered threads with metadata
        """
        pass
    
    @abstractmethod
    def detect_changes(self, quip_threads: Dict, s3_objects: Dict) -> List[str]:
        """
        Compare timestamps to identify changed threads
        
        Args:
            quip_threads: Quip thread metadata
            s3_objects: S3 object metadata
            
        Returns:
            list: Thread IDs that need synchronization
        """
        pass
    
    @abstractmethod
    def sync_documents(self, changed_thread_ids: List[str]) -> SyncResult:
        """
        Synchronize changed documents to S3
        
        Args:
            changed_thread_ids: List of thread IDs to sync
            
        Returns:
            SyncResult: Summary of synchronization operation
        """
        pass


class SyncEngine(SyncEngineInterface):
    """
    Synchronization engine implementation with thread discovery, change detection, and document synchronization
    """
    
    def __init__(self, quip_client, s3_client, correlation_id: Optional[str] = None):
        """
        Initialize sync engine with clients
        
        Args:
            quip_client: Quip API client
            s3_client: S3 client
            correlation_id: Request correlation ID for tracing
        """
        self.quip_client = quip_client
        self.s3_client = s3_client
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self._discovered_threads = {}  # In-memory storage for discovered threads
        self._s3_objects = {}  # In-memory storage for S3 objects
    
    def discover_threads(self, folder_ids: List[str]) -> Dict:
        """
        Recursively discover all threads in folders and store in memory
        
        Args:
            folder_ids: List of Quip folder IDs
            
        Returns:
            dict: Discovered threads with metadata (stored in memory)
            
        Raises:
            QuipAPIError: If folder discovery fails
        """
        logger.info("Starting thread discovery", extra={
            "correlation_id": self.correlation_id,
            "folder_count": len(folder_ids),
            "operation": "discover_threads"
        })
        start_time = time.time()
        
        try:
            # Use QuipClient's recursive discovery method
            discovered_data = self.quip_client.discover_all_threads(folder_ids)
            
            # Convert to ThreadMetadata objects and store in memory
            self._discovered_threads = {}
            for thread_id, thread_data in discovered_data.items():
                self._discovered_threads[thread_id] = ThreadMetadata(
                    id=thread_data['id'],
                    title=thread_data['title'],
                    link=thread_data['link'],
                    type=thread_data['type'],
                    updated_usec=thread_data['updated_usec'],
                    author_id=thread_data['author_id']
                )
            
            discovery_time = time.time() - start_time
            
            # Log performance metrics
            logger.info("Thread discovery completed", extra={
                "correlation_id": self.correlation_id,
                "operation": "discover_threads",
                "duration_seconds": round(discovery_time, 2),
                "threads_discovered": len(self._discovered_threads),
                "folders_processed": len(folder_ids)
            })
            
            # Record metrics
            metrics.add_metric(name="ThreadDiscoveryDuration", unit=MetricUnit.Seconds, value=discovery_time)
            metrics.add_metric(name="ThreadsDiscovered", unit=MetricUnit.Count, value=len(self._discovered_threads))
            metrics.add_metric(name="FoldersProcessed", unit=MetricUnit.Count, value=len(folder_ids))
            
            return self._discovered_threads
            
        except QuipAPIError as e:
            logger.error("Thread discovery failed", extra={
                "correlation_id": self.correlation_id,
                "operation": "discover_threads",
                "error_type": "QuipAPIError",
                "error_message": str(e),
                "duration_seconds": round(time.time() - start_time, 2)
            })
            metrics.add_metric(name="ThreadDiscoveryErrors", unit=MetricUnit.Count, value=1)
            raise
        except Exception as e:
            logger.error("Unexpected error during thread discovery", extra={
                "correlation_id": self.correlation_id,
                "operation": "discover_threads",
                "error_type": "UnexpectedError",
                "error_message": str(e),
                "duration_seconds": round(time.time() - start_time, 2)
            }, exc_info=True)
            metrics.add_metric(name="ThreadDiscoveryErrors", unit=MetricUnit.Count, value=1)
            raise QuipAPIError(f"Thread discovery failed: {e}")
    
    def detect_changes(self, quip_threads: Dict, s3_objects: Dict) -> List[str]:
        """
        Compare timestamps between Quip threads and S3 objects to identify changed threads
        
        Args:
            quip_threads: Dict of thread_id -> ThreadMetadata
            s3_objects: Dict of object_key -> last_modified_datetime
            
        Returns:
            list: Thread IDs that need synchronization (documents only, spreadsheets skipped)
        """
        logger.info("Starting change detection", extra={
            "correlation_id": self.correlation_id,
            "operation": "detect_changes",
            "quip_threads_count": len(quip_threads),
            "s3_objects_count": len(s3_objects)
        })
        start_time = time.time()
        
        changed_thread_ids = []
        documents_processed = 0
        spreadsheets_skipped = 0
        new_documents = 0
        updated_documents = 0
        unchanged_documents = 0
        
        # Store S3 objects in memory for comparison
        self._s3_objects = s3_objects
        
        for thread_id, thread_metadata in quip_threads.items():
            # Skip spreadsheet threads - only process document threads
            if not thread_metadata.is_document:
                spreadsheets_skipped += 1
                logger.debug("Skipping spreadsheet thread", extra={
                    "correlation_id": self.correlation_id,
                    "thread_id": thread_id,
                    "thread_type": thread_metadata.type
                })
                continue
            
            documents_processed += 1
            
            # Generate the expected S3 object key for this thread
            expected_s3_key = self.s3_client.generate_object_key(
                thread_metadata.link
            )
            
            # Check if object exists in S3
            if expected_s3_key not in s3_objects:
                # New document - needs synchronization
                changed_thread_ids.append(thread_id)
                new_documents += 1
                logger.debug("New document detected", extra={
                    "correlation_id": self.correlation_id,
                    "thread_id": thread_id,
                    "s3_key": expected_s3_key,
                    "change_type": "new"
                })
                continue
            
            # Compare timestamps
            quip_modified = thread_metadata.updated_datetime
            s3_modified = s3_objects[expected_s3_key]
            
            # Convert S3 datetime to UTC if it has timezone info
            if s3_modified.tzinfo is not None:
                s3_modified = s3_modified.replace(tzinfo=None)
            
            # If Quip thread is newer than S3 object, it needs synchronization
            if quip_modified > s3_modified:
                changed_thread_ids.append(thread_id)
                updated_documents += 1
                logger.debug("Updated document detected", extra={
                    "correlation_id": self.correlation_id,
                    "thread_id": thread_id,
                    "s3_key": expected_s3_key,
                    "change_type": "updated",
                    "quip_modified": quip_modified.isoformat(),
                    "s3_modified": s3_modified.isoformat()
                })
            else:
                unchanged_documents += 1
                logger.debug("Document unchanged", extra={
                    "correlation_id": self.correlation_id,
                    "thread_id": thread_id,
                    "s3_key": expected_s3_key,
                    "change_type": "unchanged"
                })
        
        detection_time = time.time() - start_time
        
        # Log comprehensive change detection results
        logger.info("Change detection completed", extra={
            "correlation_id": self.correlation_id,
            "operation": "detect_changes",
            "duration_seconds": round(detection_time, 2),
            "documents_needing_sync": len(changed_thread_ids),
            "new_documents": new_documents,
            "updated_documents": updated_documents,
            "unchanged_documents": unchanged_documents,
            "spreadsheets_skipped": spreadsheets_skipped,
            "total_documents_processed": documents_processed
        })
        
        # Record metrics
        metrics.add_metric(name="ChangeDetectionDuration", unit=MetricUnit.Seconds, value=detection_time)
        metrics.add_metric(name="DocumentsNeedingSync", unit=MetricUnit.Count, value=len(changed_thread_ids))
        metrics.add_metric(name="NewDocuments", unit=MetricUnit.Count, value=new_documents)
        metrics.add_metric(name="UpdatedDocuments", unit=MetricUnit.Count, value=updated_documents)
        metrics.add_metric(name="UnchangedDocuments", unit=MetricUnit.Count, value=unchanged_documents)
        metrics.add_metric(name="SpreadsheetsSkipped", unit=MetricUnit.Count, value=spreadsheets_skipped)
        
        return changed_thread_ids
    
    def sync_documents(self, changed_thread_ids: List[str]) -> SyncResult:
        """
        Synchronize changed documents to S3, processing only document threads with graceful error handling
        
        Args:
            changed_thread_ids: List of thread IDs to sync
            
        Returns:
            SyncResult: Summary of synchronization operation
        """
        logger.info("Starting document synchronization", extra={
            "correlation_id": self.correlation_id,
            "operation": "sync_documents",
            "threads_to_sync": len(changed_thread_ids)
        })
        start_time = time.time()
        
        result = SyncResult()
        result.total_threads_discovered = len(self._discovered_threads)
        
        # Count spreadsheets that were skipped during change detection
        for thread_metadata in self._discovered_threads.values():
            if not thread_metadata.is_document:
                result.spreadsheets_skipped += 1
        
        successful_uploads = 0
        failed_uploads = 0
        quip_api_latencies = []
        s3_upload_latencies = []
        
        # Process each changed thread with graceful error handling
        for i, thread_id in enumerate(changed_thread_ids, 1):
            thread_start_time = time.time()
            
            logger.debug("Processing thread for synchronization", extra={
                "correlation_id": self.correlation_id,
                "thread_id": thread_id,
                "progress": f"{i}/{len(changed_thread_ids)}"
            })
            
            if thread_id not in self._discovered_threads:
                error_msg = f"Thread {thread_id} not found in discovered threads"
                logger.error("Thread not found in discovery results", extra={
                    "correlation_id": self.correlation_id,
                    "thread_id": thread_id,
                    "error_type": "ThreadNotFound"
                })
                result.add_error(error_msg)
                failed_uploads += 1
                continue
            
            thread_metadata = self._discovered_threads[thread_id]
            
            # Double-check that this is a document (should already be filtered)
            if not thread_metadata.is_document:
                logger.warning("Skipping non-document thread in sync", extra={
                    "correlation_id": self.correlation_id,
                    "thread_id": thread_id,
                    "thread_type": thread_metadata.type
                })
                result.spreadsheets_skipped += 1
                continue
            
            result.documents_processed += 1
            
            try:
                # Get thread HTML content from Quip with timing
                quip_start_time = time.time()
                logger.debug("Retrieving HTML content from Quip", extra={
                    "correlation_id": self.correlation_id,
                    "thread_id": thread_id,
                    "operation": "get_thread_html"
                })
                
                html_content = self.quip_client.get_thread_html(thread_id)
                quip_latency = time.time() - quip_start_time
                quip_api_latencies.append(quip_latency)
                
                if not html_content:
                    error_msg = f"No HTML content retrieved for thread {thread_id}"
                    logger.warning("Empty HTML content retrieved", extra={
                        "correlation_id": self.correlation_id,
                        "thread_id": thread_id,
                        "quip_api_latency_seconds": round(quip_latency, 3)
                    })
                    result.add_error(error_msg)
                    failed_uploads += 1
                    continue
                
                # Generate S3 object key using link value for easy reference
                s3_key = self.s3_client.generate_object_key(
                    thread_metadata.link
                )
                
                # Prepare metadata for S3 object
                s3_metadata = {
                    'quip_thread_id': thread_metadata.id,
                    'quip_title': thread_metadata.title,
                    'quip_link': thread_metadata.link,
                    'quip_updated_usec': str(thread_metadata.updated_usec),
                    'quip_updated_datetime': thread_metadata.updated_datetime.isoformat(),
                    'quip_author_id': thread_metadata.author_id,
                    'sync_timestamp': datetime.utcnow().isoformat(),
                    'correlation_id': self.correlation_id
                }
                
                # Upload to S3 with timing
                s3_start_time = time.time()
                logger.debug("Uploading document to S3", extra={
                    "correlation_id": self.correlation_id,
                    "thread_id": thread_id,
                    "s3_key": s3_key,
                    "content_size_bytes": len(html_content.encode('utf-8')),
                    "operation": "s3_upload"
                })
                
                self.s3_client.upload_document(s3_key, html_content, s3_metadata)
                s3_latency = time.time() - s3_start_time
                s3_upload_latencies.append(s3_latency)
                
                result.documents_uploaded += 1
                successful_uploads += 1
                thread_total_time = time.time() - thread_start_time
                
                logger.info("Successfully synchronized document", extra={
                    "correlation_id": self.correlation_id,
                    "thread_id": thread_id,
                    "s3_key": s3_key,
                    "quip_api_latency_seconds": round(quip_latency, 3),
                    "s3_upload_latency_seconds": round(s3_latency, 3),
                    "total_thread_time_seconds": round(thread_total_time, 3),
                    "content_size_bytes": len(html_content.encode('utf-8')),
                    "progress": f"{i}/{len(changed_thread_ids)}"
                })
                
            except QuipAPIError as e:
                error_msg = f"Failed to retrieve content for thread {thread_id}: {e}"
                logger.error("Quip API error during synchronization", extra={
                    "correlation_id": self.correlation_id,
                    "thread_id": thread_id,
                    "error_type": "QuipAPIError",
                    "error_message": str(e),
                    "thread_processing_time_seconds": round(time.time() - thread_start_time, 3)
                })
                result.add_error(error_msg)
                failed_uploads += 1
                # Continue processing other documents despite this failure
                continue
                
            except S3OperationError as e:
                error_msg = f"Failed to upload thread {thread_id} to S3: {e}"
                logger.error("S3 operation error during synchronization", extra={
                    "correlation_id": self.correlation_id,
                    "thread_id": thread_id,
                    "error_type": "S3OperationError",
                    "error_message": str(e),
                    "thread_processing_time_seconds": round(time.time() - thread_start_time, 3)
                })
                result.add_error(error_msg)
                failed_uploads += 1
                # Continue processing other documents despite this failure
                continue
                
            except Exception as e:
                error_msg = f"Unexpected error syncing thread {thread_id}: {e}"
                logger.error("Unexpected error during synchronization", extra={
                    "correlation_id": self.correlation_id,
                    "thread_id": thread_id,
                    "error_type": "UnexpectedError",
                    "error_message": str(e),
                    "thread_processing_time_seconds": round(time.time() - thread_start_time, 3)
                }, exc_info=True)
                result.add_error(error_msg)
                failed_uploads += 1
                # Continue processing other documents despite this failure
                continue
        
        # Calculate unchanged documents
        result.documents_unchanged = result.documents_processed - result.documents_uploaded
        
        # Record execution time
        result.execution_time_seconds = time.time() - start_time
        
        # Calculate performance statistics
        avg_quip_latency = sum(quip_api_latencies) / len(quip_api_latencies) if quip_api_latencies else 0
        avg_s3_latency = sum(s3_upload_latencies) / len(s3_upload_latencies) if s3_upload_latencies else 0
        success_rate = (successful_uploads / len(changed_thread_ids)) * 100 if changed_thread_ids else 100
        
        # Log comprehensive synchronization results
        logger.info("Document synchronization completed", extra={
            "correlation_id": self.correlation_id,
            "operation": "sync_documents",
            "duration_seconds": round(result.execution_time_seconds, 2),
            "documents_uploaded": result.documents_uploaded,
            "documents_unchanged": result.documents_unchanged,
            "spreadsheets_skipped": result.spreadsheets_skipped,
            "successful_uploads": successful_uploads,
            "failed_uploads": failed_uploads,
            "error_count": len(result.errors),
            "success_rate_percent": round(success_rate, 2),
            "avg_quip_api_latency_seconds": round(avg_quip_latency, 3),
            "avg_s3_upload_latency_seconds": round(avg_s3_latency, 3),
            "total_documents_processed": result.documents_processed
        })
        
        # Record comprehensive metrics
        metrics.add_metric(name="DocumentSyncDuration", unit=MetricUnit.Seconds, value=result.execution_time_seconds)
        metrics.add_metric(name="DocumentsUploaded", unit=MetricUnit.Count, value=result.documents_uploaded)
        metrics.add_metric(name="SuccessfulUploads", unit=MetricUnit.Count, value=successful_uploads)
        metrics.add_metric(name="FailedUploads", unit=MetricUnit.Count, value=failed_uploads)
        metrics.add_metric(name="SyncSuccessRate", unit=MetricUnit.Percent, value=success_rate)
        
        if quip_api_latencies:
            metrics.add_metric(name="AvgQuipAPILatency", unit=MetricUnit.Seconds, value=avg_quip_latency)
            metrics.add_metric(name="MaxQuipAPILatency", unit=MetricUnit.Seconds, value=max(quip_api_latencies))
            metrics.add_metric(name="MinQuipAPILatency", unit=MetricUnit.Seconds, value=min(quip_api_latencies))
        
        if s3_upload_latencies:
            metrics.add_metric(name="AvgS3UploadLatency", unit=MetricUnit.Seconds, value=avg_s3_latency)
            metrics.add_metric(name="MaxS3UploadLatency", unit=MetricUnit.Seconds, value=max(s3_upload_latencies))
            metrics.add_metric(name="MinS3UploadLatency", unit=MetricUnit.Seconds, value=min(s3_upload_latencies))
        
        # Clear in-memory data structures after completion
        self._cleanup_memory()
        
        return result
    
    def _cleanup_memory(self) -> None:
        """
        Discard all in-memory data structures after synchronization completion
        """
        logger.debug("Cleaning up in-memory data structures", extra={
            "correlation_id": self.correlation_id,
            "operation": "cleanup_memory",
            "threads_to_clear": len(self._discovered_threads),
            "s3_objects_to_clear": len(self._s3_objects)
        })
        self._discovered_threads.clear()
        self._s3_objects.clear()
        logger.debug("Memory cleanup completed", extra={
            "correlation_id": self.correlation_id,
            "operation": "cleanup_memory"
        })