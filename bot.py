import discord
from discord.ext import commands
import re
import datetime
import asyncio
from collections import defaultdict, Counter
import requests
import os
from io import BytesIO
from PIL import Image, ImageSequence
import pytesseract

# === Вказуємо правильний шлях до Tesseract ===
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\user\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

# Токен твого бота
TOKEN = "MTQxNDg5MjQ3NjU4NTQ4MDI3Nw.GZwaiM.XY0hubTfvb15U7O_Ejxt0Aon0owC9d7pm7I9LA"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# === Локальний файл зі словами ===
LOCAL_SWEAR_FILE = "downloaded_swears.txt"

def load_local_swears():
    if os.path.exists(LOCAL_SWEAR_FILE):
        with open(LOCAL_SWEAR_FILE, "r", encoding="utf-8") as f:
            words = [line.strip().lower() for line in f if line.strip()]
        print(f"[LOCAL] Завантажено {len(words)} слів із {LOCAL_SWEAR_FILE}")
        return set(words)
    print("[LOCAL] Локального файлу не знайдено — буде завантажено з інтернету.")
    return set()

def save_local_swears(words):
    with open(LOCAL_SWEAR_FILE, "w", encoding="utf-8") as f:
        for w in sorted(words):
            f.write(w + "\n")
    print(f"[SAVE] Збережено {len(words)} слів у {LOCAL_SWEAR_FILE}")

def load_swear_words_from_web(url):
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200 and response.text.strip():
            words = [line.strip().lower() for line in response.text.splitlines() if line.strip()]
            return words
        else:
            print(f"[WARN] {url} — статус {response.status_code} або порожній вміст.")
    except Exception as e:
        print(f"[ERROR] Помилка при завантаженні з {url}: {e}")
    return []

english_urls = [
    "https://raw.githubusercontent.com/coffee-and-fun/google-profanity-words/main/data/en.txt",
    "https://www.cs.cmu.edu/~biglou/resources/bad-words.txt",
    "https://raw.githubusercontent.com/zautumnz/profane-words/master/words.txt",
    "https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/english.txt"
]

russian_urls = [
    "https://raw.githubusercontent.com/denexapp/russian-bad-words/master/words.txt",
    "https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/russian.txt",
    "https://raw.githubusercontent.com/kaeyzar/russian-swear-words/master/words.txt",
    "https://raw.githubusercontent.com/ishandutta/udpipe-models/master/russian-swear-words.txt",
    "https://raw.githubusercontent.com/adzr/russian-bad-words/master/russian.txt"
]

ukrainian_urls = [
    "https://raw.githubusercontent.com/saganoren/obscene-ukr/master/obscene-ukr.txt",
    "https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/ukrainian.txt",
    "https://raw.githubusercontent.com/ukrainian-swears/ukr-words/master/words.txt"
]

def load_all_swears():
    local_words = load_local_swears()
    if local_words:
        return local_words

    print("[INFO] Завантаження онлайн словників...")
    english_set, russian_set, ukrainian_set = set(), set(), set()
    for url in english_urls:
        english_set.update(load_swear_words_from_web(url))
    for url in russian_urls:
        russian_set.update(load_swear_words_from_web(url))
    for url in ukrainian_urls:
        ukrainian_set.update(load_swear_words_from_web(url))

    all_words = english_set | russian_set | ukrainian_set
    print(f"[INFO] Завантажено {len(all_words)} унікальних слів з інтернету.")
    save_local_swears(all_words)
    return all_words

all_swear_words = load_all_swears()

warnings = {}
recent_messages = defaultdict(list)
mem_channel = "мемчики"

