# AgentWatch CloudFormation Deployment

One-click deployment for AgentWatch AWS CloudWatch Monitoring Agent with Slack integration.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CloudFormation Stack                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐ │
│  │   Slack     │───▶│ API Gateway │───▶│    Lambda Function      │ │
│  │  /ask cmd   │    │  /slack-cmd │    │  (scheduled_monitor)    │ │
│  └─────────────┘    └─────────────┘    └───────────┬─────────────┘ │
│                                                     │               │
│  ┌─────────────┐                                   │               │
│  │ EventBridge │───────────────────────────────────┘               │
│  │ (15 min)    │                                                    │
│  └─────────────┘                                   │               │
│                                                     ▼               │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐ │
│  │  Cognito    │───▶│   OAuth2    │───▶│   AgentCore Runtime     │ │
│  │  User Pool  │    │   Token     │    │   (Bedrock Agent)       │ │
│  └─────────────┘    └─────────────┘    └─────────────────────────┘ │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- AWS CLI configured with appropriate credentials
- Python 3.10+ (for AgentCore CLI)
- Slack App with:
  - Incoming Webhook URL
  - Signing Secret
  - Slash Command capability

## Quick Start

### Option 1: Interactive Script (Recommended)

```bash
cd deployment/cloudformation
./deploy-stack.sh
```

### Option 2: AWS CLI

```bash
aws cloudformation deploy \
  --template-file cloudformation.yaml \
  --stack-name agentwatch \
  --parameter-overrides \
    SlackWebhookUrl="https://hooks.slack.com/services/XXX/YYY/ZZZ" \
    SlackSigningSecret="your-signing-secret" \
    CognitoDomainPrefix="agentwatch-123456" \
  --capabilities CAPABILITY_NAMED_IAM
```

### Option 3: AWS Console

1. Go to **CloudFormation** in AWS Console
2. Click **Create Stack** → **With new resources**
3. Upload `cloudformation.yaml`
4. Fill in parameters
5. Acknowledge IAM capabilities
6. Create stack

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `SlackWebhookUrl` | Yes | Slack incoming webhook URL |
| `SlackSigningSecret` | Yes | Slack app signing secret |
| `CognitoDomainPrefix` | Yes | Unique prefix for Cognito domain (lowercase, alphanumeric) |
| `AgentCoreRuntimeUrl` | No | AgentCore URL (add after AgentCore deployment) |
| `MonitoringSchedule` | No | Schedule frequency (default: 15 minutes) |

## Post-Deployment Steps

### 1. Deploy AgentCore Runtime

```bash
# From project root
pip install bedrock-agentcore-starter-toolkit
agentcore launch --agent AgentWatch
```

### 2. Update Stack with AgentCore URL

```bash
aws cloudformation update-stack \
  --stack-name agentwatch \
  --use-previous-template \
  --parameters \
    ParameterKey=SlackWebhookUrl,UsePreviousValue=true \
    ParameterKey=SlackSigningSecret,UsePreviousValue=true \
    ParameterKey=CognitoDomainPrefix,UsePreviousValue=true \
    ParameterKey=AgentCoreRuntimeUrl,ParameterValue="YOUR_AGENTCORE_URL" \
  --capabilities CAPABILITY_NAMED_IAM
```

### 3. Configure Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Select your app → **Slash Commands**
3. Create `/ask` command
4. Set Request URL to stack output `SlackCommandEndpoint`

### 4. Add AgentCore IAM Permissions

```bash
aws iam put-role-policy \
  --role-name <YOUR_AGENTCORE_ROLE> \
  --policy-name CloudWatchMonitoringAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": [
        "cloudwatch:DescribeAlarms",
        "cloudwatch:ListDashboards",
        "cloudwatch:GetDashboard",
        "logs:DescribeLogGroups",
        "logs:FilterLogEvents",
        "logs:GetLogEvents"
      ],
      "Resource": "*"
    }]
  }'
```

## Stack Outputs

| Output | Description |
|--------|-------------|
| `SlackCommandEndpoint` | URL for Slack slash command |
| `CognitoDomainUrl` | Cognito OAuth2 endpoint |
| `M2MClientId` | Client ID for authentication |
| `M2MSecretArn` | Secrets Manager ARN |

## Resources Created

- **Cognito User Pool** - M2M authentication
- **Lambda Function** - Monitoring and Slack integration
- **API Gateway** - Slack slash commands endpoint
- **EventBridge Rule** - Scheduled monitoring (15 min)
- **Secrets Manager** - M2M credentials storage
- **IAM Role** - Lambda execution permissions

## Deleting the Stack

```bash
aws cloudformation delete-stack --stack-name agentwatch
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Lambda timeout | Check AgentCore URL, verify Cognito credentials |
| Slack not receiving | Verify webhook URL, check Lambda logs |
| Auth failures | Check M2M secret, verify Cognito domain |
| AgentCore errors | Run `agentcore launch`, check IAM permissions |

## Cost Estimate

~$5-10/month (Lambda, API Gateway, Cognito, EventBridge, Secrets Manager)

*AgentCore runtime costs are separate.*