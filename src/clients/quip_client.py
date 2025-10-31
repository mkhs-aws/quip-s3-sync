"""
Quip API client interface
"""

import time
import random
import logging
import uuid
from typing import Dict, List, Set, Optional
from abc import ABC, abstractmethod
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit

from exceptions import QuipAPIError

# Initialize structured logger and metrics
logger = Logger(child=True)
metrics = Metrics()


class QuipClientInterface(ABC):
    """
    Interface for Quip API operations
    """
    
    @abstractmethod
    def get_folder_contents(self, folder_id: str) -> Dict:
        """
        Get folder contents using Get a Folder API
        
        Args:
            folder_id: Quip folder ID
            
        Returns:
            dict: Folder contents with threads and subfolders
        """
        pass
    
    @abstractmethod
    def get_threads_metadata(self, thread_ids: List[str]) -> Dict:
        """
        Get thread metadata using Get Threads V2 API
        
        Args:
            thread_ids: List of thread IDs
            
        Returns:
            dict: Thread metadata for each thread ID
        """
        pass
    
    @abstractmethod
    def get_thread_html(self, thread_id: str) -> str:
        """
        Get thread HTML using Get a Thread API
        
        Args:
            thread_id: Quip thread ID
            
        Returns:
            str: HTML representation of the thread
        """
        pass
    
    @abstractmethod
    def discover_all_threads(self, folder_ids: List[str]) -> Dict[str, Dict]:
        """
        Recursively discover all threads in folders and subfolders
        
        Args:
            folder_ids: List of root folder IDs to discover
            
        Returns:
            dict: Mapping of thread_id to thread metadata
        """
        pass


