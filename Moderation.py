import json, os, logging, re, asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict
import pytz
from telegram import Update, ChatPermissions, User
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

chat_rules, user_warns, warn_settings = {}, {}, {}
user_mutes, mute_settings, user_pseudo = {}, {}, {}

def load_data():
    for fn, var in [('chat_rules.json','chat_rules'), ('user_pseudo.json','user_pseudo'), ('user_warns.json','user_warns'),
                    ('warn_settings.json','warn_settings'), ('user_mutes.json','user_mutes'), ('mute_settings.json','mute_settings')]:
        try:
            globals()[var] = json.load(open(fn, 'r', encoding='utf-8')) if os.path.exists(fn) else {}
        except Exception:
            globals()[var] = {}
    logging.info("📦 Данные загружены")

def save_data():
    for fn, var in [('chat_rules.json','chat_rules'), ('user_pseudo.json','user_pseudo'), ('user_warns.json','user_warns'),
                    ('warn_settings.json','warn_settings'), ('user_mutes.json','user_mutes'), ('mute_settings.json','mute_settings')]:
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump(globals()[var], f, ensure_ascii=False, indent=2)

def get_warn_settings(cid):
    cid=str(cid)
    warn_settings.setdefault(cid, {"max_warns":5, "warn_duration":14})
    return warn_settings[cid]

def get_mute_settings(cid):
    cid=str(cid)
    mute_settings.setdefault(cid, {"max_mute_duration":30, "default_mute_duration":1})
    return mute_settings[cid]

def get_user_pseudo(uid, cid=None):
    u=str(uid)
    c=str(cid) if cid else None
    if c and u in user_pseudo and c in user_pseudo[u]:
        return user_pseudo[u][c]
    if u in user_pseudo and "global" in user_pseudo[u]:
        return user_pseudo[u]["global"]
    return None

def format_user_mention(user, cid=None):
    ps = get_user_pseudo(user.id, cid)
    return f'<a href="tg://user?id={user.id}">{ps}</a>' if ps else user.mention_html()

async def is_admin_or_creator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        return (await update.message.chat.get_member(update.effective_user.id)).status in ['administrator', 'creator']
    except Exception:
        return False

async def resolve_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return None, None
    if msg.reply_to_message:
        return msg.reply_to_message.from_user, ' '.join(context.args[1:]) if len(context.args)>1 else "Не указана"
    if context.args:
        raw = context.args[0].lstrip('@')
        try:
            if raw.isdigit():
                m = await context.bot.get_chat_member(msg.chat.id, int(raw))
                return m.user, ' '.join(context.args[1:]) if len(context.args)>1 else "Не указана"
            u = await context.bot.get_chat(f"@{raw}")
            if isinstance(u, User):
                return u, ' '.join(context.args[1:]) if len(context.args)>1 else "Не указана"
        except Exception:
            pass
    return None, None

async def setpseudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    is_adm = await is_admin_or_creator(update, context)
    target = None
    if msg.reply_to_message:
        target = msg.reply_to_message.from_user
    elif context.args and context.args[0].isdigit():
        try:
            tid = int(context.args[0])
            target = (await context.bot.get_chat_member(msg.chat.id, tid)).user
            context.args = context.args[1:]
        except Exception:
            await msg.reply_text("❌ Не найден")
            return
    else:
        target = update.effective_user

    if not is_adm and target.id != update.effective_user.id:
        await msg.reply_text("❌ Обычные пользователи могут менять псевдоним только себе!")
        return
    if not context.args:
        await msg.reply_text("ℹ️ /setpseudo [текст] или clear")
        return
    ps = ' '.join(context.args).strip()
    uid, cid = str(target.id), str(msg.chat.id)
    if ps.lower()=='clear':
        if uid in user_pseudo and cid in user_pseudo[uid]:
            del user_pseudo[uid][cid]
        if uid in user_pseudo and not user_pseudo[uid]:
            del user_pseudo[uid]
        save_data()
        await msg.reply_text("✅ Удалено!", parse_mode='HTML')
        return
    user_pseudo.setdefault(uid, {})[cid] = ps
    save_data()
    await msg.reply_text(f"✅ Установлен: {format_user_mention(target, msg.chat.id)}", parse_mode='HTML')

