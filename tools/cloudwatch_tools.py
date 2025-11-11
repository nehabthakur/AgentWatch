"""
CloudWatch Monitoring Tools

Provides LangChain tools for AWS CloudWatch monitoring operations including
dashboards, logs, alarms, and cross-account access.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from langchain_core.tools import tool

from .aws_helpers import _get_cross_account_client, _format_account_context

logger = logging.getLogger(__name__)


# Service to log group prefix mapping
SERVICE_LOG_GROUPS = {
    "lambda": ["/aws/lambda/"],
    "ec2": ["/aws/ec2/", "/var/log/"],
    "rds": ["/aws/rds/"],
    "eks": ["/aws/eks/"],
    "apigateway": ["/aws/apigateway/"],
    "bedrock": ["/aws/bedrock/"],
    "vpc": ["/aws/vpc/"],
    "iam": ["/aws/iam/"],
    "s3": ["/aws/s3/"],
    "cloudtrail": ["/aws/cloudtrail/"],
    "waf": ["/aws/waf/"],
}


@tool
def list_cloudwatch_dashboards(
    account_id: Optional[str] = None,
    role_name: Optional[str] = None,
) -> str:
    """
    List all CloudWatch dashboards in an AWS account.

    Use this tool to discover available CloudWatch dashboards for monitoring.
    Supports cross-account access when account_id and role_name are provided.

    Args:
        account_id: Target AWS account ID for cross-account access (optional)
        role_name: IAM role name to assume in target account (optional)

    Returns:
        Formatted string with list of dashboard names and descriptions
    """
    try:
        cloudwatch = _get_cross_account_client("cloudwatch", account_id, role_name)
        response = cloudwatch.list_dashboards()

        dashboards = response.get("DashboardEntries", [])
        account_context = _format_account_context(account_id)

        if not dashboards:
            return f"No CloudWatch dashboards found in {account_context}."

        result = [f"Found {len(dashboards)} CloudWatch dashboard(s) in {account_context}:\n"]

        for dashboard in dashboards:
            result.append(f"  - {dashboard['DashboardName']}")

        logger.info(f"Listed {len(dashboards)} dashboards from {account_context}")
        return "\n".join(result)

    except Exception as e:
        error_msg = f"Error listing CloudWatch dashboards: {str(e)}"
        logger.error(error_msg)
        return error_msg


@tool
def get_dashboard_summary(
    dashboard_name: str,
    account_id: Optional[str] = None,
    role_name: Optional[str] = None,
) -> str:
    """
    Get detailed summary of a specific CloudWatch dashboard.

    Use this tool to retrieve configuration details for a specific dashboard.

    Args:
        dashboard_name: Name of the CloudWatch dashboard
        account_id: Target AWS account ID for cross-account access (optional)
        role_name: IAM role name to assume in target account (optional)

    Returns:
        Formatted string with dashboard summary
    """
    try:
        cloudwatch = _get_cross_account_client("cloudwatch", account_id, role_name)
        response = cloudwatch.get_dashboard(DashboardName=dashboard_name)

        account_context = _format_account_context(account_id)
        dashboard_body = response.get("DashboardBody", "")

        result = [
            f"Dashboard: {dashboard_name}",
            f"Account: {account_context}",
            f"ARN: {response.get('DashboardArn', 'N/A')}",
            f"\nConfiguration retrieved successfully.",
        ]

        logger.info(f"Retrieved dashboard summary for {dashboard_name}")
        return "\n".join(result)

    except Exception as e:
        error_msg = f"Error getting dashboard summary for '{dashboard_name}': {str(e)}"
        logger.error(error_msg)
        return error_msg


@tool
def list_log_groups(
    account_id: Optional[str] = None,
    role_name: Optional[str] = None,
    limit: int = 50,
) -> str:
    """
    List CloudWatch log groups in an AWS account.

    Use this tool to discover available log groups for analysis.

    Args:
        account_id: Target AWS account ID for cross-account access (optional)
        role_name: IAM role name to assume in target account (optional)
        limit: Maximum number of log groups to return (default: 50)

    Returns:
        Formatted string with list of log group names
    """
    try:
        logs_client = _get_cross_account_client("logs", account_id, role_name)
        account_context = _format_account_context(account_id)

        log_groups = []
        paginator = logs_client.get_paginator("describe_log_groups")

        for page in paginator.paginate():
            for log_group in page["logGroups"]:
                log_groups.append(log_group["logGroupName"])
                if len(log_groups) >= limit:
                    break
            if len(log_groups) >= limit:
                break

        if not log_groups:
            return f"No log groups found in {account_context}."

        result = [f"Found {len(log_groups)} log group(s) in {account_context}:\n"]
        for log_group in log_groups:
            result.append(f"  - {log_group}")

        logger.info(f"Listed {len(log_groups)} log groups from {account_context}")
        return "\n".join(result)

    except Exception as e:
        error_msg = f"Error listing log groups: {str(e)}"
        logger.error(error_msg)
        return error_msg


@tool
def fetch_cloudwatch_logs_for_service(
    service_name: str,
    hours: int = 1,
    account_id: Optional[str] = None,
    role_name: Optional[str] = None,
    max_events: int = 50,
) -> str:
    """
    Fetch recent CloudWatch logs for a specific AWS service.

    Use this tool to retrieve and analyze recent log entries from services like
    Lambda, EC2, RDS, EKS, API Gateway, Amazon Bedrock, etc.

    Args:
        service_name: AWS service name (e.g., 'lambda', 'ec2', 'bedrock')
        hours: Number of hours of logs to retrieve (default: 1)
        account_id: Target AWS account ID for cross-account access (optional)
        role_name: IAM role name to assume in target account (optional)
        max_events: Maximum number of log events to return (default: 50)

    Returns:
        Formatted string with log entries
    """
    try:
        logs_client = _get_cross_account_client("logs", account_id, role_name)
        account_context = _format_account_context(account_id)

        # Get log group prefixes for the service
        log_group_prefixes = SERVICE_LOG_GROUPS.get(
            service_name.lower(),
            [f"/aws/{service_name}/"],
        )

        start_time = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)
        all_logs = []

        for prefix in log_group_prefixes:
            try:
                paginator = logs_client.get_paginator("describe_log_groups")
                for page in paginator.paginate(logGroupNamePrefix=prefix):
                    for log_group in page["logGroups"]:
                        try:
                            events = logs_client.filter_log_events(
                                logGroupName=log_group["logGroupName"],
                                startTime=start_time,
                                limit=max_events,
                            )

                            for event in events.get("events", []):
                                timestamp = datetime.fromtimestamp(
                                    event["timestamp"] / 1000
                                ).isoformat()
                                all_logs.append(
                                    {
                                        "timestamp": timestamp,
                                        "log_group": log_group["logGroupName"],
                                        "message": event["message"],
                                    }
                                )

                                if len(all_logs) >= max_events:
                                    break

                        except Exception as log_error:
                            logger.warning(
                                f"Error fetching logs from {log_group['logGroupName']}: {str(log_error)}"
                            )
                            continue

                        if len(all_logs) >= max_events:
                            break

                    if len(all_logs) >= max_events:
                        break

            except Exception as group_error:
                logger.warning(
                    f"Error listing log groups with prefix {prefix}: {str(group_error)}"
                )
                continue

        if not all_logs:
            return f"No logs found for service '{service_name}' in the last {hours} hour(s) in {account_context}."

        result = [
            f"Retrieved {len(all_logs)} log entries for service '{service_name}' from {account_context}:\n"
        ]

        for log in all_logs[:max_events]:
            result.append(f"[{log['timestamp']}] {log['log_group']}")
            result.append(f"  {log['message'][:200]}...\n")

        logger.info(
            f"Retrieved {len(all_logs)} log entries for service {service_name}"
        )
        return "\n".join(result)

    except Exception as e:
        error_msg = f"Error fetching logs for service '{service_name}': {str(e)}"
        logger.error(error_msg)
        return error_msg


@tool
def analyze_log_group(
    log_group_name: str,
    hours: int = 1,
    account_id: Optional[str] = None,
    role_name: Optional[str] = None,
) -> str:
    """
    Analyze a specific CloudWatch log group for errors and patterns.

    Use this tool to get insights into log patterns, error rates, and anomalies
    in a specific log group.

    Args:
        log_group_name: Name of the CloudWatch log group to analyze
        hours: Number of hours of logs to analyze (default: 1)
        account_id: Target AWS account ID for cross-account access (optional)
        role_name: IAM role name to assume in target account (optional)

    Returns:
        Formatted string with analysis results
    """
    try:
        logs_client = _get_cross_account_client("logs", account_id, role_name)
        account_context = _format_account_context(account_id)

        start_time = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)

        events = logs_client.filter_log_events(
            logGroupName=log_group_name,
            startTime=start_time,
            limit=1000,
        )

        log_events = events.get("events", [])
        total_events = len(log_events)

        if total_events == 0:
            return f"No log events found in '{log_group_name}' for the last {hours} hour(s) in {account_context}."

        # Analyze for errors
        error_count = 0
        warning_count = 0
        error_keywords = ["error", "fail", "exception", "critical"]
        warning_keywords = ["warning", "warn"]

        for event in log_events:
            message_lower = event["message"].lower()
            if any(keyword in message_lower for keyword in error_keywords):
                error_count += 1
            elif any(keyword in message_lower for keyword in warning_keywords):
                warning_count += 1

        error_rate = (error_count / total_events * 100) if total_events > 0 else 0
        warning_rate = (warning_count / total_events * 100) if total_events > 0 else 0

        result = [
            f"Log Group Analysis: {log_group_name}",
            f"Account: {account_context}",
            f"Time Range: Last {hours} hour(s)",
            f"\nSummary:",
            f"  Total Events: {total_events}",
            f"  Errors: {error_count} ({error_rate:.1f}%)",
            f"  Warnings: {warning_count} ({warning_rate:.1f}%)",
        ]

        if error_count > 0:
            result.append(
                f"\n[!]  High error rate detected! Investigate immediately."
            )
        elif warning_count > total_events * 0.1:
            result.append(
                f"\n[!]  Elevated warning count. Review may be needed."
            )
        else:
            result.append(f"\n Log group appears healthy.")

        logger.info(
            f"Analyzed log group {log_group_name}: {total_events} events, {error_count} errors"
        )
        return "\n".join(result)

    except Exception as e:
        error_msg = f"Error analyzing log group '{log_group_name}': {str(e)}"
        logger.error(error_msg)
        return error_msg


@tool
def get_cloudwatch_alarms_for_service(
    service_name: str,
    account_id: Optional[str] = None,
    role_name: Optional[str] = None,
) -> str:
    """
    Get CloudWatch alarms related to a specific AWS service.

    Use this tool to check alarm status and identify issues with AWS services.

    Args:
        service_name: AWS service name (e.g., 'lambda', 'ec2', 'bedrock')
        account_id: Target AWS account ID for cross-account access (optional)
        role_name: IAM role name to assume in target account (optional)

    Returns:
        Formatted string with alarm details
    """
    try:
        cloudwatch = _get_cross_account_client("cloudwatch", account_id, role_name)
        account_context = _format_account_context(account_id)

        response = cloudwatch.describe_alarms()
        all_alarms = response.get("MetricAlarms", [])

        # Filter alarms related to the service
        service_alarms = []
        for alarm in all_alarms:
            alarm_name = alarm.get("AlarmName", "").lower()
            namespace = alarm.get("Namespace", "").lower()

            if service_name.lower() in alarm_name or service_name.lower() in namespace:
                service_alarms.append(
                    {
                        "name": alarm["AlarmName"],
                        "state": alarm["StateValue"],
                        "reason": alarm.get("StateReason", "N/A"),
                        "namespace": alarm.get("Namespace", "N/A"),
                    }
                )

        if not service_alarms:
            return f"No CloudWatch alarms found for service '{service_name}' in {account_context}."

        # Group by state
        alarm_state = alarm_ok = in_alarm = insufficient_data = 0

        for alarm in service_alarms:
            if alarm["state"] == "OK":
                alarm_ok += 1
            elif alarm["state"] == "ALARM":
                in_alarm += 1
            else:
                insufficient_data += 1

        result = [
            f"CloudWatch Alarms for '{service_name}' in {account_context}:",
            f"\nSummary:",
            f"  Total Alarms: {len(service_alarms)}",
            f"  OK: {alarm_ok}",
            f"  ALARM: {in_alarm}",
            f"  INSUFFICIENT_DATA: {insufficient_data}",
            f"\nAlarm Details:",
        ]

        for alarm in service_alarms:
            state_icon = (
                "" if alarm["state"] == "OK" else "[!]" if alarm["state"] == "ALARM" else "?"
            )
            result.append(f"  {state_icon} {alarm['name']}: {alarm['state']}")
            if alarm["state"] == "ALARM":
                result.append(f"      Reason: {alarm['reason']}")

        logger.info(
            f"Found {len(service_alarms)} alarms for service {service_name} ({in_alarm} in ALARM state)"
        )
        return "\n".join(result)

    except Exception as e:
        error_msg = (
            f"Error getting CloudWatch alarms for service '{service_name}': {str(e)}"
        )
        logger.error(error_msg)
        return error_msg


@tool
def setup_cross_account_access(
    account_id: str,
    role_name: str,
) -> str:
    """
    Setup and verify cross-account access to CloudWatch and logs.

    Use this tool to test cross-account IAM role configuration before
    performing monitoring operations.

    Args:
        account_id: Target AWS account ID
        role_name: IAM role name to assume in target account

    Returns:
        Formatted string with verification results
    """
    try:
        # Test cross-account access
        test_client = _get_cross_account_client("sts", account_id, role_name)
        identity = test_client.get_caller_identity()

        assumed_account = identity["Account"]
        assumed_arn = identity["Arn"]

        result = [
            f" Cross-account access verified successfully!",
            f"\nTarget Account: {account_id}",
            f"Role Name: {role_name}",
            f"Assumed Account: {assumed_account}",
            f"Assumed Role ARN: {assumed_arn}",
            f"\nYou can now use this account configuration with other monitoring tools.",
        ]

        logger.info(
            f"Successfully verified cross-account access for account {account_id}"
        )
        return "\n".join(result)

    except Exception as e:
        error_msg = f"L Failed to setup cross-account access: {str(e)}"
        logger.error(error_msg)
        return error_msg