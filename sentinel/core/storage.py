import shelve
import json
import logging
import os
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class BlockchainStateStore:
    """
    Blockchain state persistent storage
    
    Uses Python's shelve module to store blockchain processing state, including:
    - Last processed block number for each network
    - Configuration information for each collector
    - Processing statistics
    """
    
    def __init__(self, db_path: str):
        """
        Initialize state storage
        
        Args:
            db_path: Database path
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
            # Store the path for later use
            self.db_path = db_path
            self.db = None
            
            # Open the database
            self._open_db()
            logger.info(f"Initialized blockchain state store at {db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize storage at {db_path}: {e}")
            raise
    
    def _open_db(self):
        """Open the database connection"""
        if self.db is None:
            try:
                self.db = shelve.open(self.db_path)
            except Exception as e:
                logger.error(f"Error opening database: {e}")
                raise
    
    def _ensure_db_open(self):
        """Ensure database is open"""
        if self.db is None:
            self._open_db()
    
    def get_last_processed_block(self, network: str) -> Optional[int]:
        """
        Get the last processed block for a network
        
        Args:
            network: Network name
            
        Returns:
            Optional[int]: Last processed block number, or None if not found
        """
        key = f"last_block:{network}"
        try:
            self._ensure_db_open()
            return int(self.db[key]) if key in self.db else None
        except Exception as e:
            logger.error(f"Error retrieving last processed block for {network}: {e}")
            return None
    
    def set_last_processed_block(self, network: str, block_number: int):
        """
        Set the last processed block for a network
        
        Args:
            network: Network name
            block_number: Block number
        """
        key = f"last_block:{network}"
        try:
            self._ensure_db_open()
            self.db[key] = str(block_number)
            self.db.sync()
        except Exception as e:
            logger.error(f"Error setting last processed block for {network}: {e}")
    
    def store_collector_stats(self, collector_id: str, stats: Dict[str, Any]):
        """
        Store collector statistics
        
        Args:
            collector_id: Collector unique identifier
            stats: Statistics dictionary
        """
        key = f"stats:{collector_id}"
        try:
            self._ensure_db_open()
            self.db[key] = json.dumps(stats)
            self.db.sync()
        except Exception as e:
            logger.error(f"Error storing stats for collector {collector_id}: {e}")
    
    def get_collector_stats(self, collector_id: str) -> Optional[Dict[str, Any]]:
        """
        Get collector statistics
        
        Args:
            collector_id: Collector unique identifier
            
        Returns:
            Optional[Dict[str, Any]]: Statistics dictionary, or None if not found
        """
        key = f"stats:{collector_id}"
        try:
            self._ensure_db_open()
            value = self.db.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            logger.error(f"Error retrieving stats for collector {collector_id}: {e}")
            return None
    
    def handle_block_reorg(self, network: str, confirmed_block: int):
        """
        Handle blockchain reorganization by reverting to a confirmed block
        
        Args:
            network: Network name
            confirmed_block: Confirmed block number to revert to
        """
        current = self.get_last_processed_block(network) or 0
        if confirmed_block < current:
            logger.warning(f"Block reorg detected on {network}. Rewinding from {current} to {confirmed_block}")
            self.set_last_processed_block(network, confirmed_block)
    
    def create_checkpoint(self, network: str, block: int, timestamp: str):
        """
        Create a checkpoint of the current state
        
        Args:
            network: Network name
            block: Current block number
            timestamp: ISO-formatted timestamp
        """
        key = f"checkpoint:{network}:{timestamp}"
        try:
            self._ensure_db_open()
            self.db[key] = str(block)
            self.db.sync()
        except Exception as e:
            logger.error(f"Error creating checkpoint for {network} at {timestamp}: {e}")
    
    def close(self):
        """Close the database connection"""
        if hasattr(self, 'db') and self.db is not None:
            try:
                self.db.close()
                self.db = None
                logger.info("Blockchain state store closed")
            except Exception as e:
                logger.error(f"Error closing blockchain state store: {e}") 