async def setglobalpseudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not await is_admin_or_creator(update, context):
        await msg.reply_text("❌ Только админам!")
        return
    target = None
    if msg.reply_to_message:
        target = msg.reply_to_message.from_user
    elif context.args and context.args[0].isdigit():
        try:
            target = (await context.bot.get_chat_member(msg.chat.id, int(context.args[0]))).user
            context.args = context.args[1:]
        except Exception:
            await msg.reply_text("❌ Не найден")
            return
    else:
        await msg.reply_text("❌ Ответьте или ID")
        return
    if not context.args:
        await msg.reply_text("ℹ️ /setglobalpseudo [текст] или clear")
        return
    ps = ' '.join(context.args).strip()
    uid = str(target.id)
    if ps.lower()=='clear':
        if uid in user_pseudo and "global" in user_pseudo[uid]:
            del user_pseudo[uid]["global"]
        if uid in user_pseudo and not user_pseudo[uid]:
            del user_pseudo[uid]
        save_data()
        await msg.reply_text("✅ Удалено!", parse_mode='HTML')
        return
    user_pseudo.setdefault(uid, {})["global"] = ps
    save_data()
    await msg.reply_text(f"✅ Глобальный установлен", parse_mode='HTML')

async def checkpseudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    target = msg.reply_to_message.from_user if msg.reply_to_message else update.effective_user
    if context.args and context.args[0].isdigit():
        try:
            target = (await context.bot.get_chat_member(msg.chat.id, int(context.args[0]))).user
        except Exception:
            await msg.reply_text("❌ Не найден")
            return
    uid = str(target.id)
    res = [f"📛 <b>Псевдонимы {target.first_name}:</b>"]
    if uid in user_pseudo:
        if "global" in user_pseudo[uid]:
            res.append(f"🌍 Глобальный: {user_pseudo[uid]['global']}")
        for c,p in user_pseudo[uid].items():
            if c!="global" and p:
                res.append(f"💬 Чат {c}: {p}")
    if len(res)==1:
        res.append("ℹ️ Не установлены")
    res.append(f"\n👤 <b>Текущее:</b> {get_user_pseudo(target.id, msg.chat.id) or target.first_name}")
    await msg.reply_text('\n'.join(res), parse_mode='HTML')

async def test_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_or_creator(update, context):
        await update.message.reply_text("❌ Только админам!")
        return
    await update.message.reply_text(f"Тест мута 1м. UTC Now: {datetime.now(timezone.utc)}")

