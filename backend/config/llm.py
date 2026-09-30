import asyncio

from dotenv import load_dotenv
from config.settings import LLM_MODEL_NAME, GEMINI_RPM
from langchain_google_genai import ChatGoogleGenerativeAI
from aiolimiter import AsyncLimiter
from utils.resilience import with_resilience


load_dotenv()

CALL_TIMEOUT_SECONDS = 60

gemini_limiter = AsyncLimiter(GEMINI_RPM, time_period=60)

model = ChatGoogleGenerativeAI(
    model=LLM_MODEL_NAME,
    max_retries=0,
)


@with_resilience(timeout=None)
async def rate_limited_ainvoke(runnable, *args, **kwargs):
    """
    Every Gemini call in the app should go through this, not runnable.ainvoke
    directly. Enforces a global RPM cap regardless of how many tickets or
    issues are in flight concurrently. Retries also go through the limiter.
    """
    
    async with gemini_limiter:
        return await asyncio.wait_for(
            runnable.ainvoke(*args, **kwargs),
            timeout=CALL_TIMEOUT_SECONDS,
        )