"""
Tools Package
"""

# CloudWatch Monitoring Tools
from .cloudwatch_tools import (
    list_cloudwatch_dashboards,
    get_dashboard_summary,
    list_log_groups,
    fetch_cloudwatch_logs_for_service,
    analyze_log_group,
    get_cloudwatch_alarms_for_service,
    setup_cross_account_access,
)

__all__ = [
    # CloudWatch tools
    "list_cloudwatch_dashboards",
    "get_dashboard_summary",
    "list_log_groups",
    "fetch_cloudwatch_logs_for_service",
    "analyze_log_group",
    "get_cloudwatch_alarms_for_service",
    "setup_cross_account_access",
]