"""
Lambda function for scheduled monitoring checks.
Invokes AgentCore runtime via HTTP and posts results to Slack.
"""

import json
import os
import boto3
import urllib3
import hmac
import hashlib
import base64
from datetime import datetime


http = urllib3.PoolManager()


def lambda_handler(event, context):
    """
    Lambda handler for scheduled monitoring checks.

    Triggered by EventBridge every 15 minutes.
    """
    print(f"Scheduled monitoring check started at {datetime.now()}")

    # Get configuration from environment variables
    agentcore_url = os.environ.get('AGENTCORE_RUNTIME_URL')
    slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')

    # Client credentials (M2M) authentication - preferred method
    cognito_domain_url = os.environ.get('COGNITO_DOMAIN_URL')
    m2m_client_id = os.environ.get('M2M_CLIENT_ID')
    m2m_client_secret = os.environ.get('M2M_CLIENT_SECRET')
    resource_server_id = os.environ.get('RESOURCE_SERVER_ID')

    # Fallback: username/password authentication
    cognito_user_pool_id = os.environ.get('COGNITO_USER_POOL_ID')
    cognito_client_id = os.environ.get('COGNITO_CLIENT_ID')
    cognito_client_secret = os.environ.get('COGNITO_CLIENT_SECRET')
    cognito_username = os.environ.get('COGNITO_USERNAME')
    cognito_password = os.environ.get('COGNITO_PASSWORD')

    if not agentcore_url:
        print("ERROR: AGENTCORE_RUNTIME_URL not set")
        return {'statusCode': 500, 'body': 'Missing AgentCore URL'}

    if not slack_webhook_url:
        print("ERROR: SLACK_WEBHOOK_URL not set")
        return {'statusCode': 500, 'body': 'Missing Slack webhook URL'}

    try:
        # Step 1: Get Cognito token
        print("Retrieving Cognito token...")

        # Try client credentials first (preferred M2M method)
        if m2m_client_id and m2m_client_secret and cognito_domain_url:
            print("Using client credentials authentication (M2M)")
            bearer_token = get_token_using_client_credentials(
                domain_url=cognito_domain_url,
                client_id=m2m_client_id,
                client_secret=m2m_client_secret,
                resource_server_id=resource_server_id
            )
        # Fallback to username/password
        elif cognito_username and cognito_password and cognito_client_id:
            print("Using username/password authentication (fallback)")
            bearer_token = get_cognito_token(
                cognito_user_pool_id,
                cognito_client_id,
                cognito_username,
                cognito_password,
                cognito_client_secret
            )
        else:
            raise Exception("No valid authentication credentials provided. Need either M2M credentials or username/password")

        # Step 2: Invoke AgentCore runtime via HTTP
        print("Invoking AgentCore runtime...")

        agent_payload = {
            "prompt": "Provide a summary of CloudWatch alarms, any critical issues, and resource health across AWS services. Focus on actionable insights.",
            "session_id": f"scheduled-{datetime.now().strftime('%Y%m%d-%H%M')}"
        }

        response = http.request(
            'POST',
            agentcore_url,
            body=json.dumps(agent_payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {bearer_token}'
            }
        )

        if response.status != 200:
            raise Exception(f"AgentCore request failed: {response.status} - {response.data.decode('utf-8')}")

        agent_response = response.data.decode('utf-8')
        print(f"Agent response received: {len(agent_response)} characters")

        # Step 3: Format response for Slack
        slack_message = format_slack_message(agent_response)

        # Step 4: Post to Slack
        print("Posting to Slack...")
        slack_response = http.request(
            'POST',
            slack_webhook_url,
            body=json.dumps(slack_message).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        if slack_response.status == 200:
            print("Successfully posted to Slack")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Monitoring check completed'})
            }
        else:
            print(f"Slack post failed: {slack_response.status}")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': f'Slack error: {slack_response.status}'})
            }

    except Exception as e:
        print(f"Error in monitoring check: {str(e)}")

        # Try to send error notification to Slack
        try:
            error_message = {
                "text": f"🚨 *Monitoring Agent Error*\n```{str(e)}```",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "🚨 Monitoring Agent Error"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n*Error:*\n```{str(e)}```"
                        }
                    }
                ]
            }
            http.request(
                'POST',
                slack_webhook_url,
                body=json.dumps(error_message).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
        except:
            pass

        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def _compute_secret_hash(
    username: str,
    client_id: str,
    client_secret: str
) -> str:
    """
    Compute SECRET_HASH for Cognito authentication.

    Args:
        username: Cognito username
        client_id: Cognito App Client ID
        client_secret: Cognito App Client Secret

    Returns:
        Base64-encoded SECRET_HASH
    """
    message = username + client_id
    dig = hmac.new(
        client_secret.encode('utf-8'),
        msg=message.encode('utf-8'),
        digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(dig).decode()


def get_cognito_token(
    user_pool_id: str,
    client_id: str,
    username: str,
    password: str,
    client_secret: str = None
) -> str:
    """
    Retrieve Cognito ID token using username/password authentication.

    Args:
        user_pool_id: Cognito User Pool ID
        client_id: Cognito App Client ID
        username: Cognito username
        password: Cognito password
        client_secret: Cognito App Client Secret (optional)

    Returns:
        ID token string
    """
    client = boto3.client('cognito-idp')

    auth_params = {
        'USERNAME': username,
        'PASSWORD': password
    }

    # Add SECRET_HASH if client_secret is provided
    if client_secret:
        auth_params['SECRET_HASH'] = _compute_secret_hash(
            username,
            client_id,
            client_secret
        )

    response = client.initiate_auth(
        ClientId=client_id,
        AuthFlow='USER_PASSWORD_AUTH',
        AuthParameters=auth_params
    )

    return response['AuthenticationResult']['IdToken']


def get_token_using_client_credentials(
    domain_url: str,
    client_id: str,
    client_secret: str,
    resource_server_id: str = None
) -> str:
    """
    Retrieve bearer token using OAuth2 Client Credentials flow.

    Args:
        domain_url: Cognito domain URL
        client_id: M2M client ID
        client_secret: M2M client secret
        resource_server_id: Optional resource server ID for scopes

    Returns:
        Access token string

    Raises:
        Exception: If token request fails
    """
    token_url = f"{domain_url}/oauth2/token"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    # Build form data
    data_parts = [
        "grant_type=client_credentials",
        f"client_id={client_id}",
        f"client_secret={client_secret}"
    ]

    # Add scope if resource server is specified
    if resource_server_id:
        scope = f"{resource_server_id}/gateway:read"
        data_parts.append(f"scope={scope}")

    data = "&".join(data_parts)

    print(f"Requesting token from {token_url}")

    response = http.request(
        'POST',
        token_url,
        body=data.encode('utf-8'),
        headers=headers
    )

    if response.status != 200:
        error_msg = f"Failed to retrieve token: {response.status} - {response.data.decode('utf-8')}"
        print(f"ERROR: {error_msg}")
        raise Exception(error_msg)

    token_data = json.loads(response.data.decode('utf-8'))
    print("Successfully retrieved bearer token")
    print(f"Token expires in {token_data.get('expires_in')} seconds")

    return token_data["access_token"]


def format_slack_message(agent_response: str) -> dict:
    """
    Format agent response into Slack message with blocks.

    Args:
        agent_response: Raw response from agent

    Returns:
        Slack message payload
    """
    timestamp = datetime.now().strftime("%b %d, %Y at %I:%M %p UTC")

    # Create Slack message with blocks for rich formatting
    message = {
        "text": f"AWS Monitoring Report - {timestamp}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📊 AWS Monitoring Report",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{timestamp}*"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": agent_response[:2900]  # Slack has a 3000 char limit per block
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "_Next check in 15 minutes_"
                    }
                ]
            }
        ]
    }

    return message