async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.chat.type not in ['group','supergroup']:
        return
    if not await is_admin_or_creator(update, context):
        await msg.reply_text("❌ Только админам!")
        return
    target, reason = await resolve_target_user(update, context)
    if not target:
        await msg.reply_text("❌ Ответьте или @/ID")
        return
    cid = str(msg.chat.id)
    s = get_warn_settings(cid)
    args = ' '.join(context.args[1:]) if len(context.args)>1 else reason
    dur = s['warn_duration']
    rule = None
    comment = "Не указано"
    m = re.search(r'(\d+)d', args, re.I)
    if m:
        dur=int(m.group(1))
        args=re.sub(r'\d+d','',args,flags=re.I).strip()
    m = re.search(r'(?:П|правило)(\d+)', args, re.I)
    if m:
        rule=int(m.group(1))
        args=re.sub(r'(?:П|правило)\d+','',args,flags=re.I).strip()
    if args.strip():
        comment=args.strip()
    uid = str(target.id)
    if rule and (cid not in chat_rules or len(chat_rules[cid])<rule or not chat_rules[cid][rule-1]):
        await msg.reply_text("❌ Такого правила нет")
        return
    chat_rules.setdefault(cid, [])
    user_warns.setdefault(cid, {}).setdefault(uid, [])
    exp = datetime.now(MOSCOW_TZ)+timedelta(days=dur)
    user_warns[cid][uid].append({"rule":rule,"comment":comment,"expires":exp.isoformat(),"issued_by":update.effective_user.id,"issued_at":datetime.now(MOSCOW_TZ).isoformat()})
    save_data()
    rule_msg = f"📜 Правило #{rule}:\n<blockquote>{chat_rules[cid][rule-1]}</blockquote>\n" if rule else "📜 Правило: Не указано\n"
    active = [w for w in user_warns[cid][uid] if datetime.fromisoformat(w["expires"])>datetime.now(MOSCOW_TZ)]
    txt = f"⚠️ <b>ПРЕДУПРЕЖДЕНИЕ</b>\n\n👤 {format_user_mention(target, msg.chat.id)}\n{rule_msg}📝 {comment}\n⏰ {dur}д\n🔢 {len(active)}/{s['max_warns']}"
    if len(active)>=s['max_warns']:
        try:
            await context.bot.ban_chat_member(chat_id=msg.chat.id, user_id=target.id, until_date=datetime.now(timezone.utc)+timedelta(days=366))
        except Exception as e:
            txt += f"\n\n❌ Ошибка бана: {e}"
        user_warns[cid][uid]=[]
        save_data()
        txt+="\n🚫 <b>Забанен за лимит!</b>"
    await msg.reply_text(txt, parse_mode='HTML')

async def setwarn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not await is_admin_or_creator(update, context):
        return
    if not context.args:
        await msg.reply_text(f"ℹ️ Макс: {get_warn_settings(msg.chat.id)['max_warns']}")
        return
    try:
        mx=int(context.args[0])
    except ValueError:
        await msg.reply_text("❌ Число")
        return
    if not 1<=mx<=20:
        await msg.reply_text("❌ 1-20")
        return
    get_warn_settings(msg.chat.id)["max_warns"]=mx
    save_data()
    await msg.reply_text(f"✅ Макс: {mx}")

async def setwarnduration_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not await is_admin_or_creator(update, context):
        return
    if not context.args:
        await msg.reply_text(f"⏰ Длительность: {get_warn_settings(msg.chat.id)['warn_duration']}д")
        return
    try:
        d=int(context.args[0])
    except ValueError:
        await msg.reply_text("❌ Число")
        return
    if not 1<=d<=365:
        await msg.reply_text("❌ 1-365")
        return
    get_warn_settings(msg.chat.id)["warn_duration"]=d
    save_data()
    await msg.reply_text(f"✅ {d}д")

async def mywarns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    cid, uid = str(msg.chat.id), str(update.effective_user.id)
    if cid not in user_warns or uid not in user_warns[cid]:
        await msg.reply_text("ℹ️ Нет")
        return
    active = [w for w in user_warns[cid][uid] if datetime.fromisoformat(w["expires"])>datetime.now(MOSCOW_TZ)]
    if not active:
        await msg.reply_text("ℹ️ Нет активных")
        return
    s = get_warn_settings(cid)
    res = [f"⚠️ <b>Ваши варны:</b> ({len(active)}/{s['max_warns']})"]
    for i,w in enumerate(active,1):
        exp=datetime.fromisoformat(w["expires"])
        left=exp-datetime.now(MOSCOW_TZ)
        rt = chat_rules.get(cid,[])[w["rule"]-1] if (w["rule"] and cid in chat_rules and len(chat_rules[cid])>=w["rule"]) else "Удалено"
        res.append(f"\n{i}. 📜 {rt}\n📝 {w['comment']}\n⏰ {left.days}д {left.seconds//3600}ч")
    await msg.reply_text('\n'.join(res), parse_mode='HTML')

