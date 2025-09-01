# main.py - Moon Userbot atualizado

import os
import logging
import platform
import subprocess
import sqlite3
import tempfile
from pyrogram import Client, idle, errors, filters
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.raw.functions.account import GetAuthorizations, DeleteAccount
from pymongo import MongoClient
import requests
import asyncio

from utils import config
from utils.db import db
from utils.misc import gitrepo, userbot_version
from utils.scripts import restart
from utils.rentry import rentry_cleanup_job
from utils.module import ModuleManager

# Config MongoDB
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "telegram_logs")
mongo_client = MongoClient(MONGO_URI)
mongo_collection = mongo_client[MONGO_DB]["messages"]

# Diretório do script
SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_PATH != os.getcwd():
    os.chdir(SCRIPT_PATH)

# Config Pyrogram
common_params = {
    "api_id": config.api_id,
    "api_hash": config.api_hash,
    "hide_password": True,
    "workdir": SCRIPT_PATH,
    "app_version": userbot_version,
    "device_model": f"Moon-Userbot @ {gitrepo.head.commit.hexsha[:7]}",
    "system_version": platform.version() + " " + platform.machine(),
    "sleep_threshold": 30,
    "test_mode": config.test_server,
    "parse_mode": ParseMode.HTML,
}

if config.STRINGSESSION:
    common_params["session_string"] = config.STRINGSESSION

app = Client("my_account", **common_params)

# Logger
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("moonlogs.txt"), logging.StreamHandler()],
)

# Carregar módulos personalizados
def load_missing_modules():
    all_modules = db.get("custom.modules", "allModules", [])
    if not all_modules:
        return

    custom_modules_path = f"{SCRIPT_PATH}/modules/custom_modules"
    os.makedirs(custom_modules_path, exist_ok=True)

    try:
        f = requests.get(
            "https://raw.githubusercontent.com/The-MoonTg-project/custom_modules/main/full.txt"
        ).text
    except Exception:
        logging.error("Falha ao buscar lista de módulos customizados")
        return

    modules_dict = {line.split("/")[-1].split()[0]: line.strip() for line in f.splitlines()}

    for module_name in all_modules:
        module_path = f"{custom_modules_path}/{module_name}.py"
        if not os.path.exists(module_path) and module_name in modules_dict:
            url = f"https://raw.githubusercontent.com/The-MoonTg-project/custom_modules/main/{modules_dict[module_name]}.py"
            resp = requests.get(url)
            if resp.ok:
                with open(module_path, "wb") as f:
                    f.write(resp.content)
                logging.info("Módulo carregado: %s", module_name)
            else:
                logging.warning("Falha ao carregar módulo: %s", module_name)

# Função para logar mensagens no MongoDB
async def log_message(message):
    try:
        temp_dir = tempfile.gettempdir()
        media_path = None
        if message.media:
            media_path = await message.download(file_name=os.path.join(temp_dir, f"{message.chat.id}_{message.message_id}"))
            logging.info(f"Mídia baixada: {media_path}")

        data = {
            "chat_id": message.chat.id,
            "chat_title": getattr(message.chat, "title", None),
            "message_id": message.message_id,
            "from_user_id": message.from_user.id if message.from_user else None,
            "username": getattr(message.from_user, "username", None) if message.from_user else None,
            "first_name": getattr(message.from_user, "first_name", None) if message.from_user else None,
            "text": message.text or "",
            "has_media": bool(message.media),
            "media_type": str(message.media) if message.media else None,
            "date": message.date.isoformat(),
        }

        mongo_collection.insert_one(data)
        logging.info(f"[MONGODB] Mensagem salva: {data}")

    except Exception as e:
        logging.error(f"[LOGGER] Erro ao salvar mensagem: {e}")

# Main
async def main():
    DeleteAccount.__new__ = None

    try:
        await app.start()
    except sqlite3.OperationalError as e:
        if str(e) == "database is locked" and os.name == "posix":
            logging.warning("Session file bloqueada. Tentando finalizar processo...")
            subprocess.run(["fuser", "-k", "my_account.session"], check=True)
            restart()
        raise
    except (errors.NotAcceptable, errors.Unauthorized) as e:
        logging.error("%s: %s. Movendo session file para my_account.session-old", e.__class__.__name__, e)
        os.rename("./my_account.session", "./my_account.session-old")
        restart()

    # Carregar módulos
    load_missing_modules()
    module_manager = ModuleManager.get_instance()
    await module_manager.load_modules(app)

    # Info de restart/update
    if info := db.get("core.updater", "restart_info"):
        text = {"restart": "<b>Restart completed!</b>", "update": "<b>Update process completed!</b>"}[info["type"]]
        try:
            await app.edit_message_text(info["chat_id"], info["message_id"], text)
        except errors.RPCError:
            pass
        db.remove("core.updater", "restart_info")

    # Session killer
    if db.get("core.sessionkiller", "enabled", False):
        db.set("core.sessionkiller", "auths_hashes", [auth.hash for auth in (await app.invoke(GetAuthorizations())).authorizations])

    logging.info("Moon-Userbot started!")

    app.loop.create_task(rentry_cleanup_job())

    @app.on_message(filters.all)
    async def all_messages_handler(client, message):
        await log_message(message)

    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(main())