async def handle_violation(member, violation_type, reason, channel=None):
    if member.id not in warnings:
        warnings[member.id] = {"offense": 0, "spam": 0, "cringe": 0}
    warnings[member.id][violation_type] += 1
    count = warnings[member.id][violation_type]

    if count <= 3:
        warning_text = f"⚠️ Попередження {count}/3 за: {reason}"
        try:
            if channel:
                msg = await channel.send(f"{member.mention}, {warning_text}")
            else:
                msg = await member.send(warning_text)
            await asyncio.sleep(10)
            await msg.delete()
        except:
            print(f"[WARN] Не вдалося надіслати попередження {member}")
    else:
        duration = 600 if count == 4 else 1800
        until_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=duration)
        try:
            await member.edit(timed_out_until=until_time, reason=reason)
            await member.send(f"Вам дано тайм-аут {duration} секунд за: {reason}")
        except Exception as e:
            print(f"[ERROR] Не вдалося дати тайм-аут {member}: {e}")

@bot.event
async def on_ready():
    print(f"✅ Бот {bot.user} запущений!")
    print(f"✅ Завантажено {len(all_swear_words)} унікальних слів.")

# === OCR для зображень і GIF ===
async def check_image_for_swears(message):
    for attachment in message.attachments:
        if attachment.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            try:
                img_bytes = await attachment.read()
                img = Image.open(BytesIO(img_bytes))
                extracted_text = ""

                if attachment.filename.lower().endswith(".gif"):
                    for frame in ImageSequence.Iterator(img):
                        frame = frame.convert("RGB")
                        extracted_text += pytesseract.image_to_string(frame, lang="ukr+rus+eng").lower() + " "
                else:
                    extracted_text = pytesseract.image_to_string(img, lang="ukr+rus+eng").lower()

                if any(word in extracted_text for word in all_swear_words):
                    try:
                        await message.delete()
                    except:
                        print(f"[WARN] Не вдалося видалити зображення від {message.author}")
                    await handle_violation(message.author, "offense", "Матюки на зображенні", channel=message.channel)
                    return True
            except Exception as e:
                print(f"[ERROR] OCR не вдалося виконати для {attachment.filename}: {e}")
    return False

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    author = message.author
    channel_name = message.channel.name.lower()

    if message.attachments:
        if await check_image_for_swears(message):
            return
        await bot.process_commands(message)
        return

    if message.content:
        words_in_message = re.findall(r"[a-zA-Zа-яА-Яґєії'-]+", message.content.lower())
        if any(word in all_swear_words for word in words_in_message):
            try:
                await message.delete()
            except:
                print(f"[WARN] Не вдалося видалити повідомлення від {author}")
            await handle_violation(author, "offense", "Оскорбления", channel=message.channel)
            return

        recent_messages[author.id].append(message.content.lower())
        if Counter(recent_messages[author.id])[message.content.lower()] >= 10:
            try:
                await message.delete()
            except:
                print(f"[WARN] Не вдалося видалити спам від {author}")
            await handle_violation(author, "spam", "Спам", channel=message.channel)
            recent_messages[author.id].clear()
            return

        if len(recent_messages[author.id]) > 20:
            recent_messages[author.id] = recent_messages[author.id][-20:]

        if "мем" in message.content.lower() and channel_name != mem_channel.lower():
            try:
                await message.delete()
            except:
                print(f"[WARN] Не вдалося видалити мем-повідомлення від {author}")
            await handle_violation(author, "cringe", "Засорение чата", channel=message.channel)
            return

    await bot.process_commands(message)

# === Команди ===
@bot.command()
async def привіт(ctx):
    await ctx.send("Привіт! Я Discord бот 😊")

@bot.command()
async def бот(ctx):
    await ctx.send("так що?")

@bot.command()
@commands.has_permissions(administrator=True)
async def clear(ctx, amount: int):
    await ctx.channel.purge(limit=amount)
    await ctx.send(f"Видалено {amount} повідомлень", delete_after=5)

@bot.command()
@commands.has_permissions(administrator=True)
async def вимкнути(ctx):
    await ctx.send("Бот вимикається...")
    await bot.close()

@bot.command()
@commands.has_permissions(administrator=True)
async def обнови_списки(ctx):
    await ctx.send("🔄 Оновлюю словники...")
    global all_swear_words
    all_swear_words = load_all_swears()
    await ctx.send(f"✅ Готово! Завантажено {len(all_swear_words)} унікальних слів.")

# === Запуск ===
bot.run(TOKEN)
