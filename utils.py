"""
Utility functions and logging configuration for the BlackJack application.
"""
import logging
from config import CurrentConfig

def setup_logging():
    """
    Configures the application's logging.
    
    Sets up a basic console handler with a formatter and sets the log level
    based on `CurrentConfig.LOG_LEVEL`. This function should be called during
    application initialization.
    """
    log_level = getattr(logging, CurrentConfig.LOG_LEVEL, logging.INFO)
    
    # Use basicConfig for simplicity, it's safe to call early.
    # It only configures the root logger if no handlers are already configured.
    logging.basicConfig(
        level=log_level,
        format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Suppress noisy logs from third-party libraries
    logging.getLogger('socketio').setLevel(logging.WARNING)
    logging.getLogger('engineio').setLevel(logging.WARNING)
    logging.getLogger('redis').setLevel(logging.WARNING)
    
    logging.info(f"Logging initialized with level: {CurrentConfig.LOG_LEVEL}")


def get_session_id_from_request():
    """
    Retrieves the unique session ID for the current client request (SocketIO).
    """
    from flask import request
    # For SocketIO, request.sid is the unique ID for the client connection.
    return request.sid if hasattr(request, 'sid') else None