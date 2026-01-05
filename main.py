import asyncio
import os
import re
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# --- ВАШИ КЛЮЧИ (НЕ МЕНЯЙТЕ ИХ, ЕСЛИ ОНИ РАБОТАЮТ) ---
API_TOKEN = '8502395795:AAEO--Am5pbn2XL5X0SOV1gEBpzOHOErojk'
OCR_API_KEY = 'K82846104288957'

class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), HealthCheck).serve_forever()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def clean_sts_data(text):
    # Убираем пробелы и переводим в верхний регистр для точного поиска
    clean_text = re.sub(r'\s+', '', text.upper())
    
    # 1. VIN-номер: ищем строго 17 символов (цифры и латынь), 
    # исключая слова вроде 'CERTIFICAT'
    vin_match = re.search(r'[A-HJ-NPR-Z0-9]{17}', clean_text)
    vin = vin_match.group(0) if vin_match else "Не найден"
    
    # 2. Госномер: ищем стандартный российский формат (буква, 3 цифры, 2 буквы, регион)
    plate_match = re.search(r'[АВЕКМНОРСТУХA-Z]\d{3}[АВЕКМНОРСТУХA-Z]{2}\d{2,3}', clean_text)
    plate = plate_match.group(0) if plate else "Не найден"
    
    # 3. Марка и модель: ищем текст после ключевых слов
    model = "Не определена"
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if any(word in line.upper() for word in ["МАРКА", "MODEL"]):
            # Берем строку, где обычно написано название авто
            model = line.replace("Марка, модель", "").replace("Марка", "").strip()
            break
            
    return {"plate": plate, "vin": vin, "model": model}


@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("✅ Бот готов к работе с любыми документами! Присылайте фото СТС.")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    status_msg = await message.answer("⌛ Читаю данные документа...")
    photo = message.photo[-1]
    file_path = f"{photo.file_id}.jpg"
    
    file = await bot.get_file(photo.file_id)
    await bot.download_file(file.file_path, file_path)
    
    try:
        payload = {'apikey': OCR_API_KEY, 'language': 'rus', 'scale': True, 'OCREngine': 2}
        with open(file_path, 'rb') as f:
            r = requests.post('https://api.ocr.space/parse/image', files={'file': f}, data=payload, timeout=60)
        
        raw_text = r.json()['ParsedResults'][0]['ParsedText']
        data = clean_sts_data(raw_text)
        
        res = (f"📋 **Данные распознаны:**\n\n"
               f"🚘 **Авто:** {data['model']}\n"
               f"🔢 **Номер:** {data['plate']}\n"
               f"🆔 **VIN:** `{data['vin']}`")
        await status_msg.edit_text(res, parse_mode="Markdown")
    except:
        await status_msg.edit_text("❌ Ошибка. Убедитесь, что фото четкое.")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

async def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
