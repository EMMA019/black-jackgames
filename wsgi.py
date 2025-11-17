"""
WSGI entry point for deploying the Flask BlackJack application.

This file is responsible for creating the app instance,
registering blueprints, and running the server.
"""
import eventlet
from eventlet import wsgi
import logging
import os
import sys

# --- 修正点 1: プロジェクトルートをパスに追加 ---
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# --- 修正完了 ---

# Patch standard library for async operations
eventlet.monkey_patch()

from app import create_app
from config import CurrentConfig

logger = logging.getLogger(__name__)

# --- 修正点 2: アプリケーションの構築とBlueprintの登録 ---
# 1. アプリのコア（拡張機能など）を作成
app = create_app()

# 2. アプリが作成された *後で*、Blueprintをインポート
#    (wsgi.pyがパスを追加したので、ここで見つかるはずです)
from game.routes import game_bp

# 3. アプリにBlueprintを登録
app.register_blueprint(game_bp)
logger.info("Game blueprint registered successfully.")
# --- 修正完了 ---


if __name__ == '__main__':
    logger.info("Starting Eventlet WSGI server for local development...")
    
    host = '0.0.0.0'
    port = int(os.environ.get('PORT', 5000))
    
    try:
        from extensions import socketio
        logger.info(f"SocketIO server starting on {host}:{port}")
        socketio.run(app, host=host, port=port)
        
    except Exception as e:
        logger.critical(f"Failed to start WSGI server: {e}")