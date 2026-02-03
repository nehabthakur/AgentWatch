# MINIMAL IMPORTS AT MODULE LEVEL - Keep under 5 seconds for AgentCore init
import json
import logging
from typing import Dict, Any

# Initialize BedrockAgentCoreApp early - this is required at module level
from bedrock_agentcore.runtime import BedrockAgentCoreApp
app = BedrockAgentCoreApp()

# Conditionally import langsmith traceable decorator (optional observability)
try:
    from langsmith import traceable
except ImportError:
    # If langsmith not available, create a no-op decorator
    def traceable(func):
        return func

# Set up logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables for lazy-loaded components
monitoring_agent = None
_initialized = False
_config_data = None
_agent_system_prompt = None

def initialize_agent():
    """
    Initialize heavy components only when needed to prevent AgentCore timeout.
    This function is called on first request instead of at module load time.

    All heavy imports (boto3, langchain, langgraph, etc.) are deferred here.
    """
    global monitoring_agent, _initialized, _config_data, _agent_system_prompt

    if _initialized:
        return

    logger.info("Initializing agent components on first request...")

    # DEFERRED IMPORTS - These happen AFTER AgentCore runtime init completes
    import json
    import boto3
    from typing import List
    from botocore.config import Config
    from langchain_aws import ChatBedrock
    from langchain.agents import create_agent
    from langgraph.checkpoint.memory import MemorySaver

    # Import tools only when needed
    from tools import (
        list_cloudwatch_dashboards,
        get_dashboard_summary,
        list_log_groups,
        fetch_cloudwatch_logs_for_service,
        analyze_log_group,
        get_cloudwatch_alarms_for_service,
        setup_cross_account_access,
    )
    from utils import load_config, load_system_prompt
    from constants import CONFIG_FILE_FNAME

    # Load configuration
    logger.info("Loading configuration file...")
    _config_data = load_config(CONFIG_FILE_FNAME)
    logger.info(f"Loaded configuration: {json.dumps(_config_data, indent=4)}")

    agent_model_configuration = _config_data['model_information']
    agent_system_prompt_fpath = agent_model_configuration['system_prompt_fpath']
    _agent_system_prompt = load_system_prompt(agent_system_prompt_fpath)
    logger.info("Loaded agent system prompt")

    # Initialize the bedrock config
    bedrock_config = Config(
        read_timeout=300,  # 5 minutes - reasonable for long agent responses
        connect_timeout=15,
        retries={
            'max_attempts': 3,
            'mode': 'adaptive'
        }
    )

    # Create a boto3 client with custom timeout configuration
    bedrock_runtime_client = boto3.client(
        service_name='bedrock-runtime',
        region_name=boto3.session.Session().region_name or 'us-east-1',
        config=bedrock_config
    )

    # Initialize the model
    agent_model = ChatBedrock(
        client=bedrock_runtime_client,
        model=agent_model_configuration["model_id"],
        model_kwargs={
            "temperature": agent_model_configuration["inference_parameters"]["temperature"],
            "max_tokens": agent_model_configuration["inference_parameters"]["max_tokens"],
            "top_p": agent_model_configuration["inference_parameters"]["top_p"],
        }
    )
    logger.info(f"Initialized Amazon Bedrock model: {agent_model_configuration['model_id']}")

    monitoring_tools: List = [
        list_cloudwatch_dashboards,
        get_dashboard_summary,
        list_log_groups,
        fetch_cloudwatch_logs_for_service,
        analyze_log_group,
        get_cloudwatch_alarms_for_service,
        setup_cross_account_access,
    ]

    # Create checkpointer for conversation memory
    checkpointer = MemorySaver()

    # Create the agent with checkpointer
    monitoring_agent = create_agent(
        model=agent_model,
        tools=monitoring_tools,
        system_prompt=_agent_system_prompt,
        checkpointer=checkpointer
    )

    _initialized = True
    logger.info("Ambient monitoring agent created successfully with checkpointing enabled")

@traceable
@app.entrypoint
def agent_handler(payload: Dict[str, Any]) -> str:
    """
    Handle incoming payload and return agent response.

    Args:
        payload: Dictionary containing the user prompt
                 Expected format: {"prompt": "user question or instruction"}

    Returns:
        String response from the monitoring agent
    """
    try:
        # Extract the prompt from the payload
        user_prompt = payload.get("prompt")
        if not user_prompt:
            error_msg = "No 'prompt' field found in payload"
            logger.error(error_msg)
            return json.dumps({"error": error_msg})

        logger.info(f"Received prompt: {user_prompt}")

        # Initialize agent components lazily on first request
        initialize_agent()

        # Thread configuration for maintaining conversation state
        # You can make this dynamic based on session_id in payload if needed
        thread_id = payload.get("session_id", "default-session")
        thread_config = {"configurable": {"thread_id": thread_id}}

        # Invoke agent with the prompt
        result = monitoring_agent.invoke(
            {"messages": [{"role": "user", "content": user_prompt}]},
            thread_config
        )

        # Extract the final AI message content
        messages = result.get('messages', [])
        final_message = messages[-1] if messages else None

        if final_message and hasattr(final_message, 'content'):
            response_text = final_message.content
            logger.info("Agent response generated successfully")
            return response_text
        else:
            error_msg = "No valid response from agent"
            logger.error(error_msg)
            return json.dumps({"error": error_msg, "raw_result": str(result)})

    except Exception as e:
        error_msg = f"Error processing request: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({"error": error_msg})



if __name__ == "__main__":
    app.run()