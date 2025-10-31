"""
Data models for synchronization results
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class SyncResult:
    """
    Represents the result of a synchronization operation
    """
    total_threads_discovered: int = 0
    documents_processed: int = 0
    spreadsheets_skipped: int = 0
    documents_uploaded: int = 0
    documents_unchanged: int = 0
    errors: List[str] = field(default_factory=list)
    execution_time_seconds: float = 0.0
    
    def add_error(self, error: str) -> None:
        """Add an error to the result"""
        self.errors.append(error)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        if self.documents_processed == 0:
            return 100.0
        return (self.documents_uploaded / self.documents_processed) * 100.0
    
    @property
    def has_errors(self) -> bool:
        """Check if there were any errors during sync"""
        return len(self.errors) > 0