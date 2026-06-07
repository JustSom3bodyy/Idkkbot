import os
import logging
import asyncio
import re
import json
import html
from datetime import datetime, timedelta, timezone
from typing import Dict, Set
import pytz

from telegram import Update, User
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# ⚠️ В продакшне используйте os.getenv("BOT_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8150429316:AAGipnKcuOLTwg3O6GliLWCPS1wJobEfph0"ь3ццццццццццццццццццц)

from Moderation import setup_rules_commands, get_user_pseudo, format_user_mention
from funfunctions import setup_ping_commands
from botrules import require_admin, require_creator, anyone_can_use, check_permissions

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

chat_events: Dict[int, Dict[str, str]] = {}
reminders: Dict[int, Dict[str, dict]] = {}
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

CREATOR_IDS = {8183099675, 5590512238}
DATA_FILE = "global_ban_data.json"

class GlobalBanData:
    def __init__(self):
        self.banned_users: Set[int] = set()
        self.known_chats: Dict[int, str] = {}

    def to_dict(self):
        return {'banned_users': list(self.banned_users), 'known_chats': self.known_chats}

    @classmethod
    def from_dict(cls, data):
        instance = cls()
        instance.banned_users = set(data.get('banned_users', []))
        instance.known_chats = data.get('known_chats', {})
        return instance

def load_global_ban_data() -> GlobalBanData:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return GlobalBanData.from_dict(json.load(f))
        except Exception:
            return GlobalBanData()
    return GlobalBanData()

def save_global_ban_data(data: GlobalBanData):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data.to_dict(), f, ensure_ascii=False, indent=2)

global_ban_data = load_global_ban_data()

async def track_chat(chat_id: int, chat_title: str):
    global_ban_data.known_chats[chat_id] = chat_title
    save_global_ban_data(global_ban_data)

async def resolve_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return None, "Не указана"
    if msg.reply_to_message:
        return msg.reply_to_message.from_user, ' '.join(context.args) if context.args else "Не указана"
    if context.args:
        raw = context.args[0].lstrip('@')
        try:
            if raw.isdigit():
                member = await context.bot.get_chat_member(msg.chat.id, int(raw))
                return member.user, ' '.join(context.args[1:]) if len(context.args)>1 else "Не указана"
            else:
                u = await context.bot.get_chat(f"@{raw}")
                if isinstance(u, User):
                    return u, ' '.join(context.args[1:]) if len(context.args)>1 else "Не указана"
        except Exception:
            pass
    return None, None

