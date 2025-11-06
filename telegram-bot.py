import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# --- الثوابت والمتغيرات العامة ---
TOKEN = "8427063575:AAGyQSTbjGHOrBHhZeVucVnNWc47amwR7RA"
DATA_FILE = "data.json"

queues = {}          # أدوار الشاتات (القنوات)
awaiting_input = {}  # لتخزين المرحلة الحالية من الأسئلة لكل شات (للمعلمة والحلقة)

# --- وظائف حفظ وتحميل البيانات ---

# تحميل بيانات القنوات المربوطة
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
        "🔗 استخدم **/link @اسم_القناة** لربط قناة.\n"
        "🗑️ استخدم **/unlink @اسم_القناة** لفصل قناة.\n"
        "📜 استخدم **/mychannels** لعرض القنوات المربوطة.\n"
        "🎯 بعد ما تربط قناة، استخدم **/startrole** لتبدأ الدور في أي قناة مربوطة."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def link_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لربط قناة بحساب المستخدم."""
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("اكتب اسم القناة: /link @اسم_القناة")
        return

    channel_username = context.args[0]
    try:
        # 1. جلب معلومات القناة
        channel = await context.bot.get_chat(channel_username)
        # 2. التحقق من صلاحية البوت
        bot_member = await context.bot.get_chat_member(channel.id, context.bot.id)
        if bot_member.status not in ["administrator", "creator"]:
            await update.message.reply_text("❌ البوت لازم يكون **أدمن** في القناة قبل الربط.")
            return

        # 3. حفظ القناة
        if user_id not in user_channels:
            user_channels[user_id] = []

        if channel.id not in user_channels[user_id]:
            user_channels[user_id].append(channel.id)
            save_data()
            await update.message.reply_text(f"✅ تم ربط القناة: **{channel.title}**")
        else:
            await update.message.reply_text("⚠️ القناة مربوطة بالفعل.")

    except Exception as e:
        await update.message.reply_text(f"❌ حصل خطأ: تأكد من أن البوت في القناة وأن اسمها صحيح. (الخطأ: {e})")

async def unlink_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لفصل قناة عن حساب المستخدم."""
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("اكتب اسم القناة: /unlink @اسم_القناة")
        return

    channel_username = context.args[0]
    try:
        channel = await context.bot.get_chat(channel_username)
        if user_id in user_channels and channel.id in user_channels[user_id]:
            user_channels[user_id].remove(channel.id)
            save_data()
            await update.message.reply_text(f"✅ فصلت القناة: **{channel.title}**")
        else:
            await update.message.reply_text("⚠️ القناة مش مربوطة بحسابك.")
    except Exception as e:
        await update.message.reply_text(f"❌ حصل خطأ: {e}")

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
            # التأكد من وجود username قبل عرضه
            username_display = f" (@{ch.username})" if ch.username else ""
            text += f"{idx}. **{ch.title}**{username_display}\n"
        except:
            text += f"{idx}. قناة غير متاحة (ID: {ch_id})\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def start_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعرض قائمة بالقنوات المربوطة لاختيار القناة لبدء الدور فيها."""
    user_id = str(update.effective_user.id)
    if user_id not in user_channels or not user_channels[user_id]:
        await update.message.reply_text("🚫 مفيش قنوات مربوطة. استخدم **/link @اسم_القناة** أول.")
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
#        2. منطق بدء الدور وجمع المعلومات
# ----------------------------------------

async def prompt_for_role(update: Update, context: ContextTypes.DEFAULT_TYPE, target_chat_id: int):
    """يبدأ عملية جمع المعلومات (المعلمة والحلقة) في القناة المختارة."""
    
    # ✅ التحقق الحقيقي إن كان فيه دور شغال في هذه القناة
    if target_chat_id in queues and not queues[target_chat_id].get("closed", True):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ فيه دور شغال بالفعل في هذه القناة، قم بإنهاءه أولاً."
        )
        return

    # حفظ حالة انتظار الإدخال بالـ chat_id الصحيح
    awaiting_input[target_chat_id] = {
        "step": "teacher",
        "creator_id": update.effective_user.id, # حفظ ID اللي بدأ العملية
        "creator_name": update.effective_user.full_name
    }
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="👩‍🏫 **اكتب اسم المعلمة:** (الرد هيكون في الدردشة الخاصة هنا)"
    )


