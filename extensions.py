"""
Application extensions and shared objects.

This module centralizes the initialization of Flask extensions like SQLAlchemy,
SocketIO, and Redis. This adheres to the `CIRCULAR_IMPORT_BAN` rule by providing
a single, importable source for these objects.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from redis import Redis
from config import CurrentConfig
import logging

logger = logging.getLogger(__name__)

# Initialize SQLAlchemy without an app
db = SQLAlchemy()

# Initialize SocketIO without an app
socketio = SocketIO(cors_allowed_origins="*", async_mode='eventlet')

# Initialize Redis client
try:
    # `decode_responses=True` is crucial for working with JSON strings
    redis_client = Redis.from_url(CurrentConfig.REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("Redis client connected successfully.")
except Exception as e:
    logger.error(f"Failed to connect to Redis at {CurrentConfig.REDIS_URL}: {e}")
    redis_client = None