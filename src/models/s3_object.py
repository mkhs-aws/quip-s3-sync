"""
Data models for S3 objects
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class S3Object:
    """
    Represents an S3 object with metadata
    """
    key: str
    last_modified: datetime
    size: int
    etag: str
    metadata: Optional[dict] = None
    
    @property
    def quip_thread_id(self) -> Optional[str]:
        """Extract Quip thread ID from S3 object metadata if available"""
        if self.metadata:
            return self.metadata.get('quip_thread_id')
        return None