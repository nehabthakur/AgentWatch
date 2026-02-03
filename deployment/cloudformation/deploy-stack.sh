#!/bin/bash
#
# One-Click CloudFormation Deployment for AgentWatch
#
# Usage:
#   ./deploy-stack.sh
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - Slack webhook URL and signing secret ready
#

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TEMPLATE_FILE="$SCRIPT_DIR/cloudformation.yaml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  AgentWatch CloudFormation Deployment${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Check prerequisites
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI not found. Please install it first.${NC}"
    exit 1
fi

# Get AWS account info
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
AWS_REGION=$(aws configure get region 2>/dev/null || echo "us-east-1")

echo -e "${GREEN}AWS Account:${NC} $AWS_ACCOUNT_ID"
echo -e "${GREEN}AWS Region:${NC} $AWS_REGION"
echo ""

# Prompt for required parameters
echo -e "${YELLOW}Please provide the following configuration:${NC}"
echo ""

read -p "Stack name [agentwatch]: " STACK_NAME
STACK_NAME=${STACK_NAME:-agentwatch}

read -p "Slack Webhook URL: " SLACK_WEBHOOK_URL
if [ -z "$SLACK_WEBHOOK_URL" ]; then
    echo -e "${RED}Error: Slack Webhook URL is required${NC}"
    exit 1
fi

read -p "Slack Signing Secret: " SLACK_SIGNING_SECRET
if [ -z "$SLACK_SIGNING_SECRET" ]; then
    echo -e "${RED}Error: Slack Signing Secret is required${NC}"
    exit 1
fi

# Generate unique Cognito domain prefix
DEFAULT_DOMAIN="${STACK_NAME}-$(echo $AWS_ACCOUNT_ID | tail -c 7)"
read -p "Cognito Domain Prefix [$DEFAULT_DOMAIN]: " COGNITO_DOMAIN
COGNITO_DOMAIN=${COGNITO_DOMAIN:-$DEFAULT_DOMAIN}

read -p "AgentCore Runtime URL (leave blank to configure later): " AGENTCORE_URL
AGENTCORE_URL=${AGENTCORE_URL:-""}

echo ""
echo -e "${YELLOW}Deploying CloudFormation stack...${NC}"
echo ""

# Deploy the stack
aws cloudformation deploy \
    --template-file "$TEMPLATE_FILE" \
    --stack-name "$STACK_NAME" \
    --parameter-overrides \
        SlackWebhookUrl="$SLACK_WEBHOOK_URL" \
        SlackSigningSecret="$SLACK_SIGNING_SECRET" \
        CognitoDomainPrefix="$COGNITO_DOMAIN" \
        AgentCoreRuntimeUrl="$AGENTCORE_URL" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "$AWS_REGION"

echo ""
echo -e "${GREEN}✅ Stack deployed successfully!${NC}"
echo ""

# Get outputs
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  Deployment Outputs${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

SLACK_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='SlackCommandEndpoint'].OutputValue" \
    --output text --region "$AWS_REGION")

COGNITO_DOMAIN_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='CognitoDomainUrl'].OutputValue" \
    --output text --region "$AWS_REGION")

M2M_CLIENT_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='M2MClientId'].OutputValue" \
    --output text --region "$AWS_REGION")

USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='CognitoUserPoolId'].OutputValue" \
    --output text --region "$AWS_REGION")

RESOURCE_SERVER_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='ResourceServerId'].OutputValue" \
    --output text --region "$AWS_REGION")

echo -e "${GREEN}Slack Command Endpoint:${NC}"
echo "  $SLACK_ENDPOINT"
echo ""
echo -e "${GREEN}Cognito Domain URL:${NC}"
echo "  $COGNITO_DOMAIN_URL"
echo ""
echo -e "${GREEN}M2M Client ID:${NC}"
echo "  $M2M_CLIENT_ID"
echo ""

# Get M2M client secret
echo -e "${YELLOW}Retrieving M2M client secret...${NC}"
M2M_CLIENT_SECRET=$(aws cognito-idp describe-user-pool-client \
    --user-pool-id "$USER_POOL_ID" \
    --client-id "$M2M_CLIENT_ID" \
    --query "UserPoolClient.ClientSecret" \
    --output text --region "$AWS_REGION")

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  Next Steps${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo -e "${YELLOW}1. Deploy AgentCore Runtime:${NC}"
echo "   cd $(dirname $SCRIPT_DIR)"
echo "   agentcore launch --agent AgentWatch"
echo ""
echo -e "${YELLOW}2. Update stack with AgentCore URL:${NC}"
echo "   After agentcore launch completes, run:"
echo "   aws cloudformation update-stack \\"
echo "     --stack-name $STACK_NAME \\"
echo "     --use-previous-template \\"
echo "     --parameters \\"
echo "       ParameterKey=SlackWebhookUrl,UsePreviousValue=true \\"
echo "       ParameterKey=SlackSigningSecret,UsePreviousValue=true \\"
echo "       ParameterKey=CognitoDomainPrefix,UsePreviousValue=true \\"
echo "       ParameterKey=AgentCoreRuntimeUrl,ParameterValue=<YOUR_AGENTCORE_URL> \\"
echo "     --capabilities CAPABILITY_NAMED_IAM"
echo ""
echo -e "${YELLOW}3. Configure Slack App:${NC}"
echo "   - Go to https://api.slack.com/apps"
echo "   - Create or select your app"
echo "   - Add Slash Command: /ask"
echo "   - Set Request URL to: $SLACK_ENDPOINT"
echo ""
echo -e "${YELLOW}4. Save these credentials for .env file:${NC}"
echo ""
cat << EOF
# Add to your .env file:
COGNITO_DOMAIN_URL=$COGNITO_DOMAIN_URL
M2M_CLIENT_ID=$M2M_CLIENT_ID
M2M_CLIENT_SECRET=$M2M_CLIENT_SECRET
RESOURCE_SERVER_ID=$RESOURCE_SERVER_ID
SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL
SLACK_SIGNING_SECRET=$SLACK_SIGNING_SECRET
EOF
echo ""
echo -e "${GREEN}✅ Deployment complete!${NC}"