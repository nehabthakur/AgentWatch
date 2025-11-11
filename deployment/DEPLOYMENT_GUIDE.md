# Ambient Agent Slack Integration - Deployment Guide

This guide will walk you through deploying your ambient monitoring agent with scheduled Slack notifications.

## Architecture

```
EventBridge Rule (every 15 min)
        ↓
    Lambda Function
        ↓
    Retrieve Cognito Token
        ↓
    Invoke AgentCore Runtime (HTTP POST)
        ↓
    Format Response
        ↓
    Post to Slack Webhook
```

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** installed and configured
3. **AgentCore Runtime** already deployed (✅ You have this)
4. **Cognito User Pool** with user credentials for authentication
5. **Slack App** with Incoming Webhook configured

## Step 1: Set Up Slack Webhook

1. Go to your Slack App settings: https://api.slack.com/apps/A09S5754CPP
2. Navigate to **Incoming Webhooks** in the left sidebar
3. Click **Activate Incoming Webhooks** (if not already active)
4. Click **Add New Webhook to Workspace**
5. Select the channel where you want to receive monitoring updates
6. Copy the webhook URL (it looks like: `https://hooks.slack.com/services/T.../B.../xxx`)

## Step 2: Configure Environment Variables

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit the `.env` file with your actual values:
   ```bash
   # AWS Configuration
   AWS_REGION=us-west-2

   # AgentCore Runtime (already have this)
   AGENTCORE_RUNTIME_URL=https://bedrock-agentcore.us-west-2.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-west-2%3A218208277580%3Aruntime%2Fambient_agent-n6N2Bc8jhN/invocations?qualifier=DEFAULT

   # Cognito Configuration (get from your Cognito User Pool)
   COGNITO_USER_POOL_ID=us-west-2_XXXXXXXXX
   COGNITO_CLIENT_ID=your_cognito_client_id
   COGNITO_USERNAME=your_username
   COGNITO_PASSWORD=your_password

   # Slack Webhook (from Step 1)
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   ```

### How to Find Cognito Values

1. Go to AWS Console → Cognito → User Pools
2. Select your user pool
3. **User Pool ID**: Found in "User pool overview"
4. **Client ID**: Go to "App integration" → "App clients" → Select your client

## Step 3: Deploy the Lambda Function

Run the deployment script:

```bash
cd deployment
chmod +x deploy_lambda.sh
./deploy_lambda.sh
```

The script will:
1. ✅ Create IAM role for Lambda with necessary permissions
2. ✅ Package the Lambda function code
3. ✅ Create/update the Lambda function
4. ✅ Create EventBridge rule (every 15 minutes)
5. ✅ Connect EventBridge to Lambda

## Step 4: Verify Deployment

### Test Lambda Function Manually

```bash
aws lambda invoke \
    --function-name ambient-agent-scheduled-monitor \
    /tmp/response.json && cat /tmp/response.json
```

Check your Slack channel - you should see a monitoring report!

### View Lambda Logs

```bash
aws logs tail /aws/lambda/ambient-agent-scheduled-monitor --follow
```

### Check EventBridge Rule

```bash
aws events describe-rule --name ambient-agent-15min-check
```

## Step 5: Monitor and Troubleshoot

### Common Issues

#### 1. Cognito Authentication Failed

**Error:** `An error occurred (NotAuthorizedException) when calling the InitiateAuth operation`

**Solution:**
- Verify your Cognito credentials in `.env`
- Ensure the App Client has `USER_PASSWORD_AUTH` flow enabled:
  ```bash
  aws cognito-idp update-user-pool-client \
      --user-pool-id YOUR_POOL_ID \
      --client-id YOUR_CLIENT_ID \
      --explicit-auth-flows USER_PASSWORD_AUTH
  ```

#### 2. AgentCore Request Failed

**Error:** `AgentCore request failed: 401`

**Solution:**
- Check that the Cognito token is valid
- Verify the AgentCore URL is correct
- Ensure the Cognito user has permissions to invoke the AgentCore runtime

