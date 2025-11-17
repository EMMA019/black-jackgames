"""
Configuration settings for the Flask application.

This module defines the `Config` class, which manages application-wide settings
including security keys, database URIs, and logging configurations.
It adheres to the `FAIL_FAST_CONFIG` and `DOTENV_SECURITY` rules by
ensuring critical settings like `SECRET_KEY` are present and by separating
secrets from general configuration flags.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
# This ensures that secrets are loaded from the correct place.
load_dotenv()

class Config:
    """
    Base configuration class for the Flask application.
    """
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        # FAIL_FAST_CONFIG: Ensure SECRET_KEY is set for security.
        raise ValueError("No SECRET_KEY set for Flask application. Did you forget to set it in .env?")

    # DOTENV_SECURITY: DATABASE_URL is treated as a secret/sensitive configuration.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///blackjack.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False # Recommended to disable to save resources.

    # REDIS_URL for scalable session management
    # Defaults to a standard local Redis instance.
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')

    # Basic logging configuration for safety_first rule.
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()


class DevelopmentConfig(Config):
    """
    Development-specific configuration.
    """
    DEBUG = True # Use DEBUG only in development.


class ProductionConfig(Config):
    """
    Production-specific configuration.
    Ensures debug is off and uses robust database configuration.
    """
    DEBUG = False # PRODUCTION_SECURITY: Never hardcode debug=True.
    # In a real production app, DATABASE_URL and REDIS_URL must be set
    # in the production environment.


def get_config():
    """
    Dynamically retrieves the appropriate configuration class based on FLASK_ENV.
    """
    env = os.environ.get('FLASK_ENV', 'development')
    if env == 'production':
        return ProductionConfig
    elif env == 'development':
        return DevelopmentConfig
    else:
        raise ValueError(f"Unknown FLASK_ENV: {env}. Must be 'development' or 'production'.")

# Export the current configuration object
CurrentConfig = get_config()