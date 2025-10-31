"""
Custom exceptions for Quip-S3 sync system
"""


class QuipSyncError(Exception):
    """Base exception for sync operations"""
    pass


class QuipAPIError(QuipSyncError):
    """Quip API communication errors"""
    pass


class S3OperationError(QuipSyncError):
    """S3 operation errors"""
    pass


class SecretsManagerError(QuipSyncError):
    """Secrets Manager access errors"""
    pass


class ConfigurationError(QuipSyncError):
    """Configuration and setup errors"""
    pass