class QuipClient(QuipClientInterface):
    """
    Quip API client implementation with retry logic and recursive folder discovery
    """
    
    def __init__(self, access_token: str, correlation_id: Optional[str] = None):
        """
        Initialize Quip client with access token
        
        Args:
            access_token: Quip personal access token
            correlation_id: Request correlation ID for tracing
        """
        self.access_token = access_token.strip()
        self.base_url = "https://platform.quip-amazon.com"
        self.correlation_id = correlation_id or str(uuid.uuid4())
        
        # Configure session with retry strategy
        self.session = requests.Session()
        
        # Set up retry strategy for transient failures
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update({
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
            'User-Agent': 'QuipS3Sync/1.0'
        })
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, max_retries: int = 3) -> Dict:
        """
        Make HTTP request with exponential backoff retry logic and comprehensive logging
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            max_retries: Maximum number of retry attempts
            
        Returns:
            dict: JSON response data
            
        Raises:
            QuipAPIError: If request fails after all retries
        """
        url = f"{self.base_url}{endpoint}"
        request_start_time = time.time()
        
        for attempt in range(max_retries + 1):
            attempt_start_time = time.time()
            
            try:
                logger.debug("Making Quip API request", extra={
                    "correlation_id": self.correlation_id,
                    "method": method,
                    "endpoint": endpoint,
                    "attempt": attempt + 1,
                    "max_retries": max_retries + 1,
                    "params": params
                })
                
                response = self.session.request(method, url, params=params, timeout=30)
                attempt_duration = time.time() - attempt_start_time
                
                # Handle rate limiting with exponential backoff
                if response.status_code == 429:
                    if attempt < max_retries:
                        # Get retry-after header or use exponential backoff
                        retry_after = int(response.headers.get('Retry-After', 0))
                        if retry_after == 0:
                            # Exponential backoff with jitter
                            delay = (2 ** attempt) + random.uniform(0, 1)
                        else:
                            delay = retry_after
                        
                        logger.warning("Rate limited by Quip API", extra={
                            "correlation_id": self.correlation_id,
                            "endpoint": endpoint,
                            "attempt": attempt + 1,
                            "retry_after_seconds": delay,
                            "attempt_duration_seconds": round(attempt_duration, 3)
                        })
                        
                        metrics.add_metric(name="QuipAPIRateLimits", unit=MetricUnit.Count, value=1)
                        time.sleep(delay)
                        continue
                    else:
                        logger.error("Rate limit exceeded after all retries", extra={
                            "correlation_id": self.correlation_id,
                            "endpoint": endpoint,
                            "max_retries": max_retries,
                            "total_duration_seconds": round(time.time() - request_start_time, 3)
                        })
                        metrics.add_metric(name="QuipAPIRateLimitFailures", unit=MetricUnit.Count, value=1)
                        raise QuipAPIError(f"Rate limit exceeded after {max_retries} retries")
                
                # Check for other HTTP errors
                if response.status_code == 401:
                    logger.error("Quip API authentication failed", extra={
                        "correlation_id": self.correlation_id,
                        "endpoint": endpoint,
                        "status_code": response.status_code
                    })
                    metrics.add_metric(name="QuipAPIAuthErrors", unit=MetricUnit.Count, value=1)
                    raise QuipAPIError("Authentication failed - invalid access token")
                elif response.status_code == 403:
                    logger.error("Quip API access forbidden", extra={
                        "correlation_id": self.correlation_id,
                        "endpoint": endpoint,
                        "status_code": response.status_code
                    })
                    metrics.add_metric(name="QuipAPIPermissionErrors", unit=MetricUnit.Count, value=1)
                    raise QuipAPIError("Access forbidden - insufficient permissions")
                elif response.status_code == 404:
                    logger.error("Quip API resource not found", extra={
                        "correlation_id": self.correlation_id,
                        "endpoint": endpoint,
                        "status_code": response.status_code
                    })
                    metrics.add_metric(name="QuipAPINotFoundErrors", unit=MetricUnit.Count, value=1)
                    raise QuipAPIError(f"Resource not found: {endpoint}")
                elif not response.ok:
                    logger.error("Quip API HTTP error", extra={
                        "correlation_id": self.correlation_id,
                        "endpoint": endpoint,
                        "status_code": response.status_code,
                        "response_text": response.text[:500]  # Limit response text length
                    })
                    metrics.add_metric(name="QuipAPIHTTPErrors", unit=MetricUnit.Count, value=1)
                    raise QuipAPIError(f"HTTP {response.status_code}: {response.text}")
                
                # Successful response
                total_duration = time.time() - request_start_time
                
                logger.debug("Quip API request successful", extra={
                    "correlation_id": self.correlation_id,
                    "endpoint": endpoint,
                    "status_code": response.status_code,
                    "attempt": attempt + 1,
                    "attempt_duration_seconds": round(attempt_duration, 3),
                    "total_duration_seconds": round(total_duration, 3),
                    "response_size_bytes": len(response.content)
                })
                
                # Record successful API call metrics
                metrics.add_metric(name="QuipAPIRequests", unit=MetricUnit.Count, value=1)
                metrics.add_metric(name="QuipAPILatency", unit=MetricUnit.Seconds, value=total_duration)
                
                # Parse JSON response
                try:
                    return response.json()
                except ValueError as e:
                    logger.error("Invalid JSON response from Quip API", extra={
                        "correlation_id": self.correlation_id,
                        "endpoint": endpoint,
                        "error": str(e),
                        "response_text": response.text[:500]
                    })
                    metrics.add_metric(name="QuipAPIJSONErrors", unit=MetricUnit.Count, value=1)
                    raise QuipAPIError(f"Invalid JSON response: {e}")
                    
            except requests.exceptions.Timeout:
                attempt_duration = time.time() - attempt_start_time
                if attempt < max_retries:
                    delay = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning("Quip API request timeout", extra={
                        "correlation_id": self.correlation_id,
                        "endpoint": endpoint,
                        "attempt": attempt + 1,
                        "retry_delay_seconds": delay,
                        "attempt_duration_seconds": round(attempt_duration, 3)
                    })
                    metrics.add_metric(name="QuipAPITimeouts", unit=MetricUnit.Count, value=1)
                    time.sleep(delay)
                    continue
                else:
                    logger.error("Quip API request timeout after all retries", extra={
                        "correlation_id": self.correlation_id,
                        "endpoint": endpoint,
                        "max_retries": max_retries,
                        "total_duration_seconds": round(time.time() - request_start_time, 3)
                    })
                    metrics.add_metric(name="QuipAPITimeoutFailures", unit=MetricUnit.Count, value=1)
                    raise QuipAPIError("Request timeout after all retries")
                    
            except requests.exceptions.ConnectionError:
                attempt_duration = time.time() - attempt_start_time
                if attempt < max_retries:
                    delay = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning("Quip API connection error", extra={
                        "correlation_id": self.correlation_id,
                        "endpoint": endpoint,
                        "attempt": attempt + 1,
                        "retry_delay_seconds": delay,
                        "attempt_duration_seconds": round(attempt_duration, 3)
                    })
                    metrics.add_metric(name="QuipAPIConnectionErrors", unit=MetricUnit.Count, value=1)
                    time.sleep(delay)
                    continue
                else:
                    logger.error("Quip API connection error after all retries", extra={
                        "correlation_id": self.correlation_id,
                        "endpoint": endpoint,
                        "max_retries": max_retries,
                        "total_duration_seconds": round(time.time() - request_start_time, 3)
                    })
                    metrics.add_metric(name="QuipAPIConnectionFailures", unit=MetricUnit.Count, value=1)
                    raise QuipAPIError("Connection error after all retries")
                    
            except requests.exceptions.RequestException as e:
                logger.error("Quip API request exception", extra={
                    "correlation_id": self.correlation_id,
                    "endpoint": endpoint,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "attempt_duration_seconds": round(time.time() - attempt_start_time, 3)
                })
                metrics.add_metric(name="QuipAPIRequestErrors", unit=MetricUnit.Count, value=1)
                raise QuipAPIError(f"Request failed: {e}")
        
        logger.error("Maximum retries exceeded for Quip API request", extra={
            "correlation_id": self.correlation_id,
            "endpoint": endpoint,
            "max_retries": max_retries,
            "total_duration_seconds": round(time.time() - request_start_time, 3)
        })
        metrics.add_metric(name="QuipAPIMaxRetriesExceeded", unit=MetricUnit.Count, value=1)
        raise QuipAPIError("Maximum retries exceeded")
    
    def get_folder_contents(self, folder_id: str) -> Dict:
        """
        Get folder contents using Get a Folder API
        
        Args:
            folder_id: Quip folder ID
            
        Returns:
            dict: Folder contents with threads and subfolders
            
        Raises:
            QuipAPIError: If API request fails
        """
        logger.info(f"Getting contents for folder {folder_id}")

        params = {"include_chats": True}
        
        endpoint = f"/1/folders/{folder_id}"
        response = self._make_request("GET", endpoint, params=params)
        
        logger.debug(f"Retrieved {len(response.get('children', []))} items from folder {folder_id}")
        return response
    
    def get_threads_metadata(self, thread_ids: List[str]) -> Dict:
        """
        Get thread metadata using Get Threads V2 API
        
        Args:
            thread_ids: List of thread IDs (max 100 per request)
            
        Returns:
            dict: Thread metadata for each thread ID
            
        Raises:
            QuipAPIError: If API request fails
        """
        if not thread_ids:
            return {}
        
        logger.info(f"Getting metadata for {len(thread_ids)} threads")
        
        # Quip API supports up to 100 thread IDs per request
        batch_size = 100
        all_metadata = {}
        
        for i in range(0, len(thread_ids), batch_size):
            batch = thread_ids[i:i + batch_size]
            
            params = {
                'ids': ','.join(batch)
            }
            
            endpoint = "/2/threads/"
            response = self._make_request("GET", endpoint, params=params)
            
            # Log sample response for debugging
            if response and isinstance(response, dict):
                sample_key = next(iter(response.keys())) if response else None
                if sample_key:
                    sample_thread = response[sample_key]
                    logger.debug(f"Sample thread metadata: {sample_thread}", extra={
                        "correlation_id": self.correlation_id,
                        "sample_thread_id": sample_key,
                        "metadata_keys": list(sample_thread.keys()) if isinstance(sample_thread, dict) else "not_dict"
                    })
            
            # Merge batch results
            if isinstance(response, dict):
                all_metadata.update(response)
            
            logger.debug(f"Retrieved metadata for batch of {len(batch)} threads")
        
        logger.info(f"Retrieved metadata for {len(all_metadata)} threads total")
        return all_metadata
    
    def get_thread_html(self, thread_id: str) -> str:
        """
        Get thread HTML using Get a Thread API
        
        Args:
            thread_id: Quip thread ID
            
        Returns:
            str: HTML representation of the thread
            
        Raises:
            QuipAPIError: If API request fails
        """
        logger.info(f"Getting HTML content for thread {thread_id}")
        
        endpoint = f"/1/threads/{thread_id}"
        response = self._make_request("GET", endpoint)
        
        # Extract HTML content from response
        html_content = response.get('html', '')
        if not html_content:
            logger.warning(f"No HTML content found for thread {thread_id}")
        
        return html_content
    
    def discover_all_threads(self, folder_ids: List[str]) -> Dict[str, Dict]:
        """
        Recursively discover all threads in folders and subfolders
        
        Args:
            folder_ids: List of root folder IDs to discover
            
        Returns:
            dict: Mapping of thread_id to thread metadata from folder discovery
            
        Raises:
            QuipAPIError: If folder discovery fails
        """
        logger.info(f"Starting recursive discovery for {len(folder_ids)} root folders")
        
        discovered_threads = {}
        visited_folders: Set[str] = set()
        folders_to_process = list(folder_ids)
        
        while folders_to_process:
            folder_id = folders_to_process.pop(0)
            
            # Skip if already processed
            if folder_id in visited_folders:
                continue
                
            visited_folders.add(folder_id)
            
            try:
                folder_contents = self.get_folder_contents(folder_id)
                children = folder_contents.get('children', [])
                
                logger.debug(f"Folder {folder_id} contains {len(children)} children")
                
                # Log a sample of the raw response structure for debugging
                if children and len(children) > 0:
                    sample_child = children[0]
                    logger.debug(f"Sample child structure: {sample_child}")
                
                valid_children = 0
                for child in children:
                    # Skip null/empty children
                    if not child or not isinstance(child, dict):
                        continue
                    
                    # Handle different API response formats
                    # The API returns either:
                    # 1. Full objects with id, type, title, etc. (for folders)
                    # 2. Simple objects with just thread_id (for threads)
                    
                    child_id = child.get('id') or child.get('thread_id')
                    child_type = child.get('type')
                    child_title = child.get('title', 'No Title')
                    
                    # Skip children with missing essential fields
                    if not child_id:
                        logger.debug(f"Skipping child with missing id/thread_id: {child}")
                        continue
                    
                    valid_children += 1
                    
                    # If we have a thread_id but no type, assume it's a thread/document
                    if child.get('thread_id') and not child_type:
                        child_type = 'THREAD'  # Default to thread type for thread_id entries
                        logger.debug(f"Processing thread: id={child_id}, type={child_type} (inferred)")
                    else:
                        logger.debug(f"Processing child: id={child_id}, type={child_type}, title={child_title}")
                    
                    if child_type == 'folder':
                        # Add subfolder to processing queue
                        if child_id not in visited_folders:
                            folders_to_process.append(child_id)
                            logger.debug(f"Added subfolder {child_id} to discovery queue")
                    
                    elif child_type in ['DOCUMENT', 'SPREADSHEET', 'THREAD'] or child.get('thread_id'):
                        # Store thread metadata from folder listing
                        # Accept items with thread_id even if type is missing
                        discovered_threads[child_id] = {
                            'id': child_id,
                            'title': child_title,
                            'type': child_type or 'THREAD',
                            'updated_usec': child.get('updated_usec', 0),
                            'author_id': child.get('author_id', ''),
                            'link': child.get('link', ''),
                            'parent_folder_id': folder_id
                        }
                        logger.debug(f"Discovered {child_type or 'THREAD'} thread: {child_id} - {child_title}")
                    
                    else:
                        logger.debug(f"Skipping child with unknown type: {child_type} (id={child_id}, title={child_title})")
                
                logger.debug(f"Folder {folder_id}: processed {valid_children} valid children out of {len(children)} total")
                
            except QuipAPIError as e:
                logger.error(f"Failed to process folder {folder_id}: {e}")
                # Continue with other folders rather than failing completely
                continue
        
        logger.info(f"Discovery complete: found {len(discovered_threads)} threads in {len(visited_folders)} folders")
        
        # Get full metadata for all discovered threads using Get Threads V2 API
        if discovered_threads:
            logger.info(f"Fetching full metadata for {len(discovered_threads)} threads")
            thread_ids = list(discovered_threads.keys())
            
            try:
                full_metadata = self.get_threads_metadata(thread_ids)
                
                # Update discovered threads with full metadata
                enriched_count = 0
                for thread_id, metadata in full_metadata.items():
                    if thread_id in discovered_threads:
                        original_title = discovered_threads[thread_id].get('title', 'No Title')
                        new_title = metadata["thread"].get('title', 'Untitled Document')
                        
                        logger.debug(f"Enriching thread {thread_id}: '{original_title}' -> '{new_title}'", extra={
                            "correlation_id": self.correlation_id,
                            "thread_id": thread_id,
                            "original_title": original_title,
                            "new_title": new_title,
                            "metadata_keys": list(metadata["thread"].keys())
                        })
                        
                        # Update with full metadata from Get Threads V2 API
                        discovered_threads[thread_id].update({
                            'title': new_title,
                            'link': metadata["thread"].get('link', ''),
                            'type': metadata["thread"].get('type', 'THREAD'),
                            'updated_usec': metadata["thread"].get('updated_usec', 0),
                            'author_id': metadata["thread"].get('author_id', '')
                        })
                        enriched_count += 1
                        
                logger.info(f"Successfully enriched {enriched_count} threads with full metadata")
                
            except Exception as e:
                logger.warning(f"Failed to fetch full metadata for threads: {e}")
                # Continue with basic metadata if full metadata fetch fails
        
        return discovered_threads