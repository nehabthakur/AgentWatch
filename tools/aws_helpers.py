"""
AWS Helper Utilities

Provides helper functions for AWS cross-account access and client management.
"""

import os
import logging
import boto3
from typing import Optional

logger = logging.getLogger(__name__)

# Default region - can be overridden by AWS_DEFAULT_REGION environment variable
DEFAULT_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')


def _get_region() -> str:
    """Get the AWS region from environment or session, defaulting to us-east-1."""
    # Try environment variable first
    region = os.environ.get('AWS_DEFAULT_REGION') or os.environ.get('AWS_REGION')
    if region:
        return region

    # Try boto3 session
    try:
        session_region = boto3.session.Session().region_name
        if session_region:
            return session_region
    except Exception:
        pass

    # Default to us-east-1
    return 'us-east-1'


def _get_cross_account_client(
    service: str,
    account_id: Optional[str] = None,
    role_name: Optional[str] = None,
    region: Optional[str] = None,
):
    """
    Get AWS client with optional cross-account access.

    Args:
        service: AWS service name (e.g., 'cloudwatch', 'logs', 'sts')
        account_id: Target AWS account ID for cross-account access
        role_name: IAM role name to assume in target account
        region: AWS region (defaults to us-east-1 if not specified)

    Returns:
        Boto3 client for the specified service

    Raises:
        Exception: If cross-account role assumption fails

    Example:
        >>> client = _get_cross_account_client('cloudwatch', '123456789012', 'MonitoringRole')
        >>> dashboards = client.list_dashboards()
    """
    # Determine the region to use
    target_region = region or _get_region()

    try:
        if account_id and role_name:
            logger.info(
                f"Setting up cross-account access for account {account_id} with role {role_name}"
            )
            sts = boto3.client("sts", region_name=target_region)
            role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

            assumed_role = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName="MonitoringAgentSession",
            )
            credentials = assumed_role["Credentials"]

            return boto3.client(
                service,
                region_name=target_region,
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
            )

        return boto3.client(service, region_name=target_region)

    except Exception as e:
        logger.error(f"Error creating {service} client: {str(e)}")
        raise


def _format_account_context(
    account_id: Optional[str] = None,
) -> str:
    """
    Format account context for logging and user messages.

    Args:
        account_id: AWS account ID (None for current account)

    Returns:
        Formatted account context string
    """
    return f"account {account_id}" if account_id else "current account"