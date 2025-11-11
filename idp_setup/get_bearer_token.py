#!/usr/bin/env python3
"""Script to retrieve a bearer token from AWS Cognito using M2M credentials."""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional

import requests


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


def _load_config(config_path: Path) -> Dict[str, Any]:
    """Load Cognito configuration from JSON file.

    Args:
        config_path: Path to the cognito_config.json file

    Returns:
        Dictionary containing Cognito configuration
idp_set
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file is invalid JSON
    """
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        logger.info(f"Loaded configuration from {config_path}")
        return config
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file: {e}")
        raise ValueError(f"Invalid JSON in {config_path}: {e}")


def _get_token_using_client_credentials(
    domain_url: str,
    client_id: str,
    client_secret: str,
    resource_server_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve bearer token using OAuth2 Client Credentials flow.

    Args:
        domain_url: Cognito domain URL
        client_id: M2M client ID
        client_secret: M2M client secret
        resource_server_id: Optional resource server ID for scopes

    Returns:
        Dictionary containing token response with keys:
        - access_token: The bearer token
        - token_type: Token type (usually "Bearer")
        - expires_in: Token expiration time in seconds

    Raises:
        requests.HTTPError: If token request fails
    """
    token_url = f"{domain_url}/oauth2/token"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    # Add scope if resource server is specified
    if resource_server_id:
        # Default scope - can be customized based on your resource server configuration
        data["scope"] = f"{resource_server_id}/read"

    logger.info(f"Requesting token from {token_url}")
    logger.debug(f"Using client_id: {client_id}")

    try:
        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()

        token_data = response.json()
        logger.info("Successfully retrieved bearer token")
        logger.debug(f"Token expires in {token_data.get('expires_in')} seconds")

        return token_data
    except requests.HTTPError as e:
        logger.error(f"Failed to retrieve token: {e}")
        logger.error(f"Response: {e.response.text}")
        raise


def _get_token_using_username_password(
    domain_url: str,
    client_id: str,
    username: str,
    password: str,
) -> Dict[str, Any]:
    """Retrieve bearer token using username and password.

    Args:
        domain_url: Cognito domain URL
        client_id: App client ID
        username: Username
        password: Password

    Returns:
        Dictionary containing token response

    Raises:
        requests.HTTPError: If token request fails
    """
    token_url = f"{domain_url}/oauth2/token"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "password",
        "client_id": client_id,
        "username": username,
        "password": password,
    }

    logger.info(f"Requesting token from {token_url} using username/password")

    try:
        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()

        token_data = response.json()
        logger.info("Successfully retrieved bearer token")

        return token_data
    except requests.HTTPError as e:
        logger.error(f"Failed to retrieve token: {e}")
        logger.error(f"Response: {e.response.text}")
        raise


def _save_token_to_config(
    config_path: Path,
    config: Dict[str, Any],
    access_token: str,
) -> None:
    """Update the config file with the new bearer token.

    Args:
        config_path: Path to the config file
        config: Configuration dictionary
        access_token: New access token to save
    """
    config["bearer_token"] = access_token

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    logger.info(f"Updated bearer_token in {config_path}")


def main() -> None:
    """Main function to retrieve and optionally save bearer token."""
    parser = argparse.ArgumentParser(
        description="Retrieve bearer token from AWS Cognito",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
    # Using M2M credentials (default)
    uv run python -m idp_setup.get_bearer_token

    # Using username/password
    uv run python -m idp_setup.get_bearer_token --auth-method password --username testuser --password mypass

    # With custom config path
    uv run python -m idp_setup.get_bearer_token --config /path/to/config.json

    # Update config file with new token
    uv run python -m idp_setup.get_bearer_token --update-config

    # Enable debug logging
    uv run python -m idp_setup.get_bearer_token --debug
"""
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "cognito_config.json",
        help="Path to cognito_config.json file",
    )

    parser.add_argument(
        "--auth-method",
        choices=["client_credentials", "password"],
        default="client_credentials",
        help="Authentication method to use (default: client_credentials)",
    )

    parser.add_argument(
        "--username",
        type=str,
        help="Username (required for password auth method)",
    )

    parser.add_argument(
        "--password",
        type=str,
        help="Password (required for password auth method)",
    )

    parser.add_argument(
        "--update-config",
        action="store_true",
        help="Update config file with new bearer token",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Load configuration
        config = _load_config(args.config)

        # Get token based on auth method
        if args.auth_method == "client_credentials":
            token_data = _get_token_using_client_credentials(
                domain_url=config["domain_url"],
                client_id=config["m2m_client_id"],
                client_secret=config["m2m_client_secret"],
                resource_server_id=config.get("resource_server_id"),
            )
        else:  # password
            if not args.username or not args.password:
                logger.error("Username and password are required for password auth method")
                parser.print_help()
                sys.exit(1)

            token_data = _get_token_using_username_password(
                domain_url=config["domain_url"],
                client_id=config["client_id"],
                username=args.username,
                password=args.password,
            )

        # Print token
        access_token = token_data["access_token"]
        print(f"\nBearer Token:")
        print(f"{access_token}\n")

        # Print additional info
        print(f"Token Type: {token_data.get('token_type', 'Bearer')}")
        print(f"Expires In: {token_data.get('expires_in')} seconds")

        if "scope" in token_data:
            print(f"Scope: {token_data['scope']}")

        # Update config if requested
        if args.update_config:
            _save_token_to_config(args.config, config, access_token)

    except Exception as e:
        logger.error(f"Failed to retrieve token: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
