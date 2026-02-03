#!/bin/bash
#
# AgentCore Runtime Redeployment Script
#
# This script redeploys the ambient agent to AWS Bedrock AgentCore Runtime,
# creating a new version with the latest code changes.
#
# Based on AWS AgentCore Runtime Versioning:
# - Each update creates a new immutable version
# - The DEFAULT endpoint automatically points to the latest version
#
# Usage:
#   ./redeploy_agentcore.sh [--wait]
#

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_ROOT/.bedrock_agentcore.yaml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
WAIT_FOR_READY=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --wait)
            WAIT_FOR_READY=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--wait]"
            echo ""
            echo "Options:"
            echo "  --wait    Wait for the runtime to become READY after deployment"
            echo "  --help    Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  AgentCore Runtime Redeployment${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}Error: Configuration file not found: $CONFIG_FILE${NC}"
    echo "Please run 'agentcore configure' first to set up the agent."
    exit 1
fi

# Extract agent name from config
AGENT_NAME=$(grep "default_agent:" "$CONFIG_FILE" | cut -d':' -f2 | tr -d ' ')
if [ -z "$AGENT_NAME" ]; then
    echo -e "${RED}Error: Could not determine default agent name${NC}"
    exit 1
fi

# Extract agent ID from config
AGENT_ID=$(grep "agent_id:" "$CONFIG_FILE" | head -1 | cut -d':' -f2 | tr -d ' ')
REGION=$(grep "region:" "$CONFIG_FILE" | head -1 | cut -d':' -f2 | tr -d ' ')

echo -e "${GREEN}Agent Configuration:${NC}"
echo "  Name:     $AGENT_NAME"
echo "  Agent ID: $AGENT_ID"
echo "  Region:   $REGION"
echo ""

# Check if agentcore CLI is installed
if ! command -v agentcore &> /dev/null; then
    echo -e "${RED}Error: 'agentcore' CLI not found.${NC}"
    echo "Please install the bedrock-agentcore-starter-toolkit:"
    echo "  pip install bedrock-agentcore-starter-toolkit"
    exit 1
fi

# Run agentcore launch
echo -e "${YELLOW}Starting AgentCore redeployment...${NC}"
echo "This will create a new version with your latest code changes."
echo "The DEFAULT endpoint will automatically point to the new version."
echo ""

cd "$PROJECT_ROOT"

echo -e "${BLUE}Running: agentcore launch --agent $AGENT_NAME${NC}"
echo ""

if agentcore launch --agent "$AGENT_NAME"; then
    echo ""
    echo -e "${GREEN}✅ AgentCore launch command completed successfully${NC}"
else
    echo ""
    echo -e "${RED}❌ AgentCore launch failed${NC}"
    exit 1
fi

# Wait for ready if requested
if [ "$WAIT_FOR_READY" = true ]; then
    echo ""
    echo -e "${YELLOW}Waiting for runtime to become READY...${NC}"

    TIMEOUT=600
    ELAPSED=0
    INTERVAL=10

    while [ $ELAPSED -lt $TIMEOUT ]; do
        # Get runtime status using AWS CLI
        STATUS=$(aws bedrock-agentcore get-agent-runtime \
            --agent-runtime-id "$AGENT_ID" \
            --region "$REGION" \
            --query 'status' \
            --output text 2>/dev/null || echo "UNKNOWN")

        if [ "$STATUS" = "READY" ]; then
            echo ""
            echo -e "${GREEN}✅ Runtime is READY!${NC}"
            break
        elif [ "$STATUS" = "CREATE_FAILED" ] || [ "$STATUS" = "UPDATE_FAILED" ]; then
            echo ""
            echo -e "${RED}❌ Runtime failed with status: $STATUS${NC}"
            exit 1
        else
            echo -ne "  Status: $STATUS... (${ELAPSED}s elapsed)\r"
            sleep $INTERVAL
            ELAPSED=$((ELAPSED + INTERVAL))
        fi
    done

    if [ $ELAPSED -ge $TIMEOUT ]; then
        echo ""
        echo -e "${YELLOW}⚠️ Timeout waiting for runtime to become READY${NC}"
    fi
fi

# Show summary
echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  Deployment Summary${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo -e "${GREEN}✅ A new version has been created with your code changes.${NC}"
echo ""
echo "Key Information:"
echo "  • The DEFAULT endpoint automatically points to the latest version"
echo "  • Custom endpoints need to be manually updated"
echo ""
echo "Useful Commands:"
echo "  # Check status:"
echo "  aws bedrock-agentcore get-agent-runtime --agent-runtime-id $AGENT_ID --region $REGION"
echo ""
echo "  # List versions:"
echo "  aws bedrock-agentcore list-agent-runtime-versions --agent-runtime-id $AGENT_ID --region $REGION"
echo ""
echo "  # View logs:"
echo "  aws logs tail /aws/agentcore/$AGENT_ID --follow --region $REGION"
echo ""