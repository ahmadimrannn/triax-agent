from config.settings import LLM_MODEL_NAME
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()

model = ChatGoogleGenerativeAI(
    model=LLM_MODEL_NAME
)