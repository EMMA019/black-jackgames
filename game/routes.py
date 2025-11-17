"""
API routes for the BlackJack game blueprint.

This module defines the WebSocket event handlers for the BlackJack game.
It interacts with the core game logic (`game/logic.py`) and uses Redis
for scalable, persistent session management.
"""
from flask import Blueprint, request, jsonify, render_template, current_app
from flask_socketio import emit, join_room, leave_room, disconnect
import logging
import json
import eventlet

from .logic import GameSession, DIFFICULTY, GamePhase
from extensions import socketio, db, redis_client
from models import User
from utils import get_session_id_from_request

logger = logging.getLogger(__name__)

game_bp = Blueprint(
    'game', 
    __name__,
    template_folder='../templates',
    static_folder='../static'
)

# --- Redis Session Helpers ---
REDIS_GAME_KEY_PREFIX = "blackjack:session:"
REDIS_SESSION_TTL = 7200 

def get_game_session(sid: str) -> GameSession | None:
    if not redis_client:
        logger.error("Redis client is not available.")
        return None
    
    key = f"{REDIS_GAME_KEY_PREFIX}{sid}"
    try:
        session_data_json = redis_client.get(key)
        if session_data_json:
            session_data = json.loads(session_data_json)
            redis_client.expire(key, REDIS_SESSION_TTL)
            return GameSession.from_dict(session_data)
    except Exception as e:
        logger.exception(f"Failed to retrieve or deserialize session {sid} from Redis: {e}")
    return None

def save_game_session(game_session: GameSession):
    if not redis_client:
        logger.error("Redis client is not available.")
        return

    key = f"{REDIS_GAME_KEY_PREFIX}{game_session.session_id}"
    try:
        session_data = game_session.to_dict()
        session_data_json = json.dumps(session_data)
        redis_client.set(key, session_data_json, ex=REDIS_SESSION_TTL)
    except Exception as e:
        logger.exception(f"Failed to serialize or save session {game_session.session_id} to Redis: {e}")

def delete_game_session(sid: str):
    if not redis_client:
        return
    key = f"{REDIS_GAME_KEY_PREFIX}{sid}"
    try:
        redis_client.delete(key)
    except Exception as e:
        logger.exception(f"Failed to delete session {sid} from Redis: {e}")

# --- HTTP Route for serving the game ---
@game_bp.route('/')
def index():
    return render_template('index.html')


# --- SocketIO Event Handlers ---

@socketio.on('connect')
def connect():
    sid = get_session_id_from_request()
    if not sid:
        return
        
    join_room(sid)
    logger.info(f"Client connected: {sid}. Joined room {sid}")
    
    game_session = get_game_session(sid)
    if game_session:
        logger.info(f"Resuming existing game session for {sid}.")
        hide_card = game_session.phase not in [GamePhase.ROUND_END, GamePhase.GAME_OVER]
        _send_game_state(sid, hide_card)
    else:
        logger.info(f"No existing session found for {sid}. Awaiting start_game.")
        socketio.emit('awaiting_start', {'message': 'Please start a new game.'})


@socketio.on('disconnect')
def disconnect_handler():
    sid = get_session_id_from_request()
    if not sid:
        return

    game_session = get_game_session(sid)
    if game_session:
        try:
            app = current_app._get_current_object()
            with app.app_context():
                user = User.query.filter_by(username="Player").first()
                if user:
                    user.update_balance(game_session.player.balance)
                logger.info(f"Client {sid} disconnected. Final balance {game_session.player.balance} persisted to DB.")
        except Exception as e:
            logger.error(f"Failed to persist balance for {sid} on disconnect: {e}")
    else:
        logger.info(f"Client disconnected: {sid}. No active game session found.")
    
    leave_room(sid)


def _send_game_state(sid: str, hide_dealer_first_card: bool = True):
    game_session = get_game_session(sid)
    if game_session:
        state = game_session.get_game_state(hide_dealer_first_card)
        socketio.emit('game_state_update', state, room=sid)
        logger.debug(f"Emitted game_state_update to {sid} for phase {state['phase']}")
    else:
        logger.warning(f"Attempted to send state to non-existent session: {sid}")
        emit('error', {'message': 'Game session not found. Please restart.'}, room=sid)


