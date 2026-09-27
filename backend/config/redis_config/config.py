from dotenv import load_dotenv
import os

from redis import Redis

load_dotenv()

redis_host = os.getenv("REDIS_HOST")
redis_password = os.getenv("REDIS_PASSWORD")

redis_client = Redis(
    host=redis_host,
    port=15532,
    decode_responses=True,
    username="default",
    password=redis_password,
)