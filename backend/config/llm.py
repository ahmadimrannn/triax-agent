from dotenv import load_dotenv
from config.settings import LLM_MODEL_NAME, GEMINI_RPM
from langchain_google_genai import ChatGoogleGenerativeAI
from aiolimiter import AsyncLimiter

load_dotenv()

gemini_limiter = AsyncLimiter(GEMINI_RPM, time_period=60)

model = ChatGoogleGenerativeAI(
    model=LLM_MODEL_NAME
)

async def rate_limited_ainvoke(runnable, *args, **kwargs):
    """
    Every Gemini call in the app should go through this, not runnable.ainvoke
    directly. Enforces a global 15 RPM cap regardless of how many tickets or
    issues are in flight concurrently.
    """
    async with gemini_limiter:
        return await runnable.ainvoke(*args, **kwargs)