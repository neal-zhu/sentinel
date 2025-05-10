"""
Token Storage Module

Provides persistent storage solutions for token tracking with multiple backend options.
"""

import json
import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sentinel.logger import logger


class TokenStorage(ABC):
    """Abstract base class for token storage implementations"""

    @abstractmethod
    def add_token(self, chain_id: int, token_address: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Add a token to storage
        
        Args:
            chain_id: The blockchain ID
            token_address: The token contract address
            metadata: Optional metadata about the token
            
        Returns:
            bool: True if token was added, False if already exists or error
        """
        pass
    
    @abstractmethod
    def contains_token(self, chain_id: int, token_address: str) -> bool:
        """
        Check if a token exists in storage
        
        Args:
            chain_id: The blockchain ID
            token_address: The token contract address
            
        Returns:
            bool: True if token exists, False otherwise
        """
        pass
    
    @abstractmethod
    def get_all_tokens(self) -> List[Tuple[int, str, Dict[str, Any]]]:
        """
        Get all tokens in storage
        
        Returns:
            List[Tuple[int, str, Dict[str, Any]]]: List of (chain_id, token_address, metadata) tuples
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close storage connection and perform cleanup"""
        pass


class JSONFileTokenStorage(TokenStorage):
    """Token storage implementation using JSON file"""
    
    def __init__(self, file_path: str):
        """
        Initialize JSON file token storage
        
        Args:
            file_path: Path to the JSON file
        """
        self.file_path = file_path
        self.tokens: Dict[str, Dict[str, Any]] = {}
        self._load()
        
    def _load(self) -> None:
        """Load tokens from file"""
        if not os.path.exists(self.file_path):
            self.tokens = {}
            return
            
        try:
            with open(self.file_path, "r") as f:
                data = json.load(f)
                self.tokens = data.get("tokens", {})
                logger.info(f"Loaded {len(self.tokens)} tokens from {self.file_path}")
        except Exception as e:
            logger.error(f"Error loading tokens from {self.file_path}: {e}")
            self.tokens = {}
            
    def _save(self) -> None:
        """Save tokens to file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(os.path.abspath(self.file_path)), exist_ok=True)
            
            with open(self.file_path, "w") as f:
                json.dump({"tokens": self.tokens}, f, indent=2)
                logger.info(f"Saved {len(self.tokens)} tokens to {self.file_path}")
        except Exception as e:
            logger.error(f"Error saving tokens to {self.file_path}: {e}")
            
    def _get_key(self, chain_id: int, token_address: str) -> str:
        """Get storage key for a token"""
        return f"{chain_id}:{token_address.lower()}"
        
    def add_token(self, chain_id: int, token_address: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Add a token to storage"""
        key = self._get_key(chain_id, token_address)
        
        if key in self.tokens:
            return False
            
        self.tokens[key] = {
            "chain_id": chain_id,
            "address": token_address.lower(),
            "first_seen": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        self._save()
        return True
        
    def contains_token(self, chain_id: int, token_address: str) -> bool:
        """Check if a token exists in storage"""
        key = self._get_key(chain_id, token_address)
        return key in self.tokens
        
    def get_all_tokens(self) -> List[Tuple[int, str, Dict[str, Any]]]:
        """Get all tokens in storage"""
        result = []
        for token_data in self.tokens.values():
            result.append((
                token_data["chain_id"],
                token_data["address"],
                token_data.get("metadata", {})
            ))
        return result
        
    def close(self) -> None:
        """Close storage connection"""
        self._save()


class SQLiteTokenStorage(TokenStorage):
    """Token storage implementation using SQLite database"""
    
    def __init__(self, db_path: str):
        """
        Initialize SQLite token storage
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        
        # Connect to database and create tables if needed
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        
    def _create_tables(self) -> None:
        """Create necessary database tables if they don't exist"""
        cursor = self.conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tokens (
            chain_id INTEGER NOT NULL,
            address TEXT NOT NULL,
            first_seen TEXT NOT NULL,
            metadata TEXT,
            PRIMARY KEY (chain_id, address)
        )
        ''')
        self.conn.commit()
        
    def add_token(self, chain_id: int, token_address: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Add a token to storage"""
        try:
            cursor = self.conn.cursor()
            
            # Check if token already exists
            cursor.execute(
                "SELECT 1 FROM tokens WHERE chain_id = ? AND address = ?",
                (chain_id, token_address.lower())
            )
            
            if cursor.fetchone():
                return False
                
            # Insert new token
            cursor.execute(
                "INSERT INTO tokens (chain_id, address, first_seen, metadata) VALUES (?, ?, ?, ?)",
                (
                    chain_id,
                    token_address.lower(),
                    datetime.now().isoformat(),
                    json.dumps(metadata or {})
                )
            )
            
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding token to SQLite storage: {e}")
            self.conn.rollback()
            return False
            
    def contains_token(self, chain_id: int, token_address: str) -> bool:
        """Check if a token exists in storage"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT 1 FROM tokens WHERE chain_id = ? AND address = ?",
                (chain_id, token_address.lower())
            )
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking if token exists in SQLite storage: {e}")
            return False
            
    def get_all_tokens(self) -> List[Tuple[int, str, Dict[str, Any]]]:
        """Get all tokens in storage"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT chain_id, address, metadata FROM tokens")
            
            result = []
            for row in cursor.fetchall():
                result.append((
                    row["chain_id"],
                    row["address"],
                    json.loads(row["metadata"])
                ))
                
            return result
        except Exception as e:
            logger.error(f"Error fetching tokens from SQLite storage: {e}")
            return []
            
    def close(self) -> None:
        """Close database connection"""
        try:
            self.conn.close()
        except Exception as e:
            logger.error(f"Error closing SQLite connection: {e}")


def create_token_storage(storage_config: Dict[str, Any]) -> TokenStorage:
    """
    Factory function to create a token storage instance based on configuration
    
    Args:
        storage_config: Storage configuration
        
    Returns:
        TokenStorage: Configured storage instance
        
    Raises:
        ValueError: If storage type is unknown
    """
    storage_type = storage_config.get("type", "json")
    
    if storage_type == "json":
        file_path = storage_config.get("file_path", "data/tokens.json")
        return JSONFileTokenStorage(file_path)
    elif storage_type == "sqlite":
        db_path = storage_config.get("db_path", "data/tokens.db")
        return SQLiteTokenStorage(db_path)
    else:
        raise ValueError(f"Unknown token storage type: {storage_type}") 