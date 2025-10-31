"""
AWS Secrets Manager client interface
"""

import json
import logging
import os
from typing import Tuple, List
from abc import ABC, abstractmethod

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError

from exceptions import SecretsManagerError


logger = logging.getLogger(__name__)


class SecretsClientInterface(ABC):
    """
    Interface for AWS Secrets Manager operations
    """
    
    @abstractmethod
    def get_quip_credentials(self) -> Tuple[str, List[str]]:
        """
        Retrieve Quip access token and folder IDs from Secrets Manager
        
        Returns:
            tuple: (access_token, folder_ids_list)
        
        Raises:
            SecretsManagerError: If credentials cannot be retrieved
        """
        pass


class SecretsClient(SecretsClientInterface):
    """
    AWS Secrets Manager client implementation
    """
    
    def __init__(self, secret_name: str, region_name: str = 'us-east-1'):
        """
        Initialize Secrets Manager client
        
        Args:
            secret_name: Name of the secret containing Quip credentials
            region_name: AWS region name
        """
        self.secret_name = secret_name
        self.region_name = region_name
        self._client = None
    
    @property
    def client(self):
        """Lazy initialization of boto3 client"""
        if self._client is None:
            try:
                self._client = boto3.client('secretsmanager', region_name=self.region_name)
            except NoCredentialsError as e:
                logger.error("AWS credentials not found")
                raise SecretsManagerError("AWS credentials not configured") from e
            except Exception as e:
                logger.error("Failed to initialize Secrets Manager client")
                raise SecretsManagerError(f"Failed to initialize Secrets Manager client: {str(e)}") from e
        return self._client
    
    def get_quip_credentials(self) -> Tuple[str, List[str]]:
        """
        Retrieve Quip access token and folder IDs from Secrets Manager or environment variables
        
        For local development, can use environment variables:
        - QUIP_ACCESS_TOKEN: The Quip access token
        - QUIP_FOLDER_IDS: Comma-separated list of folder IDs
        
        Returns:
            tuple: (access_token, folder_ids_list)
        
        Raises:
            SecretsManagerError: If credentials cannot be retrieved
        """
        # Check for local development environment variables first
        env_token = os.environ.get('QUIP_ACCESS_TOKEN')
        env_folders = os.environ.get('QUIP_FOLDER_IDS')
        
        if env_token and env_folders:
            logger.info("Using Quip credentials from environment variables")
            
            # Parse folder IDs from environment variable
            folder_ids = self._parse_folder_ids(env_folders)
            
            logger.info(f"Successfully retrieved credentials from environment for {len(folder_ids)} folders")
            return env_token, folder_ids
        
        # Fall back to Secrets Manager
        try:
            logger.info(f"Retrieving secret: {self.secret_name}")
            
            response = self.client.get_secret_value(SecretId=self.secret_name)
            secret_string = response.get('SecretString')
            
            if not secret_string:
                raise SecretsManagerError("Secret value is empty")
            
            # Parse the JSON secret
            try:
                secret_data = json.loads(secret_string)
            except json.JSONDecodeError as e:
                logger.error("Failed to parse secret JSON")
                raise SecretsManagerError("Secret is not valid JSON") from e
            
            # Extract access token
            access_token = secret_data.get('quip_access_token')
            if not access_token:
                raise SecretsManagerError("Missing 'quip_access_token' in secret")
            
            # Extract and parse folder IDs
            folder_ids_str = secret_data.get('folder_ids')
            if not folder_ids_str:
                raise SecretsManagerError("Missing 'folder_ids' in secret")
            
            # Convert comma-separated folder IDs to list
            folder_ids = self._parse_folder_ids(folder_ids_str)
            
            logger.info(f"Successfully retrieved credentials for {len(folder_ids)} folders")
            return access_token, folder_ids
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            if error_code == 'ResourceNotFoundException':
                logger.error(f"Secret not found: {self.secret_name}")
                raise SecretsManagerError(f"Secret '{self.secret_name}' not found") from e
            elif error_code == 'InvalidRequestException':
                logger.error(f"Invalid request for secret: {self.secret_name}")
                raise SecretsManagerError(f"Invalid request for secret '{self.secret_name}'") from e
            elif error_code == 'InvalidParameterException':
                logger.error(f"Invalid parameter for secret: {self.secret_name}")
                raise SecretsManagerError(f"Invalid parameter for secret '{self.secret_name}'") from e
            elif error_code == 'DecryptionFailureException':
                logger.error("Failed to decrypt secret")
                raise SecretsManagerError("Failed to decrypt secret") from e
            elif error_code == 'InternalServiceErrorException':
                logger.error("Secrets Manager internal service error")
                raise SecretsManagerError("Secrets Manager service error") from e
            elif error_code in ['UnauthorizedOperation', 'AccessDenied']:
                logger.error("Access denied to Secrets Manager")
                raise SecretsManagerError("Access denied to Secrets Manager") from e
            else:
                logger.error(f"Unexpected Secrets Manager error: {error_code} - {error_message}")
                raise SecretsManagerError(f"Secrets Manager error: {error_message}") from e
                
        except BotoCoreError as e:
            logger.error(f"Boto3 core error: {str(e)}")
            raise SecretsManagerError(f"AWS SDK error: {str(e)}") from e
        except SecretsManagerError:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving secret: {str(e)}")
            raise SecretsManagerError(f"Unexpected error: {str(e)}") from e
    
    def _parse_folder_ids(self, folder_ids_str: str) -> List[str]:
        """
        Parse comma-separated folder IDs into a list
        
        Args:
            folder_ids_str: Comma-separated string of folder IDs
            
        Returns:
            List of folder IDs with whitespace stripped
            
        Raises:
            SecretsManagerError: If folder IDs string is invalid
        """
        if not isinstance(folder_ids_str, str):
            raise SecretsManagerError("folder_ids must be a string")
        
        # Split by comma and strip whitespace
        folder_ids = [folder_id.strip() for folder_id in folder_ids_str.split(',')]
        
        # Remove empty strings
        folder_ids = [folder_id for folder_id in folder_ids if folder_id]
        
        if not folder_ids:
            raise SecretsManagerError("No valid folder IDs found in comma-separated string")
        
        # Validate folder IDs (basic validation - should not be empty and should be reasonable length)
        for folder_id in folder_ids:
            if len(folder_id) < 3:  # Minimum reasonable folder ID length
                raise SecretsManagerError(f"Invalid folder ID: '{folder_id}' (too short)")
            if len(folder_id) > 100:  # Maximum reasonable folder ID length
                raise SecretsManagerError(f"Invalid folder ID: '{folder_id}' (too long)")
        
        return folder_ids