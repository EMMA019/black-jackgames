"""
Database models for the BlackJack application.
This defines long-term persistent data, like User accounts.
Short-term session data is handled by Redis.
"""
from extensions import db
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class User(db.Model):
    """
    User model to store player information, primarily their balance.
    This balance is the *persistent* balance, loaded at the start of
    a game session.
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    balance = db.Column(db.Integer, nullable=False, default=1000) # Initial balance
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<User {self.username}>"

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'username': self.username,
            'balance': self.balance,
            'created_at': self.created_at.isoformat()
        }

    @classmethod
    def get_or_create(cls, username: str, initial_balance: int = 1000):
        """
        Retrieves a user by username or creates a new one if it doesn't exist.
        """
        user = cls.query.filter_by(username=username).first()
        if not user:
            try:
                user = cls(username=username, balance=initial_balance)
                db.session.add(user)
                db.session.commit()
                logger.info(f"Created new user: {username} with initial balance {initial_balance}")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to create user {username}: {e}")
                raise
        return user

    def update_balance(self, new_balance: int):
        """
        Updates the user's balance and commits to the database.
        """
        if new_balance < 0:
            logger.warning(f"Attempted to set negative balance for user {self.username}: {new_balance}")
            new_balance = 0 # Don't allow negative balance
            
        self.balance = new_balance
        try:
            db.session.commit()
            logger.info(f"User {self.username} balance updated to {new_balance}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update balance for {self.username}: {e}")
            raise