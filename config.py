# config.py
import os
from dataclasses import dataclass

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "7261458320:AAHpUmO1iXG03ACWP0doh7ylEISewmmPL4A")
    SOURCE_CHANNEL_ID: str = os.getenv("SOURCE_CHANNEL_ID", "-1003376569543")
    TARGET_CHANNEL_ID: str = os.getenv("TARGET_CHANNEL_ID", "-1003897821246")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "1190237801"))
    PORT: int = int(os.getenv("PORT", "10000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    RENDER_DEPLOYMENT: bool = os.getenv("RENDER_DEPLOYMENT", "true").lower() == "true"
    
    @classmethod
    def load(cls):
        return cls()

config = Config.load()
