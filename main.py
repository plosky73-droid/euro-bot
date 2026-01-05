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
    try:
        with Image.open(input_path) as img:
            img.thumbnail((1500, 1500))
            output_path = "compressed_" + input_path
            img.save(output_path, quality=85)
            return output_path
    except: return input_path

def extract_data(text):
    text_upper = text.upper()
    
    # --- ИСПРАВЛЕНИЕ VIN ---
    # Сначала удаляем само слово VIN и скобки, чтобы они не попали в номер
    # Также убираем слово CERTIFICAT
    text_clean_vin = text_upper.replace('(VIN)', '').replace('VIN', '').replace('CERTIFICAT', '')
    
    # Оставляем только буквы и цифры
    clean_text = re.sub(r'[^A-Z0-9]', '', text_clean_vin)
    
    # Теперь ищем 17 символов. Так как слова VIN уже нет, бот найдет чистый номер
    vin_match = re.search(r'[A-HJ-NPR-Z0-9]{17}', clean_text)
    vin = vin_match.group(0) if vin_match else "Не найден"

    # --- ГОСНОМЕР ---
    clean_text_plate = text_upper.replace(' ', '')
    plate_match = re.search(r'[ABCEHKMOPTXYАВЕКМНОРСТХУ]\d{3}[ABCEHKMOPTXYАВЕКМНОРСТХУ]{2}\d{2,3}', clean_text_plate)
    plate = plate_match.group(0) if plate_match else "Не найден"
    
    # --- МАРКА (SKODA YETI) ---
    model = "Не определена"
    brands = ['SKODA', 'ШКОДА', 'KIA', 'КИА', 'HYUNDAI', 'TOYOTA', 'LADA', 'ВАЗ', 'RENAULT', 'NISSAN', 'BMW', 'MERCEDES', 'VOLKSWAGEN']
    
    for brand in brands:
        if brand in text_upper:
            model = brand
            if brand in ['SKODA', 'ШКОДА'] and ('YETI' in text_upper or 'ЙЕТИ' in text_upper):
                model = "SKODA YETI"
            break
            
    if model == "Не определена":
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if "МАРКА" in line.upper():
                candidate = line.upper().replace("МАРКА", "").replace("МОДЕЛЬ", "").replace(",", "").replace(":", "").strip()
                if len(candidate) > 2:
                    model = candidate
                    break

    return {"plate": plate, "vin": vin, "model": model}

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("✅ Бот обновлен! Пришлите фото СТС.")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    status_msg = await message.answer("🔍 Распознаю данные...")
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
            
            res_text = (f"✅ **Успешно!**\n\n"
                        f"🚘 **Авто:** {data['model']}\n"
                        f"🔢 **Госномер:** {data['plate']}\n"
                        f"🆔 **VIN:** `{data['vin']}`") # Копируемый текст
            await status_msg.edit_text(res_text, parse_mode="Markdown")
        else:
            await status_msg.edit_text("❌ Текст не найден.")
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
