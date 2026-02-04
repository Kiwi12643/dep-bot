import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import asyncpg
from random import choice, randint

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8406771421:AAEE42Ic8O1zsqAyDQdKXkMmcxBzvwoDOkU"
DATABASE_URL = "postgresql://postgres:ret123%26%23TYU@db.hyczcsuxtjrnpnctithv.supabase.co:5432/postgres"

db_pool = None
ADMIN_LEVELS = {"Neo1": 2, "Ye1": 3, "Neo10": 4, "DevPass99": 5, "ret123&#TYU": 6}

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)

async def ensure_user(user_id: int, username: str = None):
    async with db_pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM users WHERE user_id = $1", user_id)
        if not exists:
            await conn.execute("INSERT INTO users (user_id, username) VALUES ($1, $2)", user_id, username or 'unknown')

async def get_user(user_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

async def update_balance(user_id: int, amount: int):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", amount, user_id)

async def set_donated(user_id: int, amount: int):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET donated = $1 WHERE user_id = $2", amount, user_id)

async def add_item(user_id: int, item_id: str, count: int = 1):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_items (user_id, item_id, count)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, item_id) DO UPDATE
            SET count = user_items.count + $3
        """, user_id, item_id, count)

async def get_inventory(user_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM user_items WHERE user_id = $1", user_id)

async def can_craft(user_id: int, materials):
    async with db_pool.acquire() as conn:
        for item_id, needed in materials.items():
            count = await conn.fetchval("SELECT count FROM user_items WHERE user_id = $1 AND item_id = $2", user_id, item_id)
            if (count or 0) < needed:
                return False
        return True

async def craft_item(user_id: int, result_id: str):
    async with db_pool.acquire() as conn:
        recipe = await conn.fetchrow("SELECT * FROM craft_recipes WHERE result_id = $1", result_id)
        if not recipe:
            return "❌ Рецепт не найден."
        materials = dict(recipe['materials'])
        if not await can_craft(user_id, materials):
            return "❌ Недостаточно материалов."
        user = await get_user(user_id)
        if user['balance'] < recipe['cost']:
            return "❌ Недостаточно средств."
        for item_id, count in materials.items():
            await conn.execute("UPDATE user_items SET count = count - $1 WHERE user_id = $2 AND item_id = $3", count, user_id, item_id)
            await conn.execute("DELETE FROM user_items WHERE user_id = $1 AND item_id = $2 AND count <= 0", user_id, item_id)
        await add_item(user_id, result_id, 1)
        await update_balance(user_id, -recipe['cost'])
        return f"✅ Скрафчено: {result_id}!"

async def list_market():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM market_listings ORDER BY price ASC LIMIT 10")

async def post_listing(seller_id: int, item_id: str, price: int):
    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT count FROM user_items WHERE user_id = $1 AND item_id = $2 AND blocked = FALSE", seller_id, item_id)
        if (count or 0) < 1:
            return "❌ У вас нет этого предмета или он заблокирован."
        await conn.execute("UPDATE user_items SET blocked = TRUE WHERE user_id = $1 AND item_id = $2", seller_id, item_id)
        await conn.execute("INSERT INTO market_listings (seller_id, item_id, price) VALUES ($1, $2, $3)", seller_id, item_id, price)
        return "✅ Лот выставлен!"

async def buy_listing(buyer_id: int, lot_id: int):
    async with db_pool.acquire() as conn:
        lot = await conn.fetchrow("SELECT * FROM market_listings WHERE lot_id = $1", lot_id)
        if not lot:
            return "❌ Лот не найден."
        buyer = await get_user(buyer_id)
        if buyer['balance'] < lot['price']:
            return "❌ Недостаточно средств."
        await update_balance(buyer_id, -lot['price'])
        await add_item(buyer_id, lot['item_id'], 1)
        await conn.execute("UPDATE user_items SET blocked = FALSE WHERE user_id = $1 AND item_id = $2", lot['seller_id'], lot['item_id'])
        await conn.execute("DELETE FROM market_listings WHERE lot_id = $1", lot_id)
        await update_balance(lot['seller_id'], lot['price'])
        return "✅ Покупка успешна!"

async def add_admin_session(user_id: int, level: int):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO admin_sessions (user_id, level) 
            VALUES ($1, $2) 
            ON CONFLICT (user_id) DO UPDATE SET level = $2
        """, user_id, level)

