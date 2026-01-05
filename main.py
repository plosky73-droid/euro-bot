import asyncio
import os
import re
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# --- ВСТАВЬТЕ ВАШИ КЛЮЧИ ТУТ ---
API_TOKEN = '8502395795:AAEO--Am5pbn2XL5X0SOV1gEBpzOHOErojk'
OCR_API_KEY = 'K82846104288957'

# Простейший сервер для Render, чтобы он не отключал бота
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), HealthCheck).serve_forever()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def clean_data(text):
    t = text.replace('б', '6').replace('З', '3').replace('о', '0').replace('О', '0')
    plate = re.search(r'[A-ZА-Я]\d{3}[A-ZА-Я]{2}\d{2,3}', t.replace(' ', ''))
    vin = re.search(r'[A-Z0-9]{17}', re.sub(r'[^A-Z0-9]', '', text.upper()))
    model = re.search(r'(ШКОДА|SKODA|YETI|ЙЕТИ|RENAULT|РЕНО)\s*([A-ZА-Я0-9]*)', text, re.IGNORECASE)
    return {"plate": plate.group(0) if plate else "Не найден", 
            "vin": vin.group(0) if vin else "Не найден", 
            "model": model.group(0) if model else "Не найдена"}

def ocr_process(file_path):
    try:
        payload = {'apikey': OCR_API_KEY, 'language': 'rus', 'scale': True, 'OCREngine': 2}
        with open(file_path, 'rb') as f:
            r = requests.post('https://api.ocr.space/parse/image', files={'file': f}, data=payload, timeout=60)
        return r.json()['ParsedResults'][0]['ParsedText']
    except: return "Ошибка чтения"

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("✅ Бот на сервере запущен! Присылайте фото СТС.")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    status = await message.answer("⌛ Обрабатываю фото в облаке...")
    photo = message.photo[-1]
    path = f"{photo.file_id}.jpg"
    await bot.download(photo, destination=path)
    raw_text = await asyncio.to_thread(ocr_process, path)
    if os.path.exists(path): os.remove(path)
    data = clean_data(raw_text)
    await status.edit_text(f"🚘 Авто: {data['model']}\n🔢 Номер: {data['plate']}\n🆔 VIN: {data['vin']}")

async def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
