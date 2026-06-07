import logging, json, os, html, asyncio
from datetime import datetime
from typing import Dict
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler

logger = logging.getLogger(__name__)
CHAT_MEMBERS_FILE = "chat_members.json"
chat_members_data: Dict[str, Dict[str, dict]] = {}

def load_chat_members():
    global chat_members_data
    if os.path.exists(CHAT_MEMBERS_FILE):
        try:
            with open(CHAT_MEMBERS_FILE, 'r', encoding='utf-8') as f:
                chat_members_data = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки: {e}")
            chat_members_data = {}
    else:
        chat_members_data = {}

def save_chat_members():
    try:
        with open(CHAT_MEMBERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(chat_members_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")

async def cache_user(user, chat_id: int):
    cid, uid = str(chat_id), str(user.id)
    if cid not in chat_members_data:
        chat_members_data[cid] = {}
    if uid not in chat_members_data[cid]:
        chat_members_data[cid][uid] = {"username": user.username or "", "first_name": user.first_name or "", "last_name": user.last_name or "", "added_date": datetime.now().isoformat(), "source": "mention"}
        save_chat_members()

async def track_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.new_chat_members:
        return
    cid = str(update.effective_chat.id)
    if cid not in chat_members_data:
        chat_members_data[cid] = {}
    for m in update.message.new_chat_members:
        uid = str(m.id)
        chat_members_data[cid][uid] = {"username": m.username or "", "first_name": m.first_name or "", "last_name": m.last_name or "", "added_date": datetime.now().isoformat()}
    save_chat_members()

async def track_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user:
        return
    cid, u = str(update.effective_chat.id), update.message.from_user
    uid = str(u.id)
    if cid not in chat_members_data:
        chat_members_data[cid] = {}
    chat_members_data[cid][uid] = {"username": u.username or "", "first_name": u.first_name or "", "last_name": u.last_name or "", "last_seen": datetime.now().isoformat(), "added_date": chat_members_data[cid].get(uid, {}).get("added_date") or datetime.now().isoformat()}
    save_chat_members()

async def pingall_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or msg.chat.type not in ['group','supergroup']:
        await msg.reply_text("❌ Только в группах!")
        return
    try:
        if (await msg.chat.get_member(update.effective_user.id)).status not in ['administrator','creator']:
            await msg.reply_text("❌ Только админам!")
            return
    except Exception:
        return
    cid = str(msg.chat.id)
    unames = [f"@{d['username']}" for d in chat_members_data.get(cid, {}).values() if d.get("username")]
    if unames:
        unames = unames[:40]
        txt = f"\n📢 {' '.join(context.args)}" if context.args else ""
        await msg.reply_text(f"🔔 <b>ВНИМАНИЕ!</b>\n\n<blockquote>{'  '.join(unames)}</blockquote>\n👥 Упомянуто: {len(unames)}{txt}", parse_mode='HTML')
    else:
        await ping_with_alternative_method(update, context)

async def ping_with_alternative_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    admins = await context.bot.get_chat_administrators(msg.chat.id)
    unames = [f"@{a.user.username}" for a in admins if not a.user.is_bot and a.user.username][:30]
    if unames:
        txt = f"\n📢 {' '.join(context.args)}" if context.args else ""
        await msg.reply_text(f"<blockquote>{'  '.join(unames)}</blockquote>\n👥 Упомянуто: {len(unames)}{txt}", parse_mode='HTML')
    else:
        await msg.reply_text("❌ Нет данных. Бот собирает базу.")

async def update_chat_members_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg:
        return
    try:
        if (await msg.chat.get_member(update.effective_user.id)).status not in ['administrator','creator']:
            await msg.reply_text("❌ Только админам!")
            return
    except Exception:
        return
    cid = str(msg.chat.id)
    admins = await context.bot.get_chat_administrators(msg.chat.id)
    if cid not in chat_members_data:
        chat_members_data[cid] = {}
    upd = 0
    for a in admins:
        u, uid = a.user, str(a.user.id)
        chat_members_data[cid][uid] = {"username": u.username or "", "first_name": u.first_name or "", "last_name": u.last_name or "", "last_seen": datetime.now().isoformat(), "added_date": chat_members_data[cid].get(uid, {}).get("added_date") or datetime.now().isoformat()}
        upd += 1
    save_chat_members()
    await msg.reply_text(f"✅ Обновлено!\n👥 +{upd}\n💾 Всего: {len(chat_members_data[cid])}")

def setup_ping_commands(application):
    load_chat_members()
    application.add_handler(CommandHandler("pingall", pingall_command))
    application.add_handler(CommandHandler("update_members", update_chat_members_command))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, track_new_chat_members))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, track_all_messages))