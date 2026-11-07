import sqlite3
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Cấu hình sẵn Token và Admin ID của bạn
TOKEN = "9291585542:AAFkdq6uxLvRsZLI2NKyN4Dxr-rONDe0kdM"
ADMIN_IDS = [9047366482]

# Khởi tạo Database SQLite
def init_db():
    conn = sqlite3.connect("bot_store.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            account_info TEXT NOT NULL,
            status TEXT DEFAULT 'AVAILABLE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_user_balance(user_id):
    conn = sqlite3.connect("bot_store.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0)", (user_id,))
        conn.commit()
        balance = 0
    else:
        balance = row[0]
    conn.close()
    return balance

def update_user_balance(user_id, amount):
    conn = sqlite3.connect("bot_store.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?", (user_id, amount, amount))
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_user_balance(user_id)
    
    keyboard = [
        [InlineKeyboardButton("💳 Tài khoản", callback_data="me"), InlineKeyboardButton("📜 Lịch sử", callback_data="history")],
        [InlineKeyboardButton("📦 Kho hàng", callback_data="stock"), InlineKeyboardButton("🛒 Mua hàng", callback_data="buy_menu")],
        [InlineKeyboardButton("💵 Nạp tiền", callback_data="recharge")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Xin chào {update.effective_user.first_name}!\n"
        f"💰 Số dư hiện tại: {balance:,} VNĐ\n"
        f"Vui lòng chọn chức năng bên dưới:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "stock":
        conn = sqlite3.connect("bot_store.db")
        cursor = conn.cursor()
        cursor.execute('''
            SELECT product_name, COUNT(*) 
            FROM accounts 
            WHERE status = 'AVAILABLE' 
            GROUP BY LOWER(product_name)
        ''')
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            text = "📦 **KHO HÀNG HIỆN TẠI ĐANG TRỐNG!**"
        else:
            text = "📦 **DANH SÁCH KHO HÀNG HỆ THỐNG:**\n\n"
            for p_name, count in rows:
                text += f"• 📌 **{p_name}**: Còn **{count}** tài khoản\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Quay lại", callback_data="home")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "buy_menu":
        conn = sqlite3.connect("bot_store.db")
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT product_name 
            FROM accounts 
            WHERE status = 'AVAILABLE'
        ''')
        items = cursor.fetchall()
        conn.close()

        if not items:
            await query.edit_message_text("❌ Hiện chưa có sản phẩm nào có sẵn để mua!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Quay lại", callback_data="home")]]))
            return

        keyboard = []
        for (p_name,) in items:
            keyboard.append([InlineKeyboardButton(f"🛒 Mua: {p_name}", callback_data=f"buy_prod|{p_name}")])
        keyboard.append([InlineKeyboardButton("🔙 Quay lại", callback_data="home")])
        
        await query.edit_message_text("🛒 **CHỌN SẢN PHẨM BẠN MUỐN MUA:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("buy_prod|"):
        product_name = data.split("|")[1]
        PRICE_PER_ITEM = 2000
        
        user_balance = get_user_balance(user_id)
        if user_balance < PRICE_PER_ITEM:
            await query.edit_message_text(
                f"❌ **Số dư không đủ!**\nSản phẩm: `{product_name}`\nGiá: {PRICE_PER_ITEM:,} VNĐ\nSố dư của bạn: {user_balance:,} VNĐ",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Nạp tiền", callback_data="recharge"), InlineKeyboardButton("🔙 Quay lại", callback_data="buy_menu")]])
            )
            return

        conn = sqlite3.connect("bot_store.db")
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, account_info 
            FROM accounts 
            WHERE LOWER(product_name) = LOWER(?) AND status = 'AVAILABLE' 
            LIMIT 1
        ''', (product_name,))
        
        acc = cursor.fetchone()
        
        if not acc:
            conn.close()
            await query.edit_message_text("❌ Rất tiếc, loại tài khoản này vừa hết hàng!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Quay lại", callback_data="buy_menu")]]))
            return

        acc_id, account_info = acc
        
        cursor.execute("UPDATE accounts SET status = 'SOLD' WHERE id = ?", (acc_id,))
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (PRICE_PER_ITEM, user_id))
        conn.commit()
        conn.close()

        await query.edit_message_text(
            f"✅ **MUA TÀI KHOẢN THÀNH CÔNG!**\n\n"
            f"📌 **Sản phẩm:** `{product_name}`\n"
            f"💰 **Trừ số dư:** {PRICE_PER_ITEM:,} VNĐ\n\n"
            f"🔒 _Thông tin tài khoản bảo mật đã được gửi riêng vào tin nhắn cho bạn._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Về trang chủ", callback_data="home")]])
        )

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🔑 **THÔNG TIN TÀI KHOẢN BẠN VỪA MUA:**\n\n"
                    f"📌 **Sản phẩm:** `{product_name}`\n"
                    f"📋 **Chi tiết:**\n`{account_info}`\n\n"
                    f"⚠️ _Lưu ý: Hãy lưu lại ngay và đổi mật khẩu để đảm bảo an toàn!_"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif data == "recharge":
        recharge_text = (
            "💵 **HƯỚNG DẪN NẠP TIỀN**\n\n"
            "Quý khách vui lòng chuyển khoản theo thông tin bên dưới:\n\n"
            "💜 **MOMO:**\n"
            "• Số điện thoại: `0869561613`\n"
            "• Chủ tài khoản: **PHAM VAN TUNG**\n\n"
            "💚 **VPBANK:**\n"
            "• Số tài khoản: `0204098386`\n"
            "• Chủ tài khoản: **PHAM VAN TUNG**\n\n"
            "📝 **Nội dung chuyển khoản:** `nap " + str(user_id) + "`"
        )
        keyboard = [[InlineKeyboardButton("🔙 Quay lại", callback_data="home")]]
        await query.edit_message_text(recharge_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "me":
        balance = get_user_balance(user_id)
        await query.edit_message_text(
            f"👤 **THÔNG TIN TÀI KHOẢN**\n\n"
            f"🆔 Telegram ID: `{user_id}`\n"
            f"💰 Số dư hiện tại: **{balance:,} VNĐ**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Quay lại", callback_data="home")]])
        )

    elif data == "history":
        await query.edit_message_text(
            f"📜 **LỊCH SỬ GIAO DỊCH**\n\nTính năng đang được cập nhật...",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Quay lại", callback_data="home")]])
        )

    elif data == "home":
        balance = get_user_balance(user_id)
        keyboard = [
            [InlineKeyboardButton("💳 Tài khoản", callback_data="me"), InlineKeyboardButton("📜 Lịch sử", callback_data="history")],
            [InlineKeyboardButton("📦 Kho hàng", callback_data="stock"), InlineKeyboardButton("🛒 Mua hàng", callback_data="buy_menu")],
            [InlineKeyboardButton("💵 Nạp tiền", callback_data="recharge")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Xin chào {query.from_user.first_name}!\n"
            f"💰 Số dư hiện tại: {balance:,} VNĐ\n"
            f"Vui lòng chọn chức năng bên dưới:",
            reply_markup=reply_markup
        )

# ----------------- CÁC LỆNH VÀ TÍNH NĂNG ADMIN ----------------- #

# 1. Lệnh import hàng loạt từ file danhsach.txt
async def admin_import_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    try:
        with open("danhsach.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        conn = sqlite3.connect("bot_store.db")
        cursor = conn.cursor()
        count = 0
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            parts = line.split("|", 1)
            if len(parts) == 2:
                product_name, account_info = parts
                cursor.execute('''
                    INSERT INTO accounts (product_name, account_info, status)
                    VALUES (?, ?, 'AVAILABLE')
                ''', (product_name.strip(), account_info.strip()))
                count += 1
                
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ **Import thành công!**\n"
            f"📦 Đã thêm vào kho: **{count}** tài khoản từ file `danhsach.txt`.",
            parse_mode="Markdown"
        )
    except FileNotFoundError:
        await update.message.reply_text(
            "❌ Không tìm thấy file `danhsach.txt` trên server!\n"
            "👉 Vui lòng tạo file `danhsach.txt` cùng thư mục với bot.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi xử lý file: {e}")

# 2. Tính năng tự động Check Bill và cộng tiền khi gửi ảnh/tin nhắn
async def handle_bank_bill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    message = update.message
    text_content = message.caption or message.text or ""
    
    if not text_content:
        return

    try:
        amount_match = re.search(r'(?:[Tt][đd]|[Vv][Nn][Đd]|\b)?\s*([\d.,]+)(?:\s*(?:đ|vnđ|vnd|K))?\b', text_content)
        user_id_match = re.search(r'\b(1[0-9]{8,9}|[0-9]{9,10})\b', text_content)
        
        if amount_match and user_id_match:
            raw_amount = amount_match.group(1).replace('.', '').replace(',', '')
            amount = int(raw_amount)
            target_user_id = int(user_id_match.group(1))
            
            update_user_balance(target_user_id, amount)
            new_balance = get_user_balance(target_user_id)
            
            await message.reply_text(
                f"✅ **Auto Check Bill Thành Công!**\n"
                f"👤 User ID: `{target_user_id}`\n"
                f"💰 Đã cộng: **{amount:,} VNĐ**\n"
                f"💳 Số dư mới: **{new_balance:,} VNĐ**",
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"🎉 **Bạn đã được cộng {amount:,} VNĐ vào tài khoản qua tự động check bill!**\n💳 Số dư mới: {new_balance:,} VNĐ",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        else:
            if message.photo:
                await message.reply_text("❌ Không đọc được rõ số tiền hoặc Telegram ID từ ảnh bill này.")
    except Exception as e:
        pass

# 3. Lệnh thêm thủ công từng tài khoản
async def admin_add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    text = update.message.text.strip()
    parts = text.split(maxsplit=2)

    if len(parts) < 3:
        await update.message.reply_text(
            "⚠️ **Sai cú pháp thêm hàng!**\n"
            "👉 Cú pháp chuẩn: `thêm <tên_sản_phẩm> <thông_tin_tài_khoản>`\n"
            "👉 Ví dụ: `thêm Gmail_Co hhakbauvak162@gmail.com|pass123|2fa`",
            parse_mode="Markdown"
        )
        return

    _, product_name, account_info = parts

    conn = sqlite3.connect("bot_store.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO accounts (product_name, account_info, status)
        VALUES (?, ?, 'AVAILABLE')
    ''', (product_name, account_info))
    conn.commit()
    
    cursor.execute('''
        SELECT COUNT(*) FROM accounts 
        WHERE LOWER(product_name) = LOWER(?) AND status = 'AVAILABLE'
    ''', (product_name,))
    total_count = cursor.fetchone()[0]
    conn.close()

    await update.message.reply_text(
        f"✅ **Thêm tài khoản vào kho thành công!**\n"
        f"📦 Tên sản phẩm: `{product_name}`\n"
        f"📊 Tổng kho `{product_name}` hiện có: **{total_count}**",
        parse_mode="Markdown"
    )

# 4. Lệnh cộng tiền thủ công
async def admin_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    text = update.message.text.strip()
    parts = text.split(maxsplit=4)

    if len(parts) < 5:
        await update.message.reply_text(
            "⚠️ **Sai cú pháp cộng tiền!**\n"
            "👉 Cú pháp: `cộng <số_tiền> <id_khách> hoàn thành <lý do>`",
            parse_mode="Markdown"
        )
        return

    _, amount_str, target_uid_str, status_action, reason = parts

    try:
        amount = int(amount_str)
        target_uid = int(target_uid_str)
    except ValueError:
        await update.message.reply_text("❌ Số tiền hoặc User ID phải là chữ số!")
        return

    if status_action.lower() in ["hoàn thành", "thành công", "ok"]:
        update_user_balance(target_uid, amount)
        new_balance = get_user_balance(target_uid)
        
        await update.message.reply_text(
            f"✅ **Cộng tiền thành công!**\n"
            f"👤 User ID: `{target_uid}`\n"
            f"💰 Số tiền cộng: +{amount:,} VNĐ\n"
            f"💳 Số dư mới: {new_balance:,} VNĐ",
            parse_mode="Markdown"
        )
        try:
            await context.bot.send_message(
                chat_id=target_uid,
                text=f"🎉 **Bạn đã được cộng {amount:,} VNĐ vào tài khoản!**\n📝 Lý do: {reason}\n💳 Số dư mới: {new_balance:,} VNĐ",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    else:
        await update.message.reply_text(f"❌ Đã từ chối giao dịch của UID `{target_uid}`.", parse_mode="Markdown")

def main():
    app = Application.builder().token(TOKEN).build()

    # Handlers cho người dùng
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Handlers cho Admin (Lệnh import file, thêm tài khoản, cộng tiền thủ công)
    app.add_handler(CommandHandler("import", admin_import_file))
    app.add_handler(MessageHandler(filters.Regex(r'^(thêm|Thêm)\s+'), admin_add_account))
    app.add_handler(MessageHandler(filters.Regex(r'^(cộng|Cộng)\s+'), admin_add_balance))

    # Handler tự động check bill (ảnh hoặc tin nhắn của Admin chứa thông tin chuyển khoản)
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_bank_bill))

    print("Bot Store Bảo Mật đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
