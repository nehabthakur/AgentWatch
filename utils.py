"""
Utility functions for the ambient monitoring agent.
"""
import logging
from pathlib import Path
from typing import Union, Dict, Optional

import yaml


# set a logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def load_config(
    config_file: Union[Path, str]
) -> Optional[Dict]:
    """
    Load configuration from a local file.

    Args:
        config_file: Path to the local file

    Returns:
        Dictionary with the loaded configuration
    """
    try:
        config_data: Optional[Dict] = None
        logger.info(f"Loading config from local file system: {config_file}")
        content = Path(config_file).read_text()
        config_data = yaml.safe_load(content)
        logger.info(f"Loaded config from local file system: {config_data}")
    except Exception as e:
        logger.error(f"Error loading config from local file system: {e}")
        config_data = None
    return config_data


def load_system_prompt(
    prompt_path: str
) -> str:
    """
    Load the system prompt from a file path.

    Args:
        prompt_path: Relative or absolute path to the system prompt file

    Returns:
        The system prompt as a string
    """
    try:
        # First try absolute path or relative to current directory
        if Path(prompt_path).exists():
            with open(prompt_path, 'r') as f:
                prompt_content = f.read()
            logger.info(f"Successfully loaded system prompt from {prompt_path}")
            return prompt_content

        # If not found, try relative to package directory
        import pkg_resources
        package_prompt_path = pkg_resources.resource_filename(
            "ml_cost_analysis", prompt_path
        )
        with open(package_prompt_path, 'r') as f:
            prompt_content = f.read()
        logger.info(f"Successfully loaded system prompt from package: {package_prompt_path}")
        return prompt_content
    except FileNotFoundError:
        logger.error(f"System prompt file not found at {prompt_path}")
        raise
    except Exception as e:
        logger.error(f"Error loading system prompt from {prompt_path}: {str(e)}")
        raise

def setup_cognito_user_pool():
    boto_session = Session()
    region = boto_session.region_name
    
    # Initialize Cognito client
    cognito_client = boto3.client('cognito-idp', region_name=region)
    
    try:
        # Create User Pool
        user_pool_response = cognito_client.create_user_pool(
            PoolName='MCPServerPool',
            Policies={
                'PasswordPolicy': {
                    'MinimumLength': 8
                }
            }
        )
        pool_id = user_pool_response['UserPool']['Id']
        
        # Create App Client
        app_client_response = cognito_client.create_user_pool_client(
            UserPoolId=pool_id,
            ClientName='MCPServerPoolClient',
            GenerateSecret=False,
            ExplicitAuthFlows=[
                'ALLOW_USER_PASSWORD_AUTH',
                'ALLOW_REFRESH_TOKEN_AUTH'
            ]
        )
        client_id = app_client_response['UserPoolClient']['ClientId']
        
        # Create User
        cognito_client.admin_create_user(
            UserPoolId=pool_id,
            Username='testuser',
            TemporaryPassword='Temp123!',
            MessageAction='SUPPRESS'
        )
        
        # Set Permanent Password
        cognito_client.admin_set_user_password(
            UserPoolId=pool_id,
            Username='testuser',
            Password='MyPassword123!',
            Permanent=True
        )
        
        # Authenticate User and get Access Token
        auth_response = cognito_client.initiate_auth(
            ClientId=client_id,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': 'testuser',
                'PASSWORD': 'MyPassword123!'
            }
        )
        bearer_token = auth_response['AuthenticationResult']['AccessToken']
        
        # Output the required values
        print(f"Pool id: {pool_id}")
        print(f"Discovery URL: https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/openid-configuration")
        print(f"Client ID: {client_id}")
        print(f"Bearer Token: {bearer_token}")
        
        # Return values if needed for further processing
        return {
            'pool_id': pool_id,
            'client_id': client_id,
            'bearer_token': bearer_token,
            'discovery_url':f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/openid-configuration"
        }
        
    except Exception as e:
        print(f"Error: {e}")
        return None

def get_or_create_resource_server(cognito, user_pool_id, RESOURCE_SERVER_ID, RESOURCE_SERVER_NAME, SCOPES):
    try:
        existing = cognito.describe_resource_server(
            UserPoolId=user_pool_id,
            Identifier=RESOURCE_SERVER_ID
        )
        return RESOURCE_SERVER_ID
    except cognito.exceptions.ResourceNotFoundException:
        print('creating new resource server')
        cognito.create_resource_server(
            UserPoolId=user_pool_id,
            Identifier=RESOURCE_SERVER_ID,
            Name=RESOURCE_SERVER_NAME,
            Scopes=SCOPES
        )
        return RESOURCE_SERVER_ID
    
def get_or_create_m2m_client(cognito, user_pool_id, CLIENT_NAME, RESOURCE_SERVER_ID):
    response = cognito.list_user_pool_clients(UserPoolId=user_pool_id, MaxResults=60)
    for client in response["UserPoolClients"]:
        if client["ClientName"] == CLIENT_NAME:
            describe = cognito.describe_user_pool_client(UserPoolId=user_pool_id, ClientId=client["ClientId"])
            return client["ClientId"], describe["UserPoolClient"]["ClientSecret"]
    print('creating new m2m client')
    created = cognito.create_user_pool_client(
        UserPoolId=user_pool_id,
        ClientName=CLIENT_NAME,
        GenerateSecret=True,
        AllowedOAuthFlows=["client_credentials"],
        AllowedOAuthScopes=[f"{RESOURCE_SERVER_ID}/gateway:read", f"{RESOURCE_SERVER_ID}/gateway:write"],
        AllowedOAuthFlowsUserPoolClient=True,
        SupportedIdentityProviders=["COGNITO"],
        ExplicitAuthFlows=["ALLOW_REFRESH_TOKEN_AUTH"]
    )
    return created["UserPoolClient"]["ClientId"], created["UserPoolClient"]["ClientSecret"]

