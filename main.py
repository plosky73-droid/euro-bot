import asyncio
import os
import re
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# --- ВАШИ КЛЮЧИ ---
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

def extract_data(text):
    # Убираем лишние пробелы и спецсимволы для надежного поиска
    clean_text = re.sub(r'[^A-Z0-9А-Я]', '', text.upper())
    
    # 1. VIN: Ищем именно 17 знаков (буквы и цифры), исключая заголовок CERTIFICAT
    # VIN в РФ часто начинается на XW8, Z7G, X7L и т.д.
    vins = re.findall(r'[A-Z0-9]{17}', clean_text)
    vin = "Не найден"
    for v in vins:
        if "CERTIFICAT" not in v:
            vin = v
            break
    
    # 2. Госномер: Поддержка РФ формата (Буква, 3 цифры, 2 буквы, регион)
    plate_match = re.search(r'[АВЕКМНОРСТУХA-Z]\d{3}[АВЕКМНОРСТУХA-Z]{2}\d{2,3}', clean_text)
    plate = plate_match.group(0) if plate_match else "Не найден"
    
    # 3. Марка/Модель: Ищем строку, где есть знакомые бренды или слово "Марка"
    model = "Не определена"
    lines = text.split('\n')
    brands = ['SKODA', 'ШКОДА', 'TOYOTA', 'ТОЙОТА', 'VOLKSWAGEN', 'RENAULT', 'ВАЗ', 'LADA', 'HYUNDAI', 'KIA']
    
    for line in lines:
        line_up = line.upper()
        if any(brand in line_up for brand in brands) or "МАРКА" in line_up:
            model = line.replace("Марка, модель", "").replace(":", "").strip()
            break
            
    return {"plate": plate, "vin": vin, "model": model}

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("✅ Бот готов к работе с любыми СТС! Присылайте фото.")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    status_msg = await message.answer("⌛ Анализирую документ...")
    photo = message.photo[-1]
    file_path = f"{photo.file_id}.jpg"
    
    file = await bot.get_file(photo.file_id)
    await bot.download_file(file.file_path, file_path)
    
    try:
        # Используем OCREngine 2 для лучшего распознавания кириллицы
        payload = {'apikey': OCR_API_KEY, 'language': 'rus', 'scale': True, 'OCREngine': 2}
        with open(file_path, 'rb') as f:
            r = requests.post('https://api.ocr.space/parse/image', files={'file': f}, data=payload, timeout=60)
        
        result = r.json()
        if 'ParsedResults' in result:
            raw_text = result['ParsedResults'][0]['ParsedText']
            data = extract_data(raw_text)
            
            res_text = (f"📋 **Результат распознавания:**\n\n"
                        f"🚘 **Авто:** {data['model']}\n"
                        f"🔢 **Госномер:** {data['plate']}\n"
                        f"🆔 **VIN:** `{data['vin']}`")
            await status_msg.edit_text(res_text, parse_mode="Markdown")
        else:
            await status_msg.edit_text("❌ Не удалось прочитать текст. Сделайте фото крупнее.")
    except Exception as e:
        await status_msg.edit_text("❌ Ошибка связи с сервером. Попробуйте еще раз.")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

async def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
