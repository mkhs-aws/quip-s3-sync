"""
Data models for Quip thread metadata
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ThreadMetadata:
    """
    Represents metadata for a Quip thread
    """
    id: str
    title: str
    link: str
    type: str  # 'DOCUMENT' or 'SPREADSHEET'
    updated_usec: int
    author_id: str
    
    @property
    def updated_datetime(self) -> datetime:
        """Convert microseconds to datetime"""
        return datetime.fromtimestamp(self.updated_usec / 1_000_000)
    
    @property
    def is_document(self) -> bool:
        """Check if thread is a document (not spreadsheet)"""
        # Accept 'DOCUMENT' and 'THREAD' as document types
        # Only 'SPREADSHEET' is considered non-document
        return self.type in ['DOCUMENT', 'THREAD']
    
    @property
    def link_value(self) -> str:
        """Extract link value from full link URL"""
        # Link format: https://company.quip.com/linkvalue
        return self.link.split('/')[-1] if self.link else self.id