async def check_global_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_chat:
            await track_chat(update.effective_chat.id, update.effective_chat.title or "Unknown")
        if update.message and update.message.new_chat_members:
            for new_member in update.message.new_chat_members:
                if new_member.id in global_ban_data.banned_users:
                    try:
                        await context.bot.ban_chat_member(
                            chat_id=update.effective_chat.id,
                            user_id=new_member.id,
                            until_date=datetime.now(timezone.utc) + timedelta(days=366)
                        )
                        await update.message.reply_text(
                            f"🚫 {new_member.mention_html()} автоматически забанен (глобальный бан)",
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logger.error(f"Ошибка авто-бана: {e}")
    except Exception as e:
        logger.error(f"Ошибка в check_global_ban: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👋 Привет, {update.effective_user.first_name}!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = """
<b>📚 Справка по боту</b>

<i>📋 Основные команды:</i>
/start - Начало работы с ботом
/help - Показать это сообщение
/info - Информация об аккаунте (свой или чужой)

<i>📅 События и напоминания:</i>
/newevent - Сохранить событие в чат
<blockquote><i>/newevent названиесобытия [ответ на сообщение]</i></blockquote>
/events - Показать все события чата
/chatevents - Альтернатива /events
/newnotif - Создать напоминание
<blockquote><i>/newnotif название ДД.ММ.ГГГГ ЧЧ:ММ (МСК)</i></blockquote>
/mynotifs - Мои активные напоминания
/cancelnotif - Отменить напоминание

<i>👥 Псевдонимы:</i>
/setpseudo - Установить псевдоним пользователю
<blockquote><i>/setpseudo [ответ] никнейм</i></blockquote>
/setglobalpseudo - Глобальный псевдоним (во всех чатах)
/checkpseudo - Проверить псевдонимы пользователя

<i>⚠️ Система предупреждений:</i>
/warn - Выдать предупреждение
<blockquote><i>/warn [ответ] 7d П3 Спам</i></blockquote>
/unwarn - Снять предупреждение
/mywarns - Мои предупреждения
/checkwarns - Проверить предупреждения пользователя
/setwarn - Макс. количество варнов (1-20)
/setwarnduration - Длительность варна в днях (1-365)

<i>🔇 Система мутов:</i>
/mute - Замьютить пользователя
<blockquote><i>/mute [ответ] 2h Флуд</i></blockquote>
/unmute - Снять мут
/checkmute - Проверить мут пользователя
/setmuteduration - Настройки длительности мутов

<i>📜 Правила чата:</i>
/setrule - Добавить правило
<blockquote><i>/setrule текст правила</i></blockquote>
/setrule1, /setrule2... - Правило под номером
/showrules - Показать все правила
/delrule1, /delrule2... - Удалить правило
/clearrules - Очистить все правила

<i>🛡 Модерация:</i>
/ban - Забанить пользователя
/unban - Разбанить пользователя
/pingall - Упомянуть всех участников (админам)
/update_members - Обновить список участников

<i>📖 Руководство пользователя:</i>
https://telegra.ph/IdkkBot-09-07

<i>🛠 Поддержка:</i>
По вопросам и предложениям: @Idkk_Cali / @Pj3tA [Создатель] / <code>5590512238</code> / @Help_AccInf_Bot [Техподдержка]
"""
    await update.message.reply_text(help_text, parse_mode='HTML')

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        target, _ = await resolve_target(update, context)
        if not target:
            target = update.effective_user
        if not isinstance(target, User):
            await update.message.reply_text("❌ Ошибка определения пользователя")
            return

        custom_pseudo = get_user_pseudo(target.id, update.message.chat.id)
        user_info = [
            f"🆔 <b>ID:</b> <code>{target.id}</code>",
            f"👤 <b>Имя:</b> {html.escape(target.first_name or '')}",
            f"📛 <b>Фамилия:</b> {html.escape(target.last_name or 'Нет')}",
            f"🔖 {'<b>Юзернейм:</b> @' + html.escape(target.username) if target.username else '🔖 Юзернейм: Нет'}",
            f"💎 <b>Премиум:</b> {'Да' if target.is_premium else 'Нет'}",
            f"🤖 <b>Бот:</b> {'Да' if target.is_bot else 'Нет'}",
            f"🎭 <b>Псевдоним:</b> {html.escape(custom_pseudo) if custom_pseudo else 'Не установлен'}"
        ]
        if update.message.chat.type in ['group', 'supergroup']:
            try:
                member = await context.bot.get_chat_member(update.message.chat.id, target.id)
                user_info.append(f"\n👮 <b>Админ:</b> {'✅' if member.status in ['administrator', 'creator'] else '❌'}")
                if member.custom_title:
                    user_info.append(f"📜 <b>Титул:</b> {html.escape(member.custom_title)}")
            except Exception:
                pass
        await update.message.reply_text('\n'.join(user_info), parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {html.escape(str(e))}")

async def newevent_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.reply_to_message or not context.args:
        await msg.reply_text("ℹ️ Ответьте на сообщение и укажите название: /newevent Название")
        return
    link = f"https://t.me/c/{str(msg.chat.id).replace('-100','')}/{msg.reply_to_message.message_id}"
    chat_events.setdefault(msg.chat.id, {})[' '.join(context.args).strip()] = link
    await msg.reply_text("✅ Событие сохранено!", parse_mode='HTML')

async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat.id
    if chat_id not in chat_events:
        await update.message.reply_text("ℹ️ Нет событий")
        return
    lst = [f"🔹 <a href='{ln}'>{nm}</a>" for nm, ln in chat_events[chat_id].items()]
    await update.message.reply_text("📅 События:\n" + '\n'.join(lst), parse_mode='HTML')

async def newnotif_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if len(context.args) < 2:
        await msg.reply_text("ℹ️ /newnotif название ДД.ММ.ГГГГ ЧЧ:ММ")
        return
    *name_parts, time_part = context.args
    reminder_name = ' '.join(name_parts[:-1]) if len(name_parts)>1 else name_parts[0]
    now = datetime.now(MOSCOW_TZ)
    reminder_dt = None
    if re.match(r'^\d{1,2}:\d{2}$', time_part):
        rem_time = datetime.strptime(time_part, "%H:%M").time()
        reminder_dt = MOSCOW_TZ.localize(datetime.combine(now.date(), rem_time))
        if reminder_dt < now:
            reminder_dt += timedelta(days=1)
    elif len(context.args) >= 3 and re.match(r'^\d{1,2}\.\d{1,2}\.\d{4}$', context.args[-2]):
        reminder_dt = MOSCOW_TZ.localize(datetime.strptime(f"{context.args[-2]} {time_part}", "%d.%m.%Y %H:%M"))
    if not reminder_dt:
        await msg.reply_text("❌ Неверный формат")
        return
    rid = f"{msg.from_user.id}_{reminder_dt.timestamp()}"
    reminders.setdefault(msg.chat.id, {})[rid] = {'user_id': msg.from_user.id, 'time': reminder_dt, 'message': reminder_name}
    asyncio.create_task(send_reminder(context.bot, msg.chat.id, msg.from_user.id, reminder_name, reminder_dt))
    await msg.reply_text(f"⏰ Напоминание на {reminder_dt.strftime('%d.%m.%Y %H:%M')} (МСК)")

async def send_reminder(bot, chat_id, user_id, message, reminder_time):
    await asyncio.sleep((reminder_time - datetime.now(MOSCOW_TZ)).total_seconds())
    mention = f"<a href='tg://user?id={user_id}'>⏰</a>"
    await bot.send_message(chat_id=chat_id, text=f"{mention*3}\n🔔 {html.escape(message)}\n{mention*3}", parse_mode='HTML')
    rid = f"{user_id}_{reminder_time.timestamp()}"
    if chat_id in reminders and rid in reminders[chat_id]:
        del reminders[chat_id][rid]

async def mynotifs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    uid = msg.from_user.id
    if msg.chat.id not in reminders:
        await msg.reply_text("ℹ️ Нет напоминаний")
        return
    user_rems = sorted([r for r in reminders[msg.chat.id].values() if r['user_id']==uid], key=lambda x: x['time'])
    if not user_rems:
        await msg.reply_text("ℹ️ Нет напоминаний")
        return
    now = datetime.now(MOSCOW_TZ)
    res = ["📅 Ваши напоминания:"]
    for r in user_rems:
        left = r['time'] - now
        d, rem = divmod(left.total_seconds(), 86400)
        h, rem = divmod(rem, 3600)
        m = rem//60
        res.append(f"🔹 {html.escape(r['message'])} - {r['time'].strftime('%d.%m.%Y %H:%M')} (МСК) | ⏳ {int(d)}д {int(h)}ч {int(m)}м")
    await msg.reply_text('\n'.join(res), parse_mode='HTML')

async def cancelnotif_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("ℹ️ /cancelnotif название")
        return
    name = ' '.join(context.args)
    cid, uid = update.message.chat.id, update.message.from_user.id
    to_del = [r for r, d in reminders.get(cid, {}).items() if d['user_id']==uid and d['message']==name]
    if not to_del:
        await update.message.reply_text("ℹ️ Не найдено")
        return
    for r in to_del:
        del reminders[cid][r]
    await update.message.reply_text("✅ Отменено!", parse_mode='HTML')

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or msg.chat.type not in ['group', 'supergroup']:
        return
    member = await msg.chat.get_member(update.effective_user.id)
    if member.status not in ['administrator', 'creator']:
        await msg.reply_text("❌ Только админам!")
        return
    target, reason = await resolve_target(update, context)
    if not target:
        await msg.reply_text("❌ Укажите @username, ID или ответьте на сообщение")
        return
    if target.id in (update.effective_user.id, context.bot.id):
        await msg.reply_text("❌ Нельзя банить себя/бота")
        return
    await context.bot.ban_chat_member(chat_id=msg.chat.id, user_id=target.id, until_date=datetime.now(timezone.utc)+timedelta(days=366))
    await msg.reply_text(f"🚫 {target.mention_html()} забанен!\n👮 {update.effective_user.mention_html()}\n📝 {reason}", parse_mode='HTML')

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or msg.chat.type not in ['group', 'supergroup']:
        return
    member = await msg.chat.get_member(update.effective_user.id)
    if member.status not in ['administrator', 'creator']:
        await msg.reply_text("❌ Только админам!")
        return
    target, reason = await resolve_target(update, context)
    if not target:
        await msg.reply_text("❌ Укажите @username, ID или ответьте")
        return
    await context.bot.unban_chat_member(chat_id=msg.chat.id, user_id=target.id, only_if_banned=True)
    await msg.reply_text(f"✅ {target.mention_html()} разбанен!\n👮 {update.effective_user.mention_html()}\n📝 {reason}", parse_mode='HTML')

async def hello_unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if update.effective_user.id not in CREATOR_IDS:
        await msg.reply_text("❌ Только создателям!")
        return
    if not context.args and not msg.reply_to_message:
        await msg.reply_text("ℹ️ /hello_unban [ID] или ответ")
        return
    target, reason = await resolve_target(update, context)
    if not target or not str(target.id).isdigit():
        await msg.reply_text("❌ Нужен числовой ID!")
        return
    global_ban_data.banned_users.discard(int(target.id))
    save_global_ban_data(global_ban_data)
    ok, err = [], []
    for cid in global_ban_data.known_chats:
        try:
            await context.bot.unban_chat_member(chat_id=cid, user_id=target.id, only_if_banned=True)
            ok.append(cid)
        except Exception:
            err.append(cid)
    await msg.reply_text(f"🌍 Разбанен в {len(ok)} чатах. Ошибки: {len(err)}", parse_mode='HTML')

async def gg_ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if update.effective_user.id not in CREATOR_IDS:
        await msg.reply_text("❌ Только создателям!")
        return
    target, reason = await resolve_target(update, context)
    if not target or not str(target.id).isdigit():
        await msg.reply_text("❌ Нужен числовой ID!")
        return
    global_ban_data.banned_users.add(target.id)
    save_global_ban_data(global_ban_data)
    ok, err = [], []
    until = datetime.now(timezone.utc) + timedelta(days=366)
    for cid in global_ban_data.known_chats:
        try:
            await context.bot.ban_chat_member(chat_id=cid, user_id=target.id, until_date=until)
            ok.append(cid)
        except Exception:
            err.append(cid)
    await msg.reply_text(f"🌍 Забанен в {len(ok)} чатах. Ошибки: {len(err)}\n📝 {reason}", parse_mode='HTML')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("newevent", newevent_command))
    application.add_handler(CommandHandler("events", events_command))
    application.add_handler(CommandHandler("chatevents", events_command))
    application.add_handler(CommandHandler("newnotif", newnotif_command))
    application.add_handler(CommandHandler("mynotifs", mynotifs_command))
    application.add_handler(CommandHandler("cancelnotif", cancelnotif_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("hello_unban", hello_unban_command))
    application.add_handler(CommandHandler("gg_ban", gg_ban_command))
    setup_rules_commands(application)
    setup_ping_commands(application)
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.ALL, check_global_ban))
    application.add_error_handler(error_handler)
    logger.info("✅ Бот запущен")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()