async def collect_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يجمع اسم المعلمة واسم الحلقة بعد أمر start_role."""
    
    # ✅ تأكد إن الرسالة نص مش زرار
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_input = update.message.text.strip()
    
    # البحث عن أي chat_id في awaiting_input يطابق creator_id الحالي
    target_chat_id = None
    for chat_id, data in awaiting_input.items():
        if data.get("creator_id") == user_id:
            target_chat_id = chat_id
            break

    if target_chat_id is None:
        # قد يكون المستخدم يحاول يكتب نص غير أمر في الخاص بدون بدء عملية
        return

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

        # إنشاء الدور في القناة المستهدفة
        queues[target_chat_id] = {
            "creator": user_id,
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

        # حذف حالة الانتظار
        del awaiting_input[target_chat_id]

        text = (
            f"👤 *بدأ الدور:* {creator_name}\n"
            f"📚 *اسم المعلمة:* {teacher_name}\n"
            f"🏫 *اسم الحلقة:* {class_name}\n\n"
            f"🎯 *القائمة الحالية:* (فاضية)"
        )
        # إرسال رسالة الدور إلى القناة المستهدفة
        await context.bot.send_message(
            chat_id=target_chat_id,
            text=text,
            reply_markup=make_main_keyboard(target_chat_id),
            parse_mode="Markdown"
        )
        # إشعار المستخدم بنجاح العملية
        await update.message.reply_text("✅ تم إنشاء الدور بنجاح في القناة!")


# ----------------------------------------
#        3. معالجة الأزرار (Callback Queries)
# ----------------------------------------

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
        
    # المعالجة الرئيسية لجميع أزرار الدور
    if len(parts) < 2:
        await query.answer("❌ خطأ في بيانات الزر.")
        return
        
    chat_id = int(parts[1])
    q = queues.get(chat_id)

    if not q:
        await query.answer("❌ مفيش دور شغال في هذه القناة.")
        return

    # يتم هنا استخدام الكود الأصلي للدور بنفس المنطق (join, remove, close, ...)
    # التعديل الوحيد هو استخدام query.edit_message_text لتحديث رسالة الدور في القناة
    
    if action == "join":
        if q["closed"]:
            await query.answer("🚫 التسجيل مقفول.")
            return

        q["usernames"][user.id] = user.full_name

        if user.id in q["removed"]:
            await query.answer("🚫 تم حذفك من الدور. استنى الدور الجديد.")
            return

        if user.id in q["members"]:
            q["members"].remove(user.id)
            if user.id in q["all_joined"]:
                q["all_joined"].remove(user.id)
            await query.answer("❌ تم انسحابك.")
        else:
            q["members"].append(user.id)
            q["all_joined"].add(user.id)
            await query.answer("✅ تم تسجيلك!")

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
        await query.answer("تم الإلغاء ✅")

    elif action == "close":
        if not is_admin_or_creator(user.id, q):
            await query.answer("🚫 مش من صلاحياتك.")
            return
        q["closed"] = True

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

        # 🧹 حذف الدور بعد القفل
        # يتم إرسال الرسالة النهائية كرسالة جديدة لأن الرسالة الأصلية سيتم حذفها/تعديلها
        await query.message.reply_text(final_text, parse_mode="Markdown")
        # حذف رسالة الدور الأصلية بعد الإنهاء
        await query.delete_message()
        del queues[chat_id]


    elif action == "manage_admins":
        if user.id != q["creator"]:
            await query.answer("🚫 بس اللي بدأ الدور يقدر يدير المشرفين.")
            return

        # يجب أن يكون المستخدم ضمن الأعضاء ليكون مشرفاً
        members_to_manage = [uid for uid in q["all_joined"] if uid != q["creator"]]

        if not members_to_manage:
            await query.answer("📋 مفيش حد يمكن تعيينه مشرفًا غيرك.")
            return

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
        if target_id in q["admins"]:
            q["admins"].remove(target_id)
        else:
            q["admins"].add(target_id)

        # إعادة بناء لوحة المفاتيح
        members_to_manage = [uid for uid in q["all_joined"] if uid != q["creator"]]
        keyboard = []
        for uid in members_to_manage:
            name = q["usernames"].get(uid, "مجهول")
            label = f"⭐ أزل {name} من المشرفين" if uid in q["admins"] else f"⭐ عيّن {name} مشرف"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"toggle_admin|{chat_id}|{uid}")])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"cancel_remove|{chat_id}")])

        await query.edit_message_text("👮 *إدارة المشرفين:*",
                                      reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
                                      
    # بعد كل عملية زر، يتم مسح الإشعار (Answer the query)
    await query.answer()

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

    if chat_id in awaiting_input:
        del awaiting_input[chat_id]
        
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
app.add_handler(CommandHandler("link", link_channel))
app.add_handler(CommandHandler("unlink", unlink_channel))
app.add_handler(CommandHandler("mychannels", my_channels))
app.add_handler(CommandHandler("startrole", start_role))

# معالجة النصوص (جمع اسم المعلمة والحلقة)
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_info))

# معالجة الأزرار (join, remove, close, select_channel)
app.add_handler(CallbackQueryHandler(button))

# أمر الإغلاق الإجباري (يستخدم داخل الدردشة/القناة)
app.add_handler(CommandHandler("forceclose", force_close))

print("🤖 البوت شغال...")
app.run_polling()
