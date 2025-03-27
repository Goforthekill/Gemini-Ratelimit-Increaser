# key_manager.py - Remains the same
import os
import threading
from itertools import cycle
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ApiKeyManager:
    def __init__(self):
        load_dotenv()
        keys_str = os.getenv("GEMINI_API_KEYS")
        if not keys_str:
            raise ValueError("GEMINI_API_KEYS environment variable not set or empty.")
        self.api_keys = [key.strip() for key in keys_str.split(',') if key.strip()]
        if not self.api_keys:
            raise ValueError("No valid API keys found in GEMINI_API_KEYS.")
        logging.info(f"Loaded {len(self.api_keys)} API keys.")
        self._key_cycler = cycle(self.api_keys)
        self._current_key = next(self._key_cycler)
        self._lock = threading.Lock()

    def get_key(self):
        with self._lock:
            return self._current_key

    def rotate_key(self):
        with self._lock:
            old_key_short = self._current_key[:4] + "..." + self._current_key[-4:]
            self._current_key = next(self._key_cycler)
            new_key_short = self._current_key[:4] + "..." + self._current_key[-4:]
            logging.warning(f"Rotating API key from {old_key_short} to {new_key_short} due to rate limit.")
            return self._current_key

key_manager = ApiKeyManager()