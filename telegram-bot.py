import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# --- الثوابت والمتغيرات العامة ---
TOKEN = "8246108964:AAGTQI8zQl6rXqhLVG7_8NyFj4YqO35dMVg"
DATA_FILE = "data.json"

queues = {}          # أدوار الشاتات (القنوات)
awaiting_input = {}  # لتخزين المرحلة الحالية من الأسئلة لكل شات أو مستخدم (للمعلمة والحلقة أو الربط/الفصل)

# --- وظائف حفظ وتحميل البيانات ---

try:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        user_channels = json.load(f)
except FileNotFoundError:
    user_channels = {}

def save_data():
    """يحفظ بيانات القنوات المربوطة في ملف JSON."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(user_channels, f, ensure_ascii=False, indent=2)

# --- وظائف المساعدة الرئيسية للدور ---

def make_main_keyboard(chat_id):
    """ينشئ لوحة المفاتيح الرئيسية للدور."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 انضم / انسحب", callback_data=f"join|{chat_id}")
        ],
        [
            InlineKeyboardButton("🗑️ ريموف", callback_data=f"remove_menu|{chat_id}"),
            InlineKeyboardButton("🔒 إنهاء الدور", callback_data=f"close|{chat_id}")
        ],
        [
            InlineKeyboardButton("⭐ إدارة المشرفين", callback_data=f"manage_admins|{chat_id}")
        ]
    ])

def is_admin_or_creator(user_id, q):
    """يتحقق إن كان المستخدم هو المنشئ أو مشرف في الدور."""
    return user_id == q["creator"] or user_id in q["admins"]

# ----------------------------------------
#        1. أوامر الربط والإدارة (في الخاص)
# ----------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعرض رسالة الترحيب والأوامر."""
    text = (
        "أهلاً 👋\nأنا بوت إدارة القنوات والدور.\n\n"
        "🔗 استخدم **/link** لربط قناة.\n"
        "🗑️ استخدم **/unlink** لفصل قناة.\n"
        "📜 استخدم **/mychannels** لعرض القنوات المربوطة.\n"
        "🎯 بعد ما تربط قناة، استخدم **/startrole** لتبدأ الدور في أي قناة مربوطة."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def link_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يبدأ عملية طلب اسم القناة للربط."""
    user_id = str(update.effective_user.id)
    # استخدام user_id كمفتاح للانتظار في الدردشة الخاصة
    awaiting_input[user_id] = {"step": "link_channel", "chat_id": update.effective_chat.id} 
    await update.message.reply_text("🔗 **أرسل الآن اسم القناة** (مع @) التي تود ربطها:")

async def unlink_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يبدأ عملية طلب اسم القناة للفصل."""
    user_id = str(update.effective_user.id)
    awaiting_input[user_id] = {"step": "unlink_channel", "chat_id": update.effective_chat.id}
    await update.message.reply_text("🗑️ **أرسل الآن اسم القناة** (مع @) التي تود فصلها:")


async def my_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لعرض القنوات المربوطة للمستخدم."""
    user_id = str(update.effective_user.id)
    if user_id not in user_channels or not user_channels[user_id]:
        await update.message.reply_text("📭 مفيش قنوات مربوطة.")
        return

    text = "📋 القنوات المربوطة:\n"
    for idx, ch_id in enumerate(user_channels[user_id], start=1):
        try:
            ch = await context.bot.get_chat(ch_id)
            username_display = f" (@{ch.username})" if ch.username else ""
            text += f"{idx}. **{ch.title}**{username_display}\n"
        except:
            text += f"{idx}. قناة غير متاحة (ID: {ch_id})\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def start_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعرض قائمة بالقنوات المربوطة لاختيار القناة لبدء الدور فيها."""
    user_id = str(update.effective_user.id)
    if user_id not in user_channels or not user_channels[user_id]:
        await update.message.reply_text("🚫 مفيش قنوات مربوطة. استخدم **/link** أول.")
        return

    text = "اختر القناة لبدء الدور:\n"
    keyboard = []
    for ch_id in user_channels[user_id]:
        try:
            ch = await context.bot.get_chat(ch_id)
            keyboard.append([InlineKeyboardButton(ch.title, callback_data=f"select_channel|{ch_id}")])
        except:
            continue
    
    if not keyboard:
        await update.message.reply_text("⚠️ لم يتم العثور على أي قنوات متاحة للبدء فيها.")
        return

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ----------------------------------------
#        2. منطق بدء الدور وجمع المعلومات / الربط والفصل
# ----------------------------------------

async def prompt_for_role(update: Update, context: ContextTypes.DEFAULT_TYPE, target_chat_id: int):
    """يبدأ عملية جمع المعلومات (المعلمة والحلقة) في القناة المختارة."""
    
    if target_chat_id in queues and not queues[target_chat_id].get("closed", True):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ فيه دور شغال بالفعل في هذه القناة، قم بإنهاءه أولاً."
        )
        return

    # استخدام target_chat_id كمفتاح للانتظار لعملية بدء الدور
    awaiting_input[target_chat_id] = {
        "step": "teacher",
        "creator_id": update.effective_user.id,
        "creator_name": update.effective_user.full_name
    }
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="👩‍🏫 **اكتب اسم المعلمة:** (الرد هيكون في الدردشة الخاصة هنا)"
    )