async def checkwarns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not await is_admin_or_creator(update, context):
        return
    target, _ = await resolve_target_user(update, context)
    if not target:
        await msg.reply_text("❌ Ответьте или @/ID")
        return
    cid, uid = str(msg.chat.id), str(target.id)
    if cid not in user_warns or uid not in user_warns[cid]:
        await msg.reply_text("ℹ️ Нет")
        return
    active = [w for w in user_warns[cid][uid] if datetime.fromisoformat(w["expires"])>datetime.now(MOSCOW_TZ)]
    s = get_warn_settings(cid)
    res = [f"⚠️ <b>Варны {format_user_mention(target, msg.chat.id)}:</b> ({len(active)}/{s['max_warns']})"]
    for i,w in enumerate(active,1):
        exp=datetime.fromisoformat(w["expires"])
        left=exp-datetime.now(MOSCOW_TZ)
        rt = chat_rules.get(cid,[])[w["rule"]-1] if (w["rule"] and cid in chat_rules and len(chat_rules[cid])>=w["rule"]) else "Удалено"
        res.append(f"\n{i}. 📜 {rt}\n📝 {w['comment']}\n⏰ {left.days}д {left.seconds//3600}ч\n👮 {w['issued_by']}")
    await msg.reply_text('\n'.join(res), parse_mode='HTML')

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not await is_admin_or_creator(update, context):
        return
    target, reason = await resolve_target_user(update, context)
    if not target:
        await msg.reply_text("❌ Ответьте или @/ID")
        return
    cid = str(msg.chat.id)
    s = get_mute_settings(cid)
    def_dur = s['default_mute_duration']*60
    args = ' '.join(context.args[1:]) if len(context.args)>1 else reason
    dur = def_dur
    for pat, mult in [(r'(\d+)d',1440),(r'(\d+)h',60),(r'(\d+)m',1)]:
        m = re.findall(pat, args, re.I)
        if m:
            dur+=sum(int(x)*mult for x in m)
            args=re.sub(pat,'',args,flags=re.I)
    if args.strip():
        reason=args.strip()
    dur = max(1, dur)
    if dur > s['max_mute_duration']*60:
        await msg.reply_text(f"❌ Макс {s['max_mute_duration']}ч")
        return
    uid = str(target.id)
    exp = datetime.now(MOSCOW_TZ)+timedelta(minutes=dur)
    user_mutes.setdefault(cid, {})[uid] = {"expires":exp.isoformat(),"reason":reason,"issued_by":update.effective_user.id,"issued_at":datetime.now(MOSCOW_TZ).isoformat(),"duration_minutes":dur,"user_mention":format_user_mention(target, msg.chat.id),"chat_id":cid}
    save_data()
    disp = f"{dur//1440}д {dur%1440//60}ч" if dur>=1440 else f"{dur//60}ч {dur%60}м" if dur>=60 else f"{dur}м"
    try:
        await context.bot.restrict_chat_member(chat_id=msg.chat.id, user_id=target.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now(timezone.utc)+timedelta(minutes=dur))
        await msg.reply_text(f"🔇 <b>МУТ</b>\n\n👤 {format_user_mention(target, msg.chat.id)}\n⏰ {disp}\n📝 {reason}\n🕒 {exp.strftime('%d.%m.%Y %H:%M')} МСК", parse_mode='HTML')
    except Exception as e:
        await msg.reply_text(f"⚠️ Ошибка: {e}")

async def check_mutes_on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    cid = str(update.message.chat.id)
    if cid not in user_mutes:
        return
    now = datetime.now(MOSCOW_TZ)
    to_del = [uid for uid,m in user_mutes[cid].items() if datetime.fromisoformat(m["expires"])<=now]
    for uid in to_del:
        m = user_mutes[cid][uid]
        disp = f"{m['duration_minutes']//1440}д" if m['duration_minutes']>=1440 else f"{m['duration_minutes']//60}ч" if m['duration_minutes']>=60 else f"{m['duration_minutes']}м"
        try:
            await context.bot.send_message(chat_id=int(cid), text=f"🔊 <b>Мут истек</b>\n\n👤 {m['user_mention']}\n⏰ {disp}\n📝 {m['reason']}", parse_mode='HTML')
        except Exception:
            pass
        del user_mutes[cid][uid]
    if to_del:
        save_data()

