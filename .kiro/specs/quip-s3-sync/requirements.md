# Requirements Document

## Introduction

This document specifies the requirements for a Quip-to-S3 synchronization system that automatically synchronizes documents from nominated Quip folders to an AWS S3 bucket. The system will be deployed as a serverless application using AWS Lambda and EventBridge, running daily to detect and sync updated documents while maintaining security through AWS Secrets Manager.

## Glossary

- **Quip_Sync_System**: The complete serverless application that synchronizes Quip documents to S3
- **Lambda_Function**: The AWS Lambda function that executes the synchronization logic
- **EventBridge_Rule**: The AWS EventBridge rule that triggers the Lambda function daily
- **S3_Bucket**: The AWS S3 bucket that stores synchronized Quip documents
- **Secrets_Manager**: AWS service that securely stores the Quip personal access token
- **CDK_Template**: AWS Cloud Development Kit template for infrastructure deployment
- **Quip_Folder**: A nominated folder in Quip containing documents to be synchronized
- **Thread**: A Quip document or spreadsheet within a folder
- **Document_Thread**: A Quip thread that contains document content (not spreadsheet)
- **HTML_Representation**: The HTML format of a Quip document retrieved via API
- **Link_Value**: The unique link identifier returned by the Get Threads V2 API for each thread
- **Secret_Name**: The configurable name of the AWS Secrets Manager secret containing Quip credentials

## Requirements

### Requirement 1

**User Story:** As a system administrator, I want the system to discover all documents in nominated Quip folders, so that I can ensure comprehensive synchronization coverage.

#### Acceptance Criteria

1. THE Quip_Sync_System SHALL use the Get a Folder API to retrieve the list of subfolders and threads in each nominated Quip_Folder
2. THE Quip_Sync_System SHALL process all subfolders recursively to discover nested content
3. THE Quip_Sync_System SHALL identify all threads within the discovered folder structure
4. THE Quip_Sync_System SHALL store the complete inventory as a Python Dict in memory and discard it upon completion of synchronization

### Requirement 2

**User Story:** As a system administrator, I want the system to retrieve metadata for all discovered documents, so that I can determine which documents need synchronization.

#### Acceptance Criteria

1. THE Quip_Sync_System SHALL use the Get Threads V2 API to retrieve metadata for each thread identified in the folder discovery process
2. THE Quip_Sync_System SHALL extract the last modified timestamp from each thread's metadata
3. THE Quip_Sync_System SHALL identify the thread type to distinguish between documents and spreadsheets
4. THE Quip_Sync_System SHALL store thread metadata in memory for comparison operations

### Requirement 3

**User Story:** As a system administrator, I want the system to inventory existing S3 objects, so that I can compare them against Quip documents for synchronization decisions.

#### Acceptance Criteria

1. THE Quip_Sync_System SHALL use the list_objects_v2 Boto3 function to retrieve all objects in the S3_Bucket
2. THE Quip_Sync_System SHALL extract the last modified timestamp from each S3 object's metadata
3. THE Quip_Sync_System SHALL create a mapping between S3 object keys and their modification timestamps
4. THE Quip_Sync_System SHALL handle pagination when the S3_Bucket contains more than 1000 objects

### Requirement 4

**User Story:** As a system administrator, I want the system to identify outdated documents, so that only changed content is synchronized to minimize processing time and costs.

#### Acceptance Criteria

1. THE Quip_Sync_System SHALL compare the last modified timestamp of each Quip thread against the corresponding S3 object timestamp
2. WHEN a Quip thread has no corresponding S3 object, THE Quip_Sync_System SHALL mark the thread as requiring synchronization
3. WHEN a Quip thread's last modified timestamp is newer than the corresponding S3 object timestamp, THE Quip_Sync_System SHALL mark the thread as requiring synchronization
4. THE Quip_Sync_System SHALL create a list of threads requiring synchronization based on the comparison results

### Requirement 5

**User Story:** As a system administrator, I want the system to retrieve and store updated document content, so that the S3 bucket contains the latest versions of all documents.

#### Acceptance Criteria