@socketio.on('start_game')
def start_game_event(data: dict):
    sid = get_session_id_from_request()
    if not sid:
        emit('error', {'message': 'No session ID found.'})
        return

    difficulty_str = data.get('difficulty', 'MEDIUM').upper()
    bet_amount = data.get('bet_amount')

    try:
        difficulty = DIFFICULTY[difficulty_str]
    except KeyError:
        emit('error', {'message': 'Invalid difficulty level.'}, room=sid)
        return
    
    if not isinstance(bet_amount, int) or bet_amount <= 0:
        emit('error', {'message': 'Bet amount must be a positive integer.'}, room=sid)
        return

    game_session = get_game_session(sid)
    
    try:
        user = User.get_or_create(username="Player")
        initial_balance = user.balance

        if not game_session or game_session.phase in [GamePhase.ROUND_END, GamePhase.GAME_OVER]:
            if game_session and game_session.phase == GamePhase.GAME_OVER:
                logger.info(f"Player {sid} is starting a new game after Game Over.")
                initial_balance = user.balance if user.balance > 0 else 1000
                if initial_balance == 0: initial_balance = 1000 # Failsafe
                
            game_session = GameSession(sid, difficulty, initial_balance=initial_balance)
        
        game_session.start_round(bet_amount)
        save_game_session(game_session)
        user.update_balance(game_session.player.balance)

        _send_game_state(sid, hide_dealer_first_card=True)
        logger.info(f"Game round started for {sid}.")

        # --- ★ バグ修正 ★ ---
        # プレイヤーのターンがスキップされた場合（例: ブラックジャック）
        # AI/ディーラーのターンを自動的に開始します。
        if (game_session.phase != GamePhase.PLAYER_TURN and
            game_session.phase != GamePhase.WAITING_FOR_BET and
            game_session.phase != GamePhase.GAME_OVER):
            
            logger.info(f"Player turn skipped (e.g. Blackjack). Starting AI/Dealer turns.")
            app = current_app._get_current_object()
            eventlet.spawn(_play_ai_and_dealer_turns, sid, app)
        # --- ★ 修正完了 ★ ---

    except (ValueError, IndexError) as e:
        db.session.rollback()
        logger.warning(f"Error starting game for {sid}: {e}")
        emit('error', {'message': str(e)}, room=sid)
    except Exception as e:
        db.session.rollback()
        logger.exception(f"Unexpected error during game start for {sid}")
        emit('error', {'message': 'An unexpected error occurred. Please try again.'}, room=sid)


@socketio.on('player_action')
def player_action_event(data: dict):
    sid = get_session_id_from_request()
    if not sid:
        emit('error', {'message': 'No session ID found.'})
        return

    game_session = get_game_session(sid)
    if not game_session:
        emit('error', {'message': 'No active game session. Please start a new game.'}, room=sid)
        return
    
    if game_session.phase != GamePhase.PLAYER_TURN:
        emit('error', {'message': 'It is not your turn to act.'}, room=sid)
        return

    action = data.get('action')
    if action not in ['hit', 'stand']:
        emit('error', {'message': 'Invalid player action.'}, room=sid)
        return

    try:
        if action == 'hit':
            game_session.player_hit()
        elif action == 'stand':
            game_session.player_stand()
        
        save_game_session(game_session)
        _send_game_state(sid, hide_dealer_first_card=True)

        # プレイヤーのターンが終了した場合 (Hitで21、Bust、またはStand)
        if game_session.phase != GamePhase.PLAYER_TURN:
            app = current_app._get_current_object()
            eventlet.spawn(_play_ai_and_dealer_turns, sid, app)

    except (ValueError, IndexError) as e:
        logger.warning(f"Action '{action}' error for {sid}: {e}")
        emit('error', {'message': str(e)}, room=sid)
    except Exception as e:
        logger.exception(f"Unexpected error during player action '{action}' for {sid}")
        emit('error', {'message': 'An unexpected error occurred. Please try again.'}, room=sid)


def _play_ai_and_dealer_turns(sid: str, app): 
    """
    Helper function to sequentially play AI and Dealer turns.
    This *must* run within an app_context to use the database.
    """
    with app.app_context():
        try:
            # --- AI Turn ---
            game_session = get_game_session(sid)
            if not game_session or game_session.phase != GamePhase.AI_TURN:
                logger.warning(f"Skipping AI turn for {sid}, invalid phase.")
                return

            eventlet.sleep(1) # Small delay for UX
            game_session.play_ai_turn()
            save_game_session(game_session)
            _send_game_state(sid, hide_dealer_first_card=True)
            
            # --- Dealer Turn ---
            game_session = get_game_session(sid) # Re-fetch
            if not game_session or game_session.phase != GamePhase.DEALER_TURN:
                logger.warning(f"Skipping Dealer turn for {sid}, invalid phase.")
                return

            eventlet.sleep(1) # Small delay for UX
            game_session.play_dealer_turn()
            
            save_game_session(game_session)
            _send_game_state(sid, hide_dealer_first_card=False) # Reveal cards

            # DB操作は app_context の中で安全に行われる
            user = User.query.filter_by(username="Player").first()
            if user:
                user.update_balance(game_session.player.balance)

            if game_session.phase == GamePhase.GAME_OVER:
                emit('game_over', {'message': 'You ran out of money! Game Over.'}, room=sid)
                logger.info(f"Game Over for {sid} due to insufficient funds.")

        except (ValueError, IndexError) as e:
            db.session.rollback()
            logger.warning(f"AI/Dealer turn error for {sid}: {e}")
            emit('error', {'message': str(e)}, room=sid)
        except Exception as e:
            db.session.rollback()
            logger.exception(f"Unexpected error during AI/Dealer turn for {sid}")
            emit('error', {'message': 'An unexpected error occurred during AI/Dealer turn.'}, room=sid)


@socketio.on('reset_game')
def reset_game_event():
    sid = get_session_id_from_request()
    if not sid:
        emit('error', {'message': 'No session ID found.'})
        return
    
    try:
        user = User.get_or_create(username="Player")
        user.update_balance(1000)
        
        game_session = get_game_session(sid)
        
        if not game_session:
            game_session = GameSession(sid, DIFFICULTY.MEDIUM, user.balance)
        else:
            game_session.reset_game(initial_balance=user.balance)
        
        save_game_session(game_session)
        _send_game_state(sid, hide_dealer_first_card=True)
        logger.info(f"Game session {sid} reset successfully.")

    except Exception as e:
        db.session.rollback()
        logger.exception(f"Unexpected error during game reset for {sid}")
        emit('error', {'message': 'An unexpected error occurred during game reset.'}, room=sid)