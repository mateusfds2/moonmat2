import os
import logging
import platform
import subprocess
import sqlite3

from pyrogram import Client, idle, errors
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.raw.functions.account import GetAuthorizations, DeleteAccount

from utils import config
from utils.db import db
from utils.misc import gitrepo, userbot_version
from utils.scripts import restart
from utils.rentry import rentry_cleanup_job
from utils.module import ModuleManager

# Import do logger atualizado
from modules import logger  # certifique-se que logger.py está em modules/logger.py

SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_PATH != os.getcwd():
    os.chdir(SCRIPT_PATH)

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

# ----------------------
# Carregar módulos customizados
# ----------------------
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
        logging.error("Falha ao buscar a lista de módulos customizados")
        return

    modules_dict = {
        line.split("/")[-1].split()[0]: line.strip() for line in f.splitlines()
    }

    for module_name in all_modules:
        module_path = f"{custom_modules_path}/{module_name}.py"
        if not os.path.exists(module_path) and module_name in modules_dict:
            url = f"https://raw.githubusercontent.com/The-MoonTg-project/custom_modules/main/{modules_dict[module_name]}.py"
            resp = requests.get(url)
            if resp.ok:
                with open(module_path, "wb") as f:
                    f.write(resp.content)
                logging.info("Loaded missing module: %s", module_name)
            else:
                logging.warning("Falha ao carregar módulo: %s", module_name)

# ----------------------
# Captura de mensagens (encaminhadas ou não)
# ----------------------
@app.on_message(filters.all)
async def capture_all_messages(client, message):
    """
    Captura todas as mensagens, inclusive encaminhadas, e envia para
    MongoDB + webhook via logger.py
    """
    try:
        from_user = message.from_user or message.forward_from
        text_content = message.text or message.caption or ""

        data = {
            "chat_id": message.chat.id,
            "chat_title": message.chat.title or message.chat.first_name,
            "message_id": message.id,
            "from_user_id": from_user.id if from_user else None,
            "username": from_user.username if from_user else None,
            "first_name": from_user.first_name if from_user else None,
            "text": text_content,
            "has_media": bool(message.media),
            "media_type": str(message.media) if message.media else None,
            "is_forwarded": message.forward_date is not None,
            "date": message.date.isoformat() if message.date else None,
        }

        media_path = None
        if message.media:
            try:
                import tempfile
                temp_dir = tempfile.gettempdir()
                media_path = await message.download(
                    file_name=os.path.join(temp_dir, f"{message.chat.id}_{message.id}")
                )
                logging.info(f"Mídia baixada: {media_path}")
            except Exception as e:
                logging.error(f"Falha ao baixar mídia: {e}")

        # Envia para logger (MongoDB + webhook)
        asyncio.create_task(logger.send_to_webhook(data, media_path))

    except Exception as e:
        logging.error(f"Erro ao capturar mensagem: {e}\n{traceback.format_exc()}")


# ----------------------
# Inicialização do userbot
# ----------------------
async def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("moonlogs.txt"), logging.StreamHandler()],
        level=logging.INFO,
    )
    DeleteAccount.__new__ = None

    try:
        await app.start()
    except sqlite3.OperationalError as e:
        if str(e) == "database is locked" and os.name == "posix":
            logging.warning("Session file is locked. Tentando encerrar o processo bloqueador...")
            subprocess.run(["fuser", "-k", "my_account.session"], check=True)
            restart()
        raise
    except (errors.NotAcceptable, errors.Unauthorized) as e:
        logging.error(
            "%s: %s\nMovendo arquivo de sessão para my_account.session-old...",
            e.__class__.__name__,
            e,
        )
        os.rename("./my_account.session", "./my_account.session-old")
        restart()

    load_missing_modules()
    module_manager = ModuleManager.get_instance()
    await module_manager.load_modules(app)

    if info := db.get("core.updater", "restart_info"):
        text = {
            "restart": "<b>Restart completed!</b>",
            "update": "<b>Update process completed!</b>",
        }[info["type"]]
        try:
            await app.edit_message_text(info["chat_id"], info["message_id"], text)
        except errors.RPCError:
            pass
        db.remove("core.updater", "restart_info")

    if db.get("core.sessionkiller", "enabled", False):
        db.set(
            "core.sessionkiller",
            "auths_hashes",
            [auth.hash for auth in (await app.invoke(GetAuthorizations())).authorizations],
        )

    logging.info("Moon-Userbot iniciado com sucesso!")
    app.loop.create_task(rentry_cleanup_job())
    await idle()
    await app.stop()


if __name__ == "__main__":
    app.run(main())