1. WHEN a Document_Thread requires synchronization, THE Quip_Sync_System SHALL use the Get a Thread Quip API to retrieve the HTML_Representation
2. WHEN a thread is identified as a spreadsheet, THE Quip_Sync_System SHALL skip the thread without processing
3. THE Quip_Sync_System SHALL upload the HTML_Representation to the S3_Bucket using an object key that incorporates the link value returned by the Get Threads V2 API
4. THE Quip_Sync_System SHALL set appropriate metadata on the S3 object including the original Quip modification timestamp

### Requirement 6

**User Story:** As a security administrator, I want the Quip access token and folder configuration to be stored securely, so that sensitive credentials and configuration are protected according to security best practices.

#### Acceptance Criteria

1. THE Quip_Sync_System SHALL retrieve the Quip personal access token from Secrets_Manager
2. THE Quip_Sync_System SHALL retrieve the comma-separated list of Quip folder IDs from Secrets_Manager
3. THE Lambda_Function SHALL have appropriate IAM permissions to read from Secrets_Manager
4. THE Quip_Sync_System SHALL handle authentication failures gracefully when the token is invalid or expired
5. THE Quip_Sync_System SHALL not log or expose the access token or folder IDs in any system outputs

### Requirement 11

**User Story:** As a system administrator, I want to specify a custom name during deployment that will be used for the CloudFormation stack name, S3 bucket, and secret, so that I can deploy multiple knowledge bases with different names and maintain consistent naming across all resources.

#### Acceptance Criteria

1. THE CDK_Template SHALL prompt the user for a custom name during deployment
2. THE CDK_Template SHALL create the CloudFormation stack name using the format `QuipSyncStack-<custom-name>`
3. THE CDK_Template SHALL create the S3_Bucket name by combining the AWS account ID and the user-provided name in the format `<AWS-Account-ID>-<custom-name>`
4. THE CDK_Template SHALL create the Secret_Name by combining the AWS account ID and the user-provided name in the format `<AWS-Account-ID>-<custom-name>`
5. THE Lambda_Function SHALL receive both the S3_Bucket name and Secret_Name through environment variables
6. THE CDK_Template SHALL validate that the user-provided name follows AWS naming conventions for both S3 and Secrets Manager

### Requirement 7

**User Story:** As a system administrator, I want the synchronization to run automatically each day, so that documents are kept up-to-date without manual intervention.

#### Acceptance Criteria

1. THE EventBridge_Rule SHALL trigger the Lambda_Function daily at midnight Sydney time
2. THE EventBridge_Rule SHALL use a cron expression that accounts for Sydney timezone (UTC+10/UTC+11)
3. THE EventBridge_Rule SHALL have appropriate permissions to invoke the Lambda_Function
4. THE Lambda_Function SHALL execute the complete synchronization process when triggered by the EventBridge_Rule

### Requirement 8

**User Story:** As a DevOps engineer, I want all infrastructure to be defined as code, so that the system can be deployed consistently and maintained efficiently.

#### Acceptance Criteria

1. THE CDK_Template SHALL define the Lambda_Function with appropriate runtime and configuration
2. THE CDK_Template SHALL define the S3_Bucket with the specified bucket policy
3. THE CDK_Template SHALL define the EventBridge_Rule with the correct schedule and target configuration
4. THE CDK_Template SHALL define all necessary IAM roles and policies for system operation

### Requirement 9

**User Story:** As a data analyst, I want the S3 bucket to be accessible by Quick Suite, so that I can create reports and dashboards from the synchronized documents.

#### Acceptance Criteria

1. THE S3_Bucket SHALL have a bucket policy that allows the specified Quick Suite service role to access objects
2. THE bucket policy SHALL grant GetObject, ListBucket, GetBucketLocation, GetObjectVersion, and ListBucketVersions permissions
3. THE bucket policy SHALL include the specified condition for QuickSightDataSourceCreatorPrincipalId and QuickSightNamespace
4. THE CDK_Template SHALL apply the bucket policy during S3_Bucket creation

### Requirement 10

**User Story:** As a system architect, I want the system to operate without persistent state, so that it can scale efficiently and avoid state management complexity.

#### Acceptance Criteria

1. THE Quip_Sync_System SHALL operate as a stateless application
2. THE Quip_Sync_System SHALL not persist any data between synchronization runs
3. THE Quip_Sync_System SHALL store all temporary data structures in memory during execution
4. THE Quip_Sync_System SHALL discard all in-memory data upon completion of each synchronization run