from langfuse import get_client
from langfuse.langchain import CallbackHandler
from dotenv import load_dotenv

load_dotenv()

# Initialize Langfuse client
langfuse = get_client()

# Initialize Langfuse CallbackHandler for Langchain (tracing)
langfuse_handler = CallbackHandler()