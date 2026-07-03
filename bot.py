import asyncio
import json
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

# ---------- Config (Railway variables'dan o'qiladi) ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_FILE = DATA_DIR / "packs.json"

# ---------- Kategoriyalar (keyboarddagi 4 tugma) ----------
# Nomlarni bemalol o'zgartirsang bo'ladi — keyboard avtomatik yangilanadi.
CATEGORIES = [
    "Anim Texture pack",
    "18+ Texture pack",
    "1.21+",
    "1.16+",
]

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# admin .zip yuborganda qaysi bo'limga qo'shishni kutish uchun vaqtinchalik xotira
pending = {}

# ---------- Saqlash yordamchilari ----------
def load_packs():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return []

def save_packs(packs):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(packs, ensure_ascii=False, indent=2), encoding="utf-8")

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def main_keyboard() -> ReplyKeyboardMarkup:
    # 4 ta tugma — 2 qatorda 2 tadan
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CATEGORIES[0]), KeyboardButton(text=CATEGORIES[1])],
            [KeyboardButton(text=CATEGORIES[2]), KeyboardButton(text=CATEGORIES[3])],
        ],
        resize_keyboard=True,
    )

# ---------- /start: pastda 4 ta tugmali keyboard ----------
@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "\U0001F44B Salom! Quyidagi bo'limlardan birini tanlang \U0001F447",
        reply_markup=main_keyboard(),
    )

# ---------- Kategoriya tugmasi bosilganda o'sha bo'lim pack'lari ----------
@dp.message(F.text.in_(CATEGORIES))
async def on_category(message: Message):
    category = message.text
    packs = [p for p in load_packs() if p.get("category") == category]
    if not packs:
        await message.answer(f"“{category}” bo'limida hozircha pack yo'q \U0001F614")
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=p["title"], callback_data=f"get:{p['id']}")]
            for p in packs
        ]
    )
    await message.answer(f"\U0001F4E6 <b>{category}</b> — mavjud pack'lar:", reply_markup=kb)

# ---------- Pack tugmasi bosilganda .zip yuboriladi ----------
@dp.callback_query(F.data.startswith("get:"))
async def cb_get(callback: CallbackQuery):
    pack_id = callback.data.split(":", 1)[1]
    pack = next((p for p in load_packs() if p["id"] == pack_id), None)
    if pack is None:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await callback.message.answer_document(
        document=pack["file_id"],
        caption=f"\U0001F4E6 <b>{pack['title']}</b>",
    )
    await callback.answer()

# ---------- Admin: .zip yuboradi → bo'lim tanlashni so'raydi ----------
@dp.message(F.document)
async def on_document(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Faqat owner pack qo'sha oladi.")
        return
    doc = message.document
    if not (doc.file_name or "").lower().endswith(".zip"):
        await message.answer("Faqat .zip fayl qabul qilinadi.")
        return
    pending[message.from_user.id] = {
        "file_id": doc.file_id,
        "file_name": doc.file_name,
        "title": doc.file_name.rsplit(".zip", 1)[0],
    }
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=c, callback_data=f"cat:{i}")]
            for i, c in enumerate(CATEGORIES)
        ]
    )
    await message.answer("Qaysi bo'limga qo'shamiz?", reply_markup=kb)

# ---------- Admin: bo'lim tanlanganda pack saqlanadi ----------
@dp.callback_query(F.data.startswith("cat:"))
async def cb_category(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    data = pending.get(callback.from_user.id)
    if not data:
        await callback.answer("Avval .zip fayl yuboring.", show_alert=True)
        return
    category = CATEGORIES[int(callback.data.split(":", 1)[1])]
    packs = load_packs()
    new_id = str(max([int(p["id"]) for p in packs], default=0) + 1)
    packs.append({
        "id": new_id,
        "title": data["title"],
        "file_id": data["file_id"],
        "file_name": data["file_name"],
        "category": category,
    })
    save_packs(packs)
    pending.pop(callback.from_user.id, None)
    await callback.message.answer(f"\u2705 Qo'shildi: <b>{data['title']}</b>\nBo'lim: {category}")
    await callback.answer()

# ---------- Admin: ro'yxat va o'chirish ----------
@dp.message(Command("list"))
async def cmd_list(message: Message):
    if not is_admin(message.from_user.id):
        return
    packs = load_packs()
    if not packs:
        await message.answer("Ro'yxat bo'sh.")
        return
    lines = [f"{p['id']}. {p['title']} — <i>{p.get('category', '?')}</i>" for p in packs]
    await message.answer("\U0001F4CB Pack'lar:\n" + "\n".join(lines) + "\n\nO'chirish: /remove ID")

@dp.message(Command("remove"))
async def cmd_remove(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Foydalanish: /remove ID")
        return
    pack_id = parts[1]
    packs = load_packs()
    new_packs = [p for p in packs if p["id"] != pack_id]
    if len(new_packs) == len(packs):
        await message.answer("Bunday ID yo'q.")
        return
    save_packs(new_packs)
    await message.answer(f"\U0001F5D1 O'chirildi (ID {pack_id}).")

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi! Railway variables'ni tekshiring.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
