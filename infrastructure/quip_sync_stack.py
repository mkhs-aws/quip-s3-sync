"""
CDK stack for Quip-to-S3 synchronization system
"""

from typing import Optional, Dict
from aws_cdk import (
    Stack,
    Duration,
    CfnParameter,
    CfnCondition,
    Fn,
    Tags,
    BundlingOptions,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
    aws_sns as sns,
)
from constructs import Construct
import json


class QuipSyncStack(Stack):
    """
    CDK stack for Quip-S3 synchronization infrastructure
    """
    
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        quicksight_principal_id: Optional[str] = None,
        quicksight_namespace: str = "default",
        service_role_arn: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Initialize the Quip Sync stack
        
        Args:
            scope: CDK scope
            construct_id: Stack identifier
            quicksight_principal_id: QuickSight principal ID for S3 access
            quicksight_namespace: QuickSight namespace
            service_role_arn: QuickSight service role ARN
            **kwargs: Additional stack arguments
        """
        super().__init__(scope, construct_id, **kwargs)
        
        # Create CDK parameters for configurable Quick Suite access
        self.quicksight_principal_param = CfnParameter(
            self, "quicksightPrincipalId",
            type="String",
            description="QuickSight principal ID for S3 bucket access",
            default=quicksight_principal_id or ""
        )
        
        self.quicksight_namespace_param = CfnParameter(
            self, "quicksightNamespace", 
            type="String",
            description="QuickSight namespace",
            default=quicksight_namespace
        )
        
        self.service_role_param = CfnParameter(
            self, "serviceRoleArn",
            type="String", 
            description="QuickSight service role ARN for S3 access",
            default=service_role_arn or ""
        )
        
        # Create S3 bucket with dynamic name format: <AWS Account ID>-quip-sync
        self.bucket = self._create_s3_bucket()
        
        # Create Secrets Manager secret for Quip credentials
        self.secret = self._create_secrets_manager_secret()
        
        # Create Lambda function with specified configuration
        self.lambda_function = self._create_lambda_function()
        
        # Create EventBridge rule for daily execution at midnight Sydney time
        self.event_rule = self._create_eventbridge_rule()
        
        # Create CloudWatch alarms for monitoring
        self.alarms = self._create_cloudwatch_alarms()
        
    def _create_s3_bucket(self) -> s3.Bucket:
        """
        Create S3 bucket with dynamic name and QuickSight access policy
        
        Returns:
            s3.Bucket: The created S3 bucket
        """
        bucket_name = f"{self.account}-quip-sync"
        
        bucket = s3.Bucket(
            self, "QuipSyncBucket",
            bucket_name=bucket_name,
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL
        )
        
        # Create bucket policy for QuickSight access if parameters are provided
        self._create_bucket_policy(bucket)
        
        # Add tags for resource identification and security
        Tags.of(bucket).add("Purpose", "QuipSync")
        Tags.of(bucket).add("Application", "QuipS3Sync")
        Tags.of(bucket).add("Environment", "Production")
        Tags.of(bucket).add("DataClassification", "Internal")
        
        return bucket
    
    def _create_bucket_policy(self, bucket: s3.Bucket) -> None:
        """
        Create S3 bucket policy for QuickSight access
        
        Args:
            bucket: The S3 bucket to apply the policy to
        """
        # Only create bucket policy if QuickSight parameters are provided
        # Use CDK conditions to handle optional parameters
        bucket_policy = s3.BucketPolicy(
            self, "QuipSyncBucketPolicy",
            bucket=bucket,
            document=iam.PolicyDocument(
                statements=[
                    iam.PolicyStatement(
                        sid="AllowQuickSuite",
                        effect=iam.Effect.ALLOW,
                        principals=[
                            iam.ArnPrincipal(self.service_role_param.value_as_string)
                        ],
                        actions=[
                            "s3:GetObject",
                            "s3:ListBucket",
                            "s3:GetBucketLocation",
                            "s3:GetObjectVersion",
                            "s3:ListBucketVersions"
                        ],
                        resources=[
                            bucket.bucket_arn,
                            f"{bucket.bucket_arn}/*"
                        ],
                        conditions={
                            "StringEquals": {
                                "aws:PrincipalTag/QuickSightDataSourceCreatorPrincipalId": self.quicksight_principal_param.value_as_string,
                                "aws:PrincipalTag/QuickSightNamespace": self.quicksight_namespace_param.value_as_string
                            }
                        }
                    )
                ]
            )
        )
        
        # Add conditional creation - only create policy if service role ARN is provided
        # Create condition to check if service role ARN is provided
        has_service_role = CfnCondition(
            self, "HasServiceRole",
            expression=Fn.condition_not(
                Fn.condition_equals(self.service_role_param.value_as_string, "")
            )
        )
        
        # Apply condition to bucket policy
        bucket_policy.node.default_child.cfn_options.condition = has_service_role
        
        # Add tags for resource identification
        Tags.of(bucket_policy).add("Purpose", "QuipSync")
        Tags.of(bucket_policy).add("Application", "QuipS3Sync")
        Tags.of(bucket_policy).add("Environment", "Production")
    
    def _create_secrets_manager_secret(self) -> secretsmanager.Secret:
        """
        Create Secrets Manager secret for Quip credentials
        
        Returns:
            secretsmanager.Secret: The created secret
        """
        secret = secretsmanager.Secret(
            self, "QuipCredentials",
            secret_name="quip-sync-credentials",
            description="Quip access token and folder IDs for synchronization",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"quip_access_token": "", "folder_ids": ""}',
                generate_string_key="placeholder",
                exclude_characters=" %+~`#$&*()|[]{}:;<>?!'/\"\\@"
            )
        )
        
        # Add tags for IAM policy conditions and resource identification
        Tags.of(secret).add("Purpose", "QuipSync")
        Tags.of(secret).add("Application", "QuipS3Sync")
        Tags.of(secret).add("Environment", "Production")
        
        return secret
    
    def _create_lambda_function(self) -> _lambda.Function:
        """
        Create Lambda function with Python 3.13 runtime and specified configuration
        
        Returns:
            _lambda.Function: The created Lambda function
        """
        # Create Lambda execution role with least-privilege permissions
        # This role implements the principle of least privilege by:
        # 1. Granting access only to the specific Secrets Manager secret containing Quip credentials
        # 2. Limiting S3 permissions to the designated sync bucket only
        # 3. Restricting CloudWatch Logs access to the Lambda function's log group
        # 4. Using separate policy documents for different service permissions for better auditability
        lambda_role = iam.Role(
            self, "QuipSyncLambdaRole",
            role_name="quip-sync-lambda-execution-role",
            description="Execution role for Quip-S3 synchronization Lambda function",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                "QuipSyncSecretsManagerPolicy": iam.PolicyDocument(
                    statements=[
                        # Secrets Manager permissions - least privilege access to specific secret
                        iam.PolicyStatement(
                            sid="AllowGetQuipCredentials",
                            effect=iam.Effect.ALLOW,
                            actions=["secretsmanager:GetSecretValue"],
                            resources=[self.secret.secret_arn]
                        )
                    ]
                ),
                "QuipSyncS3Policy": iam.PolicyDocument(
                    statements=[
                        # S3 permissions - least privilege access to specific bucket
                        iam.PolicyStatement(
                            sid="AllowS3BucketOperations",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:ListBucket",
                                "s3:GetBucketLocation"
                            ],
                            resources=[self.bucket.bucket_arn]
                        ),
                        iam.PolicyStatement(
                            sid="AllowS3ObjectOperations", 
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:GetObject",
                                "s3:PutObject",
                                "s3:PutObjectMetadata",
                                "s3:PutObjectTagging"
                            ],
                            resources=[f"{self.bucket.bucket_arn}/*"]
                        )
                    ]
                ),
                "QuipSyncCloudWatchLogsPolicy": iam.PolicyDocument(
                    statements=[
                        # CloudWatch Logs permissions - scoped to specific log group
                        iam.PolicyStatement(
                            sid="AllowCloudWatchLogsOperations",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream", 
                                "logs:PutLogEvents",
                                "logs:DescribeLogGroups",
                                "logs:DescribeLogStreams"
                            ],
                            resources=[
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lambda/quip-sync-function",
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lambda/quip-sync-function:*"
                            ]
                        )
                    ]
                )
            }
        )
        
        # Create CloudWatch log group
        log_group = logs.LogGroup(
            self, "QuipSyncLogGroup",
            log_group_name="/aws/lambda/quip-sync-function",
            retention=logs.RetentionDays.ONE_MONTH
        )
        
        # Create Lambda function
        lambda_function = _lambda.Function(
            self, "QuipSyncFunction",
            function_name="quip-sync-function",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset(
                "src",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_13.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output"
                    ]
                )
            ),
            memory_size=1024,
            timeout=Duration.minutes(15),
            role=lambda_role,
            environment={
                "S3_BUCKET_NAME": self.bucket.bucket_name,
                "SECRET_NAME": self.secret.secret_name,
                "LOG_LEVEL": "INFO"
            },
            log_group=log_group
        )
        
        # Add tags for resource identification and security
        Tags.of(lambda_function).add("Purpose", "QuipSync")
        Tags.of(lambda_function).add("Application", "QuipS3Sync")
        Tags.of(lambda_function).add("Environment", "Production")
        Tags.of(lambda_role).add("Purpose", "QuipSync")
        Tags.of(lambda_role).add("Application", "QuipS3Sync")
        Tags.of(lambda_role).add("Environment", "Production")
        
        return lambda_function
    
    def _create_eventbridge_rule(self) -> events.Rule:
        """
        Create EventBridge rule for daily execution at midnight Sydney time
        
        Returns:
            events.Rule: The created EventBridge rule
        """
        # Cron expression for midnight Sydney time (UTC+10/UTC+11)
        # Using 0 14 * * ? * (2 PM UTC = midnight Sydney time during standard time)
        # Note: This doesn't account for daylight saving time transitions
        event_rule = events.Rule(
            self, "QuipSyncSchedule",
            rule_name="quip-sync-daily-schedule",
            description="Daily trigger for Quip-S3 synchronization at midnight Sydney time",
            schedule=events.Schedule.cron(
                minute="0",
                hour="14",  # 2 PM UTC = midnight Sydney time (UTC+10)
                day="*",
                month="*",
                year="*"
            ),
            enabled=True
        )
        
        # Add Lambda function as target
        event_rule.add_target(
            targets.LambdaFunction(
                self.lambda_function,
                retry_attempts=2,
                max_event_age=Duration.hours(2)
            )
        )
        
        # Grant EventBridge permission to invoke Lambda
        self.lambda_function.add_permission(
            "AllowEventBridgeInvoke",
            principal=iam.ServicePrincipal("events.amazonaws.com"),
            source_arn=event_rule.rule_arn
        )
        
        return event_rule
    
    def _create_cloudwatch_alarms(self) -> Dict[str, cloudwatch.Alarm]:
        """
        Create CloudWatch alarms for Lambda function failures and execution timeouts
        
        Returns:
            dict: Dictionary of created CloudWatch alarms
        """
        alarms = {}
        
        # Create SNS topic for alarm notifications (optional)
        alarm_topic = sns.Topic(
            self, "QuipSyncAlarmTopic",
            topic_name="quip-sync-alarms",
            display_name="Quip S3 Sync Alarms"
        )
        
        # Lambda function error alarm
        alarms['lambda_errors'] = cloudwatch.Alarm(
            self, "QuipSyncLambdaErrorAlarm",
            alarm_name="quip-sync-lambda-errors",
            alarm_description="Alert when Quip S3 sync Lambda function encounters errors",
            metric=self.lambda_function.metric_errors(
                period=Duration.minutes(5),
                statistic="Sum"
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        # Lambda function timeout alarm
        alarms['lambda_duration'] = cloudwatch.Alarm(
            self, "QuipSyncLambdaDurationAlarm",
            alarm_name="quip-sync-lambda-duration",
            alarm_description="Alert when Quip S3 sync Lambda function approaches timeout",
            metric=self.lambda_function.metric_duration(
                period=Duration.minutes(5),
                statistic="Maximum"
            ),
            threshold=Duration.minutes(13).to_milliseconds(),  # Alert at 13 minutes (2 min before 15 min timeout)
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        # Lambda function throttle alarm
        alarms['lambda_throttles'] = cloudwatch.Alarm(
            self, "QuipSyncLambdaThrottleAlarm",
            alarm_name="quip-sync-lambda-throttles",
            alarm_description="Alert when Quip S3 sync Lambda function is throttled",
            metric=self.lambda_function.metric_throttles(
                period=Duration.minutes(5),
                statistic="Sum"
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        # Custom metric alarms for application-specific metrics
        
        # Quip API error rate alarm
        alarms['quip_api_errors'] = cloudwatch.Alarm(
            self, "QuipSyncQuipAPIErrorAlarm",
            alarm_name="quip-sync-quip-api-errors",
            alarm_description="Alert when Quip API error rate is high",
            metric=cloudwatch.Metric(
                namespace="AWS/Lambda",
                metric_name="QuipAPIErrors",
                dimensions_map={
                    "FunctionName": self.lambda_function.function_name
                },
                period=Duration.minutes(5),
                statistic="Sum"
            ),
            threshold=5,  # Alert if more than 5 Quip API errors in 5 minutes
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        # S3 upload failure alarm
        alarms['s3_upload_errors'] = cloudwatch.Alarm(
            self, "QuipSyncS3UploadErrorAlarm",
            alarm_name="quip-sync-s3-upload-errors",
            alarm_description="Alert when S3 upload error rate is high",
            metric=cloudwatch.Metric(
                namespace="AWS/Lambda",
                metric_name="S3UploadErrors",
                dimensions_map={
                    "FunctionName": self.lambda_function.function_name
                },
                period=Duration.minutes(5),
                statistic="Sum"
            ),
            threshold=3,  # Alert if more than 3 S3 upload errors in 5 minutes
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        # Sync success rate alarm (alert if success rate drops below 90%)
        alarms['sync_success_rate'] = cloudwatch.Alarm(
            self, "QuipSyncSuccessRateAlarm",
            alarm_name="quip-sync-success-rate-low",
            alarm_description="Alert when sync success rate drops below 90%",
            metric=cloudwatch.Metric(
                namespace="AWS/Lambda",
                metric_name="SyncSuccessRate",
                dimensions_map={
                    "FunctionName": self.lambda_function.function_name
                },
                period=Duration.minutes(15),
                statistic="Average"
            ),
            threshold=90,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        # High API latency alarm
        alarms['high_api_latency'] = cloudwatch.Alarm(
            self, "QuipSyncHighAPILatencyAlarm",
            alarm_name="quip-sync-high-api-latency",
            alarm_description="Alert when average Quip API latency is high",
            metric=cloudwatch.Metric(
                namespace="AWS/Lambda",
                metric_name="AvgQuipAPILatency",
                dimensions_map={
                    "FunctionName": self.lambda_function.function_name
                },
                period=Duration.minutes(10),
                statistic="Average"
            ),
            threshold=10,  # Alert if average API latency exceeds 10 seconds
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        # Add SNS topic subscription for notifications (commented out - can be enabled as needed)
        # for alarm_name, alarm in alarms.items():
        #     alarm.add_alarm_action(
        #         cloudwatch_actions.SnsAction(alarm_topic)
        #     )
        
        # Add tags to alarms
        for alarm_name, alarm in alarms.items():
            Tags.of(alarm).add("Purpose", "QuipSync")
            Tags.of(alarm).add("Application", "QuipS3Sync")
            Tags.of(alarm).add("Environment", "Production")
            Tags.of(alarm).add("AlarmType", alarm_name)
        
        Tags.of(alarm_topic).add("Purpose", "QuipSync")
        Tags.of(alarm_topic).add("Application", "QuipS3Sync")
        Tags.of(alarm_topic).add("Environment", "Production")
        
        return alarms