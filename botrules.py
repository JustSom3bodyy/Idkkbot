import logging
from typing import Callable
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)
CREATOR_IDS = {8183099675, 5590512238}

def is_creator(user_id: int) -> bool:
    return user_id in CREATOR_IDS

async def check_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE, require_admin: bool = True) -> bool:
    try:
        if is_creator(update.effective_user.id):
            return True
        if not require_admin:
            return True
        if update.effective_chat and update.effective_chat.type in ['group', 'supergroup']:
            member = await update.effective_chat.get_member(update.effective_user.id)
            return member.status in ['administrator', 'creator']
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки прав: {e}")
        return False

def require_admin(handler: Callable) -> Callable:
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not await check_permissions(update, context, require_admin=True):
            await update.message.reply_text("❌ Только администраторы могут использовать эту команду!")
            return
        return await handler(update, context, *args, **kwargs)
    return wrapper

def require_creator(handler: Callable) -> Callable:
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not is_creator(update.effective_user.id):
            await update.message.reply_text("❌ Только создателям бота!")
            return
        return await handler(update, context, *args, **kwargs)
    return wrapper

def anyone_can_use(handler: Callable) -> Callable:
    return handler