def create_cognito_domain(
    user_pool_id: str, 
    domain_name: Optional[str] = None,
    region: Optional[str] = None
) -> Dict[str, str]:
    """
    Create a domain for the Cognito User Pool.
    
    Args:
        user_pool_id: The Cognito User Pool ID
        domain_name: Optional custom domain name. If not provided, creates one from pool ID
        region: AWS region. If not provided, uses current session region
        
    Returns:
        Dictionary containing domain information with 'domain' and 'domain_url' keys
        
    Raises:
        Exception: If domain creation fails
    """
    if region is None:
        boto_session = Session()
        region = boto_session.region_name
    
    cognito_client = boto3.client('cognito-idp', region_name=region)
    
    try:
        # Check if domain already exists for this user pool
        try:
            response = cognito_client.describe_user_pool(UserPoolId=user_pool_id)
            user_pool = response.get('UserPool', {})
            existing_domain = user_pool.get('Domain')
            
            if existing_domain:
                domain_url = f"https://{existing_domain}.auth.{region}.amazoncognito.com"
                logger.info(f"Domain already exists for user pool {user_pool_id}: {existing_domain}")
                return {
                    'domain': existing_domain,
                    'domain_url': domain_url,
                    'status': 'existing'
                }
        except Exception as e:
            logger.error(f"Error checking existing domain: {e}")
        
        # Generate domain name if not provided
        if domain_name is None:
            # Create domain name from pool ID - remove first underscore and convert to lowercase
            if '_' in user_pool_id:
                domain_name = user_pool_id.replace('_', '', 1).lower()
            else:
                domain_name = user_pool_id.lower()
        
        # Ensure domain name is valid (alphanumeric and hyphens only, lowercase)
        domain_name = domain_name.lower().replace('_', '-')
        
        logger.info(f"Creating Cognito domain: {domain_name} for pool: {user_pool_id}")
        
        # Create the domain
        response = cognito_client.create_user_pool_domain(
            Domain=domain_name,
            UserPoolId=user_pool_id
        )
        
        domain_url = f"https://{domain_name}.auth.{region}.amazoncognito.com"
        
        logger.info(f"Successfully created domain: {domain_name}")
        logger.info(f"Domain URL: {domain_url}")
        
        return {
            'domain': domain_name,
            'domain_url': domain_url,
            'status': 'created',
            'cloudfront_domain': response.get('CloudFrontDomain', '')
        }
        
    except cognito_client.exceptions.InvalidParameterException as e:
        if 'Domain already associated' in str(e):
            # Domain might be associated with another pool
            logger.warning(f"Domain {domain_name} already in use: {e}")
            # Try with a timestamp suffix
            import time
            timestamp_suffix = str(int(time.time()))[-6:]
            new_domain_name = f"{domain_name}-{timestamp_suffix}"
            
            logger.info(f"Trying with timestamped domain: {new_domain_name}")
            response = cognito_client.create_user_pool_domain(
                Domain=new_domain_name,
                UserPoolId=user_pool_id
            )
            
            domain_url = f"https://{new_domain_name}.auth.{region}.amazoncognito.com"
            
            return {
                'domain': new_domain_name,
                'domain_url': domain_url,
                'status': 'created_with_suffix',
                'cloudfront_domain': response.get('CloudFrontDomain', '')
            }
        else:
            logger.error(f"Invalid parameter for domain creation: {e}")
            raise
            
    except Exception as e:
        logger.error(f"Error creating Cognito domain: {e}")
        raise

def get_or_create_user_pool(cognito, USER_POOL_NAME, CREATE_USER_POOL: bool = False):
    response = cognito.list_user_pools(MaxResults=60)
    for pool in response["UserPools"]:
        if pool["Name"] == USER_POOL_NAME:
            user_pool_id = pool["Id"]
            response = cognito.describe_user_pool(
                UserPoolId=user_pool_id
            )
        
            # Get the domain from user pool description
            user_pool = response.get('UserPool', {})
            domain = user_pool.get('Domain')
        
            if domain:
                region = user_pool_id.split('_')[0] if '_' in user_pool_id else REGION
                domain_url = f"https://{domain}.auth.{region}.amazoncognito.com"
                print(f"Found domain for user pool {user_pool_id}: {domain} ({domain_url})")
            else:
                print(f"No domains found for user pool {user_pool_id}")
            return pool["Id"]
    print('Creating new user pool')
    if CREATE_USER_POOL:
        created = cognito.create_user_pool(PoolName=USER_POOL_NAME)
        user_pool_id = created["UserPool"]["Id"]
        # Create domain name correctly - remove only first underscore
        if '_' in user_pool_id:
            user_pool_domain = user_pool_id.replace('_', '', 1).lower()
        else:
            user_pool_domain = user_pool_id.lower()
        cognito.create_user_pool_domain(
            Domain=user_pool_domain,
            UserPoolId=user_pool_id
        )
        print("Domain created as well")
    else:
        print(f"User pool creation set to {CREATE_USER_POOL}. Returning.")
        return
    return created["UserPool"]["Id"]