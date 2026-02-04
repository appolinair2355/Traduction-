# config.py
import os
from dataclasses import dataclass

@dataclass
class Config:
    # API Telegram (Pyrogram)
    API_ID: int = int(os.getenv("API_ID", "29177661"))
    API_HASH: str = os.getenv("API_HASH", "a8639172fa8d35dbfd8ea46286d349ab")
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "7261458320:AAHpUmO1iXG03ACWP0doh7ylEISewmmPL4A")
    
    # Configuration des canaux (SUPERGROUP/SUBCHANNEL IDs)
    # Enlever le -100 et garder juste le nombre pour Pyrogram
    SOURCE_CHANNEL_ID: int = int(os.getenv("SOURCE_CHANNEL_ID", "-1003376569543"))
    TARGET_CHANNEL_ID: int = int(os.getenv("TARGET_CHANNEL_ID", "-1003897821246"))
    
    # Admin ID pour notifications privées
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "1190237801"))
    
    # Configuration Render
    RENDER_DEPLOYMENT: bool = os.getenv("RENDER_DEPLOYMENT", "true").lower() == "true"
    PORT: int = int(os.getenv("PORT", "10000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    
    # Configuration du traducteur
    TARGET_LANGUAGE: str = os.getenv("TARGET_LANGUAGE", "fr")
    
    @classmethod
    def load(cls) -> "Config":
        return cls()

config = Config.load()
    