#### 3. Slack Webhook Failed

**Error:** `Slack post failed: 404`

**Solution:**
- Verify the webhook URL in `.env`
- Check that the Slack App still has the webhook active
- Test the webhook manually:
  ```bash
  curl -X POST $SLACK_WEBHOOK_URL \
      -H 'Content-Type: application/json' \
      -d '{"text":"Test message"}'
  ```

### View CloudWatch Logs

1. Go to AWS Console → CloudWatch → Log groups
2. Find `/aws/lambda/ambient-agent-scheduled-monitor`
3. View the latest log stream

## What Happens Now?

✅ **Every 15 minutes**, the Lambda function will:
1. Retrieve a Cognito authentication token
2. Call your AgentCore runtime with a monitoring prompt
3. Receive the agent's analysis of CloudWatch alarms and resource health
4. Format the response into a nice Slack message
5. Post it to your configured Slack channel

## Customization

### Change Schedule Frequency

Edit `deployment/deploy_lambda.sh` and change the schedule expression:

```bash
# Current: Every 15 minutes
--schedule-expression "rate(15 minutes)"

# Options:
--schedule-expression "rate(5 minutes)"   # Every 5 minutes
--schedule-expression "rate(1 hour)"      # Every hour
--schedule-expression "cron(0 9 * * ? *)" # Daily at 9 AM UTC
```

Then re-run the deployment script.

### Customize the Monitoring Prompt

Edit `lambda/scheduled_monitor.py` and modify the `agent_payload`:

```python
agent_payload = {
    "prompt": "Your custom monitoring prompt here",
    "session_id": f"scheduled-{datetime.now().strftime('%Y%m%d-%H%M')}"
}
```

### Change Slack Message Format

Edit the `format_slack_message()` function in `lambda/scheduled_monitor.py` to customize the Slack message layout.

## Cost Estimate

**Monthly costs for this setup:**
- Lambda (15 min schedule): ~$1-2/month
- EventBridge: $0.10/month
- CloudWatch Logs: ~$0.50-1/month
- AgentCore + Bedrock: ~$50-100/month (depends on usage)

**Total: ~$52-103/month**

## Updating the Deployment

When you make changes to the Lambda function:

```bash
cd deployment
./deploy_lambda.sh
```

The script will automatically update the existing Lambda function with your changes.

## Cleaning Up

To remove all resources:

```bash
# Delete EventBridge rule
aws events remove-targets --rule ambient-agent-15min-check --ids 1
aws events delete-rule --name ambient-agent-15min-check

# Delete Lambda function
aws lambda delete-function --function-name ambient-agent-scheduled-monitor

# Delete IAM role (detach policies first)
aws iam detach-role-policy \
    --role-name ambient-agent-lambda-role \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws iam detach-role-policy \
    --role-name ambient-agent-lambda-role \
    --policy-arn arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/AmbientAgentLambdaPolicy

aws iam delete-role --role-name ambient-agent-lambda-role

# Delete custom policy
aws iam delete-policy \
    --policy-arn arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/AmbientAgentLambdaPolicy
```

## Next Steps

### Add Interactive Slack Commands

In the future, you can extend this to support interactive slash commands like:
- `/aws-status` - Get current AWS status on-demand
- `/aws-logs [service]` - Fetch logs for a specific service
- `/aws-alarms` - List active alarms

This would require:
1. Additional Lambda function for command handling
2. API Gateway to receive Slack requests
3. Slack request signature verification

Let me know if you want to implement this next!

## Support

If you encounter issues:
1. Check CloudWatch Logs for error messages
2. Verify all environment variables are set correctly
3. Test each component individually (Cognito auth, AgentCore call, Slack webhook)
4. Review the Lambda function execution role permissions

---

**Deployed Successfully?** 🎉

Your ambient agent should now be posting AWS monitoring updates to Slack every 15 minutes!
