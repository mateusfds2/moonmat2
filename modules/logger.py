from pyrogram import Client, filters
from pymongo import MongoClient
import os

# Pega as variáveis de ambiente
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "telegram_logs")

# Conecta no MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]
collection = db["messages"]

# Captura todas as mensagens (suas + de outros), exceto mensagens de serviço (ex: "fulano entrou no grupo")
@Client.on_message(filters.all & ~filters.service)
async def log_message(client, message):
    try:
        data = {
            "chat_id": message.chat.id,
            "chat_title": getattr(message.chat, "title", None),
            "user_id": getattr(message.from_user, "id", None) if message.from_user else None,
            "username": getattr(message.from_user, "username", None) if message.from_user else No