async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not await is_admin_or_creator(update, context):
        return
    target, _ = await resolve_target_user(update, context)
    if not target:
        await msg.reply_text("❌ Ответьте или @/ID")
        return
    cid, uid = str(msg.chat.id), str(target.id)
    if cid not in user_mutes or uid not in user_mutes[cid]:
        await msg.reply_text("ℹ️ Нет мута")
        return
    try:
        await context.bot.restrict_chat_member(chat_id=msg.chat.id, user_id=target.id, permissions=ChatPermissions(can_send_messages=True))
    except Exception as e:
        await msg.reply_text(f"❌ Ошибка: {e}")
        return
    del user_mutes[cid][uid]
    save_data()
    await msg.reply_text("✅ Мут снят!", parse_mode='HTML')

async def setmuteduration_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not await is_admin_or_creator(update, context):
        return
    s = get_mute_settings(msg.chat.id)
    if not context.args:
        await msg.reply_text(f"⏰ Макс: {s['max_mute_duration']}ч, Дефолт: {s['default_mute_duration']}ч")
        return
    try:
        mx=int(context.args[0])
        df=int(context.args[1]) if len(context.args)>1 else s['default_mute_duration']
    except ValueError:
        await msg.reply_text("❌ Числа")
        return
    if not 1<=mx<=720 or not 1<=df<=mx:
        await msg.reply_text("❌ Диапазон неверен")
        return
    s["max_mute_duration"]=mx
    s["default_mute_duration"]=df
    save_data()
    await msg.reply_text(f"✅ Макс {mx}ч, Дефолт {df}ч")

async def checkmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    target, _ = await resolve_target_user(update, context)
    if not target:
        target = update.effective_user
    cid, uid = str(msg.chat.id), str(target.id)
    if cid not in user_mutes or uid not in user_mutes[cid]:
        await msg.reply_text("ℹ️ Нет мута")
        return
    m = user_mutes[cid][uid]
    exp = datetime.fromisoformat(m["expires"])
    if exp <= datetime.now(MOSCOW_TZ):
        await msg.reply_text("ℹ️ Мут истек")
        return
    left = exp-datetime.now(MOSCOW_TZ)
    d,h,m_t = left.days, left.seconds//3600, (left.seconds%3600)//60
    tstr = f"{d}д "*(d>0) + f"{h}ч "*(h>0) + f"{m_t}м"
    await msg.reply_text(f"🔇 <b>Мут</b>\n\n👤 {format_user_mention(target, msg.chat.id)}\n⏰ Осталось: {tstr}\n📝 {m['reason']}\n👮 {m['issued_by']}\n🕒 {exp.strftime('%d.%m.%Y %H:%M')}", parse_mode='HTML')

async def setrule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        await update.effective_message.reply_text("❌ Ошибка")
        return
    if not await is_admin_or_creator(update, context):
        await msg.reply_text("❌ Только админам!")
        return
    rule_text = msg.text.split(' ', 1)[1] if ' ' in msg.text else ''
    if not rule_text.strip():
        await msg.reply_text("ℹ️ /setrule текст")
        return
    if len(rule_text) > 250:
        await msg.reply_text("❌ Макс. 250 символов")
        return
    cid = str(msg.chat.id)
    chat_rules.setdefault(cid, []).append(rule_text.strip())
    save_data()
    await msg.reply_text(f"✅ Правило #{len(chat_rules[cid])} добавлено!", parse_mode='HTML')

async def setrule_num_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not await is_admin_or_creator(update, context):
        return
    m = re.match(r'^/setrule(\d+)(?:\s|$)', msg.text)
    if not m:
        return
    n, txt = int(m.group(1)), msg.text.replace(m.group(0), '').strip()
    if not txt:
        await msg.reply_text(f"ℹ️ /setrule{n} текст")
        return
    if len(txt) > 250:
        await msg.reply_text("❌ Макс. 250 символов")
        return
    cid = str(msg.chat.id)
    if cid not in chat_rules:
        chat_rules[cid] = []
    while len(chat_rules[cid]) < n:
        chat_rules[cid].append("")
    chat_rules[cid][n-1] = txt
    save_data()
    await msg.reply_text(f"✅ Правило #{n} установлено!", parse_mode='HTML')

async def showrules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    cid = str(msg.chat.id)
    if cid not in chat_rules or not any(chat_rules[cid]):
        await msg.reply_text("ℹ️ Нет правил")
        return
    res = ["📜 <b>Правила:</b>"] + [f"{i}. <blockquote>{r}</blockquote>" for i,r in enumerate(chat_rules[cid],1) if r]
    await msg.reply_text('\n'.join(res), parse_mode='HTML')

async def delrule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not await is_admin_or_creator(update, context):
        return
    m = re.match(r'^/delrule(\d+)(?:\s|$)', msg.text)
    if not m:
        return
    n = int(m.group(1))
    cid = str(msg.chat.id)
    if cid not in chat_rules or len(chat_rules[cid])<n:
        await msg.reply_text("❌ Нет")
        return
    chat_rules[cid][n-1] = ""
    save_data()
    await msg.reply_text(f"✅ Правило #{n} удалено!", parse_mode='HTML')

async def clearrules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        await update.effective_message.reply_text("❌ Ошибка")
        return
    if not await is_admin_or_creator(update, context):
        await msg.reply_text("❌ Только админам!")
        return
    cid = str(msg.chat.id)
    if cid in chat_rules:
        chat_rules[cid]=[]
        save_data()
        await msg.reply_text("✅ Очищено!")
        return
    await msg.reply_text("ℹ️ Нет")

async def unwarn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not await is_admin_or_creator(update, context):
        return
    target, _ = await resolve_target_user(update, context)
    if not target:
        await msg.reply_text("❌ Ответьте или @/ID")
        return
    cid, uid = str(msg.chat.id), str(target.id)
    if cid not in user_warns or uid not in user_warns[cid]:
        await msg.reply_text("ℹ️ Нет варнов")
        return
    wnum = int(context.args[1]) if len(context.args)>1 and context.args[1].isdigit() else None
    if wnum:
        if wnum<1 or wnum>len(user_warns[cid][uid]):
            await msg.reply_text("❌ Неверный номер")
            return
        r = user_warns[cid][uid].pop(wnum-1)
        save_data()
        await msg.reply_text(f"✅ Варн #{wnum} снят!\n📝 {r['comment']}", parse_mode='HTML')
    else:
        cnt = len(user_warns[cid][uid])
        user_warns[cid][uid]=[]
        save_data()
        await msg.reply_text(f"✅ Все ({cnt}) сняты!", parse_mode='HTML')

def setup_rules_commands(application):
    load_data()
    application.add_handler(CommandHandler("setpseudo", setpseudo_command))
    application.add_handler(CommandHandler("setglobalpseudo", setglobalpseudo_command))
    application.add_handler(CommandHandler("checkpseudo", checkpseudo_command))
    application.add_handler(CommandHandler("setrule", setrule_command))
    application.add_handler(CommandHandler("showrules", showrules_command))
    application.add_handler(CommandHandler("clearrules", clearrules_command))
    application.add_handler(MessageHandler(filters.Regex(r'^/setrule\d+'), setrule_num_handler))
    application.add_handler(MessageHandler(filters.Regex(r'^/delrule\d+'), delrule_handler))
    application.add_handler(CommandHandler("warn", warn_command))
    application.add_handler(CommandHandler("setwarn", setwarn_command))
    application.add_handler(CommandHandler("setwarnduration", setwarnduration_command))
    application.add_handler(CommandHandler("mywarns", mywarns_command))
    application.add_handler(CommandHandler("checkwarns", checkwarns_command))
    application.add_handler(CommandHandler("unwarn", unwarn_command))
    application.add_handler(CommandHandler("mute", mute_command))
    application.add_handler(CommandHandler("unmute", unmute_command))
    application.add_handler(CommandHandler("setmuteduration", setmuteduration_command))
    application.add_handler(CommandHandler("checkmute", checkmute_command))
    application.add_handler(CommandHandler("testmute", test_mute))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, check_mutes_on_message))