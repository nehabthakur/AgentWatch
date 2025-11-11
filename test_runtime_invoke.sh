#!/bin/bash

# Exit on error
set -e

# Configuration from cognito_config.json
AWS_REGION="us-west-2"
COGNITO_DOMAIN="us-west-2jy9ha8msb"
M2M_CLIENT_ID="us65bl9tcmaghof9g6e5pfmui"
M2M_CLIENT_SECRET="gl9q81ub184o23r3fm3oeldlm3kpngqrmai60r6bjjmu2ktcgvu"
RESOURCE_SERVER_ID="monitoring-agentcore-gateway-id"
RUNTIME_URL="https://bedrock-agentcore.us-west-2.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-west-2%3A218208277580%3Aruntime%2Fambient_agent-GdSzEe2MzI/invocations?qualifier=DEFAULT"

echo "🔐 Getting Cognito token using M2M credentials..."

# Get token from Cognito using client credentials
TOKEN_RESPONSE=$(curl -s -X POST \
  "https://${COGNITO_DOMAIN}.auth.${AWS_REGION}.amazoncognito.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=${M2M_CLIENT_ID}&client_secret=${M2M_CLIENT_SECRET}&scope=${RESOURCE_SERVER_ID}/gateway:read")

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token')

if [ "$ACCESS_TOKEN" == "null" ] || [ -z "$ACCESS_TOKEN" ]; then
    echo "❌ Failed to get access token"
    echo "Response: $TOKEN_RESPONSE"
    exit 1
fi

echo "✅ Got access token (length: ${#ACCESS_TOKEN})"
echo ""
echo "🔑 Access Token:"
echo "$ACCESS_TOKEN"
echo ""
echo "📋 Copy-paste command to run directly:"
echo ""
echo "curl -X POST '$RUNTIME_URL' \\"
echo "  -H 'Authorization: Bearer $ACCESS_TOKEN' \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"prompt\": \"Hello! Just respond with a simple greeting.\"}'"
echo ""
echo "🚀 Testing runtime invocation..."
echo ""

# Test with a simple request matching the Lambda payload structure
# Write response to temp file for safer parsing
TEMP_FILE=$(mktemp)
HTTP_CODE=$(curl -s -w "%{http_code}" -o "$TEMP_FILE" -X POST \
  "$RUNTIME_URL" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Hello! Just respond with a simple greeting."
  }')

# Read the response body from the temp file
HTTP_BODY=$(cat "$TEMP_FILE")
rm -f "$TEMP_FILE"

echo "📊 HTTP Status: $HTTP_CODE"
echo ""
echo "📝 Response Body:"
echo "$HTTP_BODY" | jq '.' 2>/dev/null || echo "$HTTP_BODY"

if [ "$HTTP_CODE" -eq 200 ]; then
    echo ""
    echo "✅ Runtime invocation successful!"
else
    echo ""
    echo "❌ Runtime invocation failed"
fi
