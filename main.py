import asyncio
import os
import re
import requests
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# --- ВАШИ КЛЮЧИ ---
API_TOKEN = '8502395795:AAEO--Am5pbn2XL5X0SOV1gEBpzOHOErojk'
OCR_API_KEY = 'K82846104288957'

# Сервер для Render
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), HealthCheck).serve_forever()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def compress_image(input_path):
    """Сжимаем фото для ускорения работы"""
    try:
        with Image.open(input_path) as img:
            img.thumbnail((1500, 1500))
            output_path = "compressed_" + input_path
            img.save(output_path, quality=85)
            return output_path
    except: return input_path

def extract_data(text):
    text_upper = text.upper()
    
    # 1. ЧИСТКА для поиска VIN
    # Убираем слово VIN и CERTIFICAT, чтобы они не прилипали к номеру
    clean_text_for_vin = re.sub(r'[^A-Z0-9]', '', text_upper).replace('VIN', '').replace('CERTIFICAT', '')
    
    # Ищем 17 символов подряд (обычно VIN начинается не с 0)
    vin_match = re.search(r'[A-HJ-NPR-Z0-9]{17}', clean_text_for_vin)
    vin = vin_match.group(0) if vin_match else "Не найден"

    # 2. ГОСНОМЕР
    # Убираем пробелы, чтобы найти "E 056 HY 73" как "E056HY73"
    clean_text_plate = text_upper.replace(' ', '')
    plate_match = re.search(r'[ABCEHKMOPTXYАВЕКМНОРСТХУ]\d{3}[ABCEHKMOPTXYАВЕКМНОРСТХУ]{2}\d{2,3}', clean_text_plate)
    plate = plate_match.group(0) if plate_match else "Не найден"
    
    # 3. МАРКА АВТО (Умный поиск)
    model = "Не определена"
    # Список частых брендов (дополните при желании)
    brands = ['SKODA', 'ШКОДА', 'KIA', 'КИА', 'HYUNDAI', 'ХЕНДАЙ', 'TOYOTA', 'VOLKSWAGEN', 'LADA', 'ВАЗ', 'RENAULT', 'NISSAN', 'BMW', 'MERCEDES']
    
    # Сначала ищем знакомые слова
    for brand in brands:
        if brand in text_upper:
            model = brand # Нашли бренд!
            # Проверяем модели рядом
            if brand in ['SKODA', 'ШКОДА'] and ('YETI' in text_upper or 'ЙЕТИ' in text_upper):
                model = "SKODA YETI"
            break
            
    # Если бренд не нашли, пробуем вытащить из строки "Марка, модель"
    if model == "Не определена":
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if "МАРКА" in line.upper():
                candidate = line.upper().replace("МАРКА", "").replace("МОДЕЛЬ", "").replace(",", "").replace(":", "").strip()
                if len(candidate) > 2:
                    model = candidate
                    break
                elif i+1 < len(lines): # Смотрим следующую строку
                    model = lines[i+1].strip()
                    break

    return {"plate": plate, "vin": vin, "model": model}

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("🚙 Бот готов! Пришлите фото СТС.")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    status_msg = await message.answer("⚙️ Обрабатываю фото...")
    photo = message.photo[-1]
    original_path = f"{photo.file_id}.jpg"
    
    try:
        file = await bot.get_file(photo.file_id)
        await bot.download_file(file.file_path, original_path)
        work_path = compress_image(original_path)
        
        payload = {'apikey': OCR_API_KEY, 'language': 'rus', 'scale': True, 'OCREngine': 2}
        with open(work_path, 'rb') as f:
            r = requests.post('https://api.ocr.space/parse/image', files={'file': f}, data=payload, timeout=30)
        
        result = r.json()
        if result.get('ParsedResults'):
            raw_text = result['ParsedResults'][0]['ParsedText']
            data = extract_data(raw_text)
            
            res_text = (f"✅ **Данные из СТС:**\n\n"
                        f"🚘 **Авто:** {data['model']}\n"
                        f"🔢 **Госномер:** {data['plate']}\n"
                        f"🆔 **VIN:** `{data['vin']}`")
            await status_msg.edit_text(res_text, parse_mode="Markdown")
        else:
            await status_msg.edit_text("❌ Не удалось прочитать текст.")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")
    finally:
        if os.path.exists(original_path): os.remove(original_path)
        if os.path.exists("compressed_" + original_path): os.remove("compressed_" + original_path)

async def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
