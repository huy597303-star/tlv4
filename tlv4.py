import sqlite3
import re
import logging
import os
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ----------------- CẤU HÌNH HỆ THỐNG ----------------- #
TOKEN = "9291585542:AAFkdq6uxLvRsZLI2NKyN4Dxr-rONDe0kdM"
ADMIN_IDS = [9047366482]
SEPAY_API_TOKEN = "9OAOWJ7EPNEIWSUMZ93V0OACREYI8U3JTFWS1LG7WVSK4DSCUCFZIX6XHFQNBE18"

# ----------------- DATABASE ----------------- #
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

# ----------------- TELEGRAM BOT HANDLERS ----------------- #
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
        
        # --- BẢNG GIÁ RIÊNG CHO TỪNG SẢN PHẨM ---
        prices = {
            "gmail": 5000,       # Gmail giá 5k
            "facebook": 2000,    # Facebook giá 2k
            "tiktok": 2000       # TikTok giá 2k
        }
        
        # Mặc định 2,000đ nếu không khớp từ khóa nào
        price_per_item = 2000
        for key, val in prices.items():
            if key in product_name.lower():
                price_per_item = val
                break
        
        user_balance = get_user_balance(user_id)
        if user_balance < price_per_item:
            await query.edit_message_text(
                f"❌ **Số dư không đủ!**\nSản phẩm: `{product_name}`\nGiá: {price_per_item:,} VNĐ\nSố dư của bạn: {user_balance:,} VNĐ",
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
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price_per_item, user_id))
        conn.commit()
        conn.close()

        await query.edit_message_text(
            f"✅ **MUA TÀI KHOẢN THÀNH CÔNG!**\n\n"
            f"📌 **Sản phẩm:** `{product_name}`\n"
            f"💰 **Trừ số dư:** {price_per_item:,} VNĐ\n\n"
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
            "💵 **HƯỚNG DẪN NẠP TIỀN TỰ ĐỘNG (24/7)**\n\n"
            "Quý khách chuyển khoản theo thông tin bên dưới (Tiền sẽ được cộng tự động trong vài giây):\n\n"
            "💚 **VPBANK:**\n"
            "• Số tài khoản: `020420098386`\n"
            "• Chủ tài khoản: **PHAM VAN TUNG**\n\n"
            "📝 **Nội dung chuyển khoản (Bắt buộc):** `nap " + str(user_id) + "`"
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

# ----------------- ADMIN COMMANDS ----------------- #
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
        await update.message.reply_text(f"✅ **Import thành công {count} tài khoản từ tệp!**", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")

async def admin_add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        text_input = " ".join(context.args)
        if "|" not in text_input:
            await update.message.reply_text("❌ Sai cú pháp! Dùng: `/themacc Tên sản phẩm | Thông_tin_acc`", parse_mode="Markdown")
            return
            
        parts = text_input.split("|", 1)
        product_name = parts[0].strip()
        account_info = parts[1].strip()
        
        conn = sqlite3.connect("bot_store.db")
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO accounts (product_name, account_info, status)
            VALUES (?, ?, 'AVAILABLE')
        ''', (product_name, account_info))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ **Thêm tài khoản thủ công thành công!**\n\n"
            f"📌 **Sản phẩm:** `{product_name}`\n"
            f"📋 **Thông tin:** `{account_info}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")

async def admin_add_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("❌ Sai cú pháp! Dùng: `/cong [user_id] [số_tiền]`", parse_mode="Markdown")
            return
        
        target_user_id = int(args[0])
        amount = int(args[1])
        
        update_user_balance(target_user_id, amount)
        new_balance = get_user_balance(target_user_id)
        
        await update.message.reply_text(
            f"✅ **Cộng tiền thủ công thành công!**\n"
            f"👤 User ID: `{target_user_id}`\n"
            f"💰 Đã cộng: **+{amount:,} VNĐ**\n"
            f"💳 Số dư mới: **{new_balance:,} VNĐ**",
            parse_mode="Markdown"
        )
        
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🎉 **Tài khoản của bạn đã được Admin cộng tiền!**\n\n💰 Số tiền: **+{amount:,} VNĐ**\n💳 Số dư mới: **{new_balance:,} VNĐ**",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")

# ----------------- SEPAY WEBHOOK SERVER ----------------- #
async def handle_sepay_webhook(request):
    try:
        data = await request.json()
        amount = int(data.get("transferAmount", 0))
        content = data.get("content", "")
        
        match = re.search(r'nap\s*(\d+)', content, re.IGNORECASE)
        if match:
            target_user_id = int(match.group(1))
            update_user_balance(target_user_id, amount)
            new_balance = get_user_balance(target_user_id)
            
            bot = request.app['bot']
            
            try:
                await bot.send_message(
                    chat_id=target_user_id,
                    text=f"🎉 **NẠP TIỀN TỰ ĐỘNG THÀNH CÔNG!**\n\n💰 Số tiền nạp: **+{amount:,} VNĐ**\n💳 Số dư mới: **{new_balance:,} VNĐ**",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
                
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=f"🔔 **Nạp tự động SePay:**\n👤 User ID: `{target_user_id}`\n💰 Đã cộng: **+{amount:,} VNĐ**\n📝 Nội dung: `{content}`",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
                    
        return web.json_response({"status": "success"}, status=200)
    except Exception as e:
        logging.error(f"Lỗi xử lý SePay Webhook: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=400)

# ----------------- CHẠY ỨNG DỤNG ----------------- #
async def main():
    app = Application.builder().token(TOKEN).build()

    # Đăng ký các lệnh User & Admin
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("import", admin_import_file))
    app.add_handler(CommandHandler("themacc", admin_add_account))
    app.add_handler(CommandHandler("cong", admin_add_money))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Khởi tạo Telegram Bot Runner
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Tạo server HTTP Webhook cho SePay
    web_app = web.Application()
    web_app['bot'] = app.bot
    web_app.router.add_post('/sepay-webhook', handle_sepay_webhook)

    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    print(f"Bot & Webhook SePay đang chạy trên cổng {port}...")
    await site.start()

    import asyncio
    await asyncio.Event().wait()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