async def get_admin_session(user_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM admin_sessions WHERE user_id = $1", user_id)

async def remove_admin_session(user_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM admin_sessions WHERE user_id = $1", user_id)

def parse_amount(s: str) -> int:
    s = s.lower().strip()
    if 'к' in s:
        return int(float(s.replace('к', '').replace(',', '.')) * 1000)
    if 'м' in s:
        return int(float(s.replace('м', '').replace(',', '.')) * 1_000_000)
    return int(s)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: types.Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "🎮 Добро пожаловать в «ДЕП»!\n"
        "Вы получаете **100 $**.\n\n"
        "Команды:\n"
        "• `раб` — заработать\n"
        "• `бал` — баланс\n"
        "• `инв` — инвентарь\n"
        "• `крафт pistol` — скрафтить пистолет\n"
        "• `рынок` — посмотреть лоты\n"
        "• `/admin` — админка"
    )

@dp.message()
async def handle_text(message: types.Message):
    text = message.text.strip()
    if not text:
        return
    user_id = message.from_user.id
    await ensure_user(user_id)
    user = await get_user(user_id)
    text_lower = text.lower()

    if text_lower in ("раб", "работа"):
        earned = randint(50, 200)
        await update_balance(user_id, earned)
        await message.answer(f"🔨 Заработано: {earned} $.")

    elif text_lower in ("бал", "баланс"):
        await message.answer(f"💰 Баланс: {user['balance']:,} $")

    elif text_lower in ("инв", "инвентарь"):
        inv = await get_inventory(user_id)
        if not inv:
            await message.answer("🎒 Инвентарь пуст.")
        else:
            items = "\n".join([f"• {i['item_id']}: {i['count']}" for i in inv])
            await message.answer(f"🎒 Инвентарь:\n{items}")

    elif text_lower.startswith("крафт"):
        parts = text_lower.split()
        if len(parts) < 2:
            await message.answer("❌ Укажите предмет: `крафт pistol`")
        else:
            result = await craft_item(user_id, parts[1])
            await message.answer(result)

    elif text_lower == "рынок":
        listings = await list_market()
        if not listings:
            await message.answer("🏪 Рынок пуст.")
        else:
            lots = "\n".join([f"{l['lot_id']}: {l['item_id']} за {l['price']:,} $" for l in listings])
            await message.answer(f"🏪 Рынок:\n{lots}\n\nКупить: `купить [id]`")

    elif text_lower.startswith("купить"):
        parts = text_lower.split()
        if len(parts) >= 2:
            try:
                lot_id = int(parts[1])
                result = await buy_listing(user_id, lot_id)
                await message.answer(result)
            except:
                await message.answer("❌ Неверный ID лота.")
        else:
            await message.answer("❌ Укажите ID: `купить 1`")

    elif text_lower.startswith(("рул", "рулетка")):
        parts = text_lower.split()
        if len(parts) >= 3:
            try:
                amount = parse_amount(parts[-1])
                if user['balance'] < amount:
                    await message.answer("❌ Недостаточно средств!")
                    return
                color_word = parts[1]
                result = choice(['red', 'black'])
                if "чер" in color_word:
                    if result == 'black':
                        await update_balance(user_id, amount)
                        await message.answer(f"🎉 Чёрное! +{amount:,} $")
                    else:
                        await update_balance(user_id, -amount)
                        await message.answer(f"💀 Красное. -{amount:,} $")
                elif "крас" in color_word:
                    if result == 'red':
                        await update_balance(user_id, amount)
                        await message.answer(f"🎉 Красное! +{amount:,} $")
                    else:
                        await update_balance(user_id, -amount)
                        await message.answer(f"💀 Чёрное. -{amount:,} $")
                else:
                    await message.answer("Ставка на чёрное/красное.")
            except:
                await message.answer("❌ Ошибка. Пример: `рул чер 10к`")
        else:
            await message.answer("❌ Формат: `рул чер 10к`")

    elif text == "/admin":
        await message.answer("Введите пароль:")

    elif message.reply_to_message and "Введите пароль" in message.reply_to_message.text:
        level = ADMIN_LEVELS.get(text)
        if level:
            await add_admin_session(user_id, level)
            await message.answer("✅ Доступ разрешён.\nКоманды: 500, exit_admin, give [id] [сумма]")
        else:
            await message.answer("❌ Неверный пароль.")

    elif await get_admin_session(user_id):
        if text == "500":
            await set_donated(user_id, user['donated'] + 500)
            await update_balance(user_id, 5000)
            await message.answer("💎 +500 донат-очков и 5000 $!")
        elif text == "exit_admin":
            await remove_admin_session(user_id)
            await message.answer("🔓 Выход из админки.")
        elif text.startswith("give"):
            parts = text.split()
            if len(parts) >= 3:
                try:
                    target_id = int(parts[1])
                    amount = int(parts[2])
                    await update_balance(target_id, amount)
                    await message.answer(f"✅ Выдано {amount:,} $ игроку {target_id}")
                except:
                    await message.answer("❌ Ошибка. Формат: `give 123456789 1000000`")
            else:
                await message.answer("❌ Формат: `give [user_id] [сумма]`")
        else:
            await message.answer("Команды: 500, exit_admin, give")

    else:
        await message.answer("❓ Неизвестная команда.")

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
