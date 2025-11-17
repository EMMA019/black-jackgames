"""
Main Flask application factory.
"""
import logging
from flask import Flask, request, jsonify, render_template
from config import CurrentConfig
from extensions import db, socketio, redis_client
from utils import setup_logging
import os

# --- 修正点 ---
# db.create_all() が User モデルを認識できるように、
# ここで明示的にインポートします。
import models 
# --- 修正完了 ---

logger = logging.getLogger(__name__)

def create_app() -> Flask:
    """
    Creates and configures the Flask application instance.
    NOTE: This factory *does not* register blueprints.
    Registration is handled by the WSGI entry point to avoid circular imports.
    """
    # Configure template and static folders
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(CurrentConfig)

    # Initialize logging early.
    setup_logging()
    logger.info(f"Application starting in {app.config['FLASK_ENV']} environment.")

    # Check for Redis connection
    if not redis_client:
        logger.critical("CRITICAL: Redis connection FAILED. Application cannot start.")
        raise RuntimeError("Failed to connect to Redis. Check REDIS_URL and server status.")

    # Initialize extensions (CIRCULAR_IMPORT_BAN)
    db.init_app(app)
    socketio.init_app(app)
    logger.info("Database and SocketIO extensions initialized.")

    with app.app_context():
        # Create database tables if they don't exist.
        try:
            # models.py がインポート済みなので、ここで 'user' テーブルが作成されます
            db.create_all()
            logger.info("Database tables checked/created.")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    # @app.route('/') # <-- このルートは game_bp にあります
    
    # Health check for load balancers
    @app.route('/health')
    def health_check():
        try:
            # Check DB connection
            db.session.execute('SELECT 1')
            # Check Redis connection
            redis_client.ping()
            return jsonify({'status': 'ok', 'database': 'ok', 'redis': 'ok'}), 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 503

    # Error handler for 404 (Not Found)
    @app.errorhandler(404)
    def not_found_error(error):
        logger.warning(f"404 Not Found: {request.path}")
        return jsonify({'error': 'Not Found', 'message': f'The requested URL {request.path} was not found on the server.'}), 404

    # Error handler for 500 (Internal Server Error)
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback() # Rollback any pending database transactions
        logger.exception("500 Internal Server Error.")
        return jsonify({'error': 'Internal Server Error', 'message': 'An unexpected error occurred.'}), 500

    logger.info("Flask application created and configured.")
    return app