async def collect_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يجمع اسم المعلمة/الحلقة أو اسم القناة للربط/الفصل."""
    
    if not update.message or not update.message.text:
        return

    user_id = str(update.effective_user.id)
    user_input = update.message.text.strip()

    # 1. البحث عن حالة انتظار لعمليات الربط/الفصل (المفتاح هو user_id)
    if user_id in awaiting_input and user_id == str(awaiting_input[user_id].get("creator_id", user_id)):
        state = awaiting_input.pop(user_id) # إزالة الحالة فوراً لمنع التكرار
        step = state["step"]
        channel_username = user_input.split()[0] # نأخذ أول كلمة فقط للتأكد أنه اسم قناة

        # --- معالجة الربط ---
        if step == "link_channel":
            try:
                channel = await context.bot.get_chat(channel_username)
                bot_member = await context.bot.get_chat_member(channel.id, context.bot.id)
                
                if bot_member.status not in ["administrator", "creator"]:
                    await update.message.reply_text("❌ البوت لازم يكون **أدمن** في القناة قبل الربط.")
                    return
                
                if user_id not in user_channels:
                    user_channels[user_id] = []

                if channel.id not in user_channels[user_id]:
                    user_channels[user_id].append(channel.id)
                    save_data()
                    await update.message.reply_text(f"✅ تم ربط القناة: **{channel.title}**")
                else:
                    await update.message.reply_text("⚠️ القناة مربوطة بالفعل.")
            except Exception as e:
                await update.message.reply_text(f"❌ حصل خطأ. تأكد من إرسال اسم قناة صحيح (مع @) ومن كون البوت في القناة.")
            return

        # --- معالجة الفصل ---
        elif step == "unlink_channel":
            try:
                channel = await context.bot.get_chat(channel_username)
                if user_id in user_channels and channel.id in user_channels[user_id]:
                    user_channels[user_id].remove(channel.id)
                    save_data()
                    await update.message.reply_text(f"✅ فصلت القناة: **{channel.title}**")
                else:
                    await update.message.reply_text("⚠️ القناة مش مربوطة بحسابك.")
            except Exception as e:
                await update.message.reply_text(f"❌ حصل خطأ. تأكد من إرسال اسم قناة صحيح (مع @).")
            return


    # 2. البحث عن حالة انتظار لعملية بدء الدور (المفتاح هو chat_id القناة)
    
    # تحديد target_chat_id من مفاتيح awaiting_input التي ليست user_id
    target_chat_id = None
    for chat_id, data in awaiting_input.items():
        # التأكد من أن المفتاح هو عدد صحيح (chat_id) وأن المستخدم هو من بدأ العملية
        if isinstance(chat_id, int) and data.get("creator_id") == update.effective_user.id:
            target_chat_id = chat_id
            break

    if target_chat_id is None:
        return # ليس هناك عملية انتظار قائمة لهذا المستخدم

    step = awaiting_input[target_chat_id]["step"]

    if step == "teacher":
        awaiting_input[target_chat_id]["teacher"] = user_input
        awaiting_input[target_chat_id]["step"] = "class_name"
        await update.message.reply_text("📘 **اكتب اسم الحلقة:**")
        return

    elif step == "class_name":
        teacher_name = awaiting_input[target_chat_id]["teacher"]
        class_name = user_input
        creator_name = awaiting_input[target_chat_id]["creator_name"]

        queues[target_chat_id] = {
            "creator": update.effective_user.id,
            "creator_name": creator_name,
            "admins": set(),
            "members": [],
            "removed": set(),
            "all_joined": set(),
            "closed": False,
            "usernames": {},
            "teacher_name": teacher_name,
            "class_name": class_name
        }

        del awaiting_input[target_chat_id]

        text = (
            f"👤 *بدأ الدور:* {creator_name}\n"
            f"📚 *اسم المعلمة:* {teacher_name}\n"
            f"🏫 *اسم الحلقة:* {class_name}\n\n"
            f"🎯 *القائمة الحالية:* (فاضية)"
        )
        await context.bot.send_message(
            chat_id=target_chat_id,
            text=text,
            reply_markup=make_main_keyboard(target_chat_id),
            parse_mode="Markdown"
        )
        await update.message.reply_text("✅ تم إنشاء الدور بنجاح في القناة!")


# ----------------------------------------
#        3. معالجة الأزرار (Callback Queries)
# ----------------------------------------
# (هذه الدالة تبقى كما هي، تستخدم التعديلات لسرعة الاستجابة والإشعارات)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = query.from_user
    parts = data.split("|")
    action = parts[0]
    
    # معالجة اختيار القناة للبدء فيها
    if action == "select_channel":
        target_chat_id = int(parts[1])
        await query.answer(f"اخترت القناة. سيتم بدء إدخال البيانات.")
        await prompt_for_role(update, context, target_chat_id)
        return
        
    if len(parts) < 2:
        await query.answer("❌ خطأ في بيانات الزر.")
        return
        
    chat_id = int(parts[1])
    q = queues.get(chat_id)

    if not q:
        await query.answer("❌ مفيش دور شغال في هذه القناة.") 
        return

    
    if action == "join":
        if q["closed"]:
            await query.answer("🚫 التسجيل مقفول.") 
            return

        q["usernames"][user.id] = user.full_name

        if user.id in q["removed"]:
            await query.answer("🚫 تم حذفك من الدور. استنى الدور الجديد.")
            return

        message = ""
        if user.id in q["members"]:
            q["members"].remove(user.id)
            if user.id in q["all_joined"]:
                q["all_joined"].remove(user.id)
            message = "❌ تم انسحابك."
        else:
            q["members"].append(user.id)
            q["all_joined"].add(user.id)
            message = "✅ تم تسجيلك!"

        await query.answer(message) 

        members_text = "\n".join(
            [f"{i+1}. {q['usernames'].get(uid, 'مجهول')}" for i, uid in enumerate(q["members"])]
        ) or "(فاضية)"
        text = (
            f"👤 *بدأ الدور:* {q['creator_name']}\n"
            f"📚 *اسم المعلمة:* {q['teacher_name']}\n"
            f"🏫 *اسم الحلقة:* {q['class_name']}\n\n"
            f"🎯 *القائمة الحالية:*\n{members_text}"
        )
        await query.edit_message_text(text, reply_markup=make_main_keyboard(chat_id), parse_mode="Markdown")

    elif action == "remove_menu":
        if not is_admin_or_creator(user.id, q):
            await query.answer("🚫 مش من صلاحياتك.")
            return
        if not q["members"]:
            await query.answer("📋 مفيش حد في الدور.")
            return
        
        await query.answer()

        keyboard = []
        for i, uid in enumerate(q["members"]):
            name = q["usernames"].get(uid, "مجهول")
            keyboard.append([InlineKeyboardButton(f"❌ {name}", callback_data=f"remove_member|{chat_id}|{i}")])
        keyboard.append([InlineKeyboardButton("🔙 إلغاء", callback_data=f"cancel_remove|{chat_id}")])

        text = "🗑️ *اختر الاسم اللي عايز تمسحه:*"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif action == "remove_member":
        if not is_admin_or_creator(user.id, q):
            await query.answer("🚫 مش من صلاحياتك.")
            return
        index = int(parts[2])
        if 0 <= index < len(q["members"]):
            target = q["members"].pop(index)
            q["removed"].add(target)
            
        await query.answer("✅ تم حذف العضو.")

        members_text = "\n".join(
            [f"{i+1}. {q['usernames'].get(uid, 'مجهول')}" for i, uid in enumerate(q["members"])]
        ) or "(فاضية)"
        text = (
            f"👤 *بدأ الدور:* {q['creator_name']}\n"
            f"📚 *اسم المعلمة:* {q['teacher_name']}\n"
            f"🏫 *اسم الحلقة:* {q['class_name']}\n\n"
            f"🎯 *القائمة الحالية:*\n{members_text}"
        )
        await query.edit_message_text(text, reply_markup=make_main_keyboard(chat_id), parse_mode="Markdown")

    elif action == "cancel_remove":
        await query.answer("تم الإلغاء ✅")
        
        members_text = "\n".join(
            [f"{i+1}. {q['usernames'].get(uid, 'مجهول')}" for i, uid in enumerate(q["members"])]
        ) or "(فاضية)"
        text = (
            f"👤 *بدأ الدور:* {q['creator_name']}\n"
            f"📚 *اسم المعلمة:* {q['teacher_name']}\n"
            f"🏫 *اسم الحلقة:* {q['class_name']}\n\n"
            f"🎯 *القائمة الحالية:*\n{members_text}"
        )
        await query.edit_message_text(text, reply_markup=make_main_keyboard(chat_id), parse_mode="Markdown")

    elif action == "close":
        if not is_admin_or_creator(user.id, q):
            await query.answer("🚫 مش من صلاحياتك.")
            return
        q["closed"] = True
        
        await query.answer("🔒 تم إنهاء الدور.")

        all_joined = list(q["all_joined"])
        removed = list(q["removed"])
        remaining = [uid for uid in q["members"] if uid not in removed]

        full_list_text = "\n".join(
            [f"{i+1}. {q['usernames'].get(uid, 'مجهول')}" for i, uid in enumerate(all_joined)]
        ) or "(فاضية)"
        removed_text = "\n".join(
            [f"{i+1}. {q['usernames'].get(uid, 'مجهول')}" for i, uid in enumerate(removed)]
        ) or "(مفيش)"
        remaining_text = "\n".join(
            [f"{i+1}. {q['usernames'].get(uid, 'مجهول')}" for i, uid in enumerate(remaining)]
        ) or "(مفيش)"

        final_text = (
            f"👤 *بدأ الدور:* {q['creator_name']}\n"
            f"📚 *اسم المعلمة:* {q['teacher_name']}\n"
            f"🏫 *اسم الحلقة:* {q['class_name']}\n\n"
            "📋 *القائمة النهائية للدور:*\n\n"
            "👥 *كل اللي شاركوا فعليًا:*\n"
            f"{full_list_text}\n\n"
            "✅ *تمت القراءه:*\n"
            f"{removed_text}\n\n"
            "❌ *لم يقرأ:*\n"
            f"{remaining_text}\n\n"
            "🛑 *تم إنهاء الدور.*"
        )

        await query.message.reply_text(final_text, parse_mode="Markdown")
        await query.delete_message()
        del queues[chat_id]


    elif action == "manage_admins":
        if user.id != q["creator"]:
            await query.answer("🚫 بس اللي بدأ الدور يقدر يدير المشرفين.")
            return

        members_to_manage = [uid for uid in q["all_joined"] if uid != q["creator"]]

        if not members_to_manage:
            await query.answer("📋 مفيش حد يمكن تعيينه مشرفًا غيرك.")
            return
            
        await query.answer()

        keyboard = []
        for uid in members_to_manage:
            name = q["usernames"].get(uid, "مجهول")
            label = f"⭐ أزل {name} من المشرفين" if uid in q["admins"] else f"⭐ عيّن {name} مشرف"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"toggle_admin|{chat_id}|{uid}")])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"cancel_remove|{chat_id}")])

        await query.edit_message_text("👮 *إدارة المشرفين:*",
                                      reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif action == "toggle_admin":
        if user.id != q["creator"]:
            await query.answer("🚫 بس اللي بدأ الدور يقدر يعمل كده.")
            return
        target_id = int(parts[2])
        
        message = ""
        if target_id in q["admins"]:
            q["admins"].remove(target_id)
            message = "❌ تم إزالة الإشراف."
        else:
            q["admins"].add(target_id)
            message = "⭐ تم تعيينه مشرفًا."
            
        await query.answer(message)

        members_to_manage = [uid for uid in q["all_joined"] if uid != q["creator"]]
        keyboard = []
        for uid in members_to_manage:
            name = q["usernames"].get(uid, "مجهول")
            label = f"⭐ أزل {name} من المشرفين" if uid in q["admins"] else f"⭐ عيّن {name} مشرف"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"toggle_admin|{chat_id}|{uid}")])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"cancel_remove|{chat_id}")])

        await query.edit_message_text("👮 *إدارة المشرفين:*",
                                      reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ----------------------------------------
#        4. أمر الإغلاق الإجباري
# ----------------------------------------

async def force_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لقفل الدور إجباريًا (أي حد يستخدمه)."""
    chat_id = update.effective_chat.id
    user_name = update.effective_user.full_name

    if chat_id in queues:
        del queues[chat_id]
        closed_queue_message = f"🚨 تم حذف الدور المفتوح في هذه الدردشة بواسطة **{user_name}** ✅"
    else:
        closed_queue_message = f"⚠️ مفيش دور مفتوح حاليًا في هذه الدردشة ليتم حذفه."

    # مسح أي حالة انتظار تخص الشات المحدد إذا كان مفتاحه هو chat_id
    if chat_id in awaiting_input:
        del awaiting_input[chat_id]
    
    # مسح أي حالة انتظار تخص المستخدم نفسه إذا كان يحاول الربط/الفصل
    user_id_str = str(update.effective_user.id)
    if user_id_str in awaiting_input:
        del awaiting_input[user_id_str]
        
    await update.message.reply_text(
        closed_queue_message,
        parse_mode="Markdown"
    )

# ----------------------------------------
#        5. إعداد التطبيق (Main)
# ----------------------------------------

app = ApplicationBuilder().token(TOKEN).build()

# أوامر الربط والإدارة (في الخاص)
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("link", link_prompt)) # تم تغيير المعالج
app.add_handler(CommandHandler("unlink", unlink_prompt)) # تم تغيير المعالج
app.add_handler(CommandHandler("mychannels", my_channels))
app.add_handler(CommandHandler("startrole", start_role))

# معالجة النصوص (جمع اسم المعلمة والحلقة و الربط/الفصل)
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_info))

# معالجة الأزرار (join, remove, close, select_channel)
app.add_handler(CallbackQueryHandler(button))

# أمر الإغلاق الإجباري (يستخدم داخل الدردشة/القناة)
app.add_handler(CommandHandler("forceclose", force_close))

print("🤖 البوت شغال...")
app.run_polling()
