import asyncio
import os
import re
import requests
from PIL import Image # Библиотека для обработки изображений
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
    """Сжимаем фото до ширины 1500px, чтобы OCR работал мгновенно"""
    try:
        with Image.open(input_path) as img:
            img.thumbnail((1500, 1500)) # Уменьшаем размер
            output_path = "compressed_" + input_path
            img.save(output_path, quality=85) # Сохраняем с качеством 85%
            return output_path
    except Exception as e:
        print(f"Ошибка сжатия: {e}")
        return input_path # Если ошибка, вернем оригинал

def extract_data(text):
    # Очистка
    clean_text = re.sub(r'[^A-Z0-9А-Я]', '', text.upper())
    
    # 1. VIN: Ищем 17 символов. Исключаем слово CERTIFICAT, которое часто путают с VIN
    # Находим все совпадения по 17 символов
    candidates = re.findall(r'[A-Z0-9]{17}', clean_text)
    vin = "Не найден"
    for c in candidates:
        # VIN не должен содержать много гласных подряд (как в словах) 
        # и обычно содержит цифры. Фильтруем заголовок:
        if "CERTIFICAT" not in c and not c.startswith("REGE0"):
            vin = c
            break
            
    # 2. Госномер
    plate_match = re.search(r'[АВЕКМНОРСТУХA-Z]\d{3}[АВЕКМНОРСТУХA-Z]{2}\d{2,3}', clean_text)
    plate = plate_match.group(0) if plate_match else "Не найден"
    
    # 3. Марка
    model = "Не определена"
    # Простой поиск по строкам
    lines = text.split('\n')
    for line in lines:
        if "SKODA" in line.upper(): model = "SKODA YETI"
        if "KIA" in line.upper(): model = "KIA"
        if "HYUNDAI" in line.upper(): model = "HYUNDAI"
        # Если нашли слово Марка, берем текст рядом
        if "МАРКА" in line.upper():
            temp = line.upper().replace("МАРКА", "").replace("МОДЕЛЬ", "").replace(":", "").replace(",", "").strip()
            if len(temp) > 2: model = temp

    return {"plate": plate, "vin": vin, "model": model}

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("✅ Бот обновлен! Теперь я сжимаю фото для быстрой работы.")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    status_msg = await message.answer("⚙️ Скачиваю и сжимаю фото...")
    
    photo = message.photo[-1]
    original_path = f"{photo.file_id}.jpg"
    
    try:
        # 1. Скачиваем
        file = await bot.get_file(photo.file_id)
        await bot.download_file(file.file_path, original_path)
        
        # 2. Сжимаем
        work_path = compress_image(original_path)
        
        # 3. Отправляем в OCR
        await status_msg.edit_text("📡 Отправляю на сервер распознавания...")
        payload = {'apikey': OCR_API_KEY, 'language': 'rus', 'scale': True, 'OCREngine': 2}
        
        with open(work_path, 'rb') as f:
            # Таймаут 30 сек, так как фото теперь легкое
            r = requests.post('https://api.ocr.space/parse/image', files={'file': f}, data=payload, timeout=30)
        
        result = r.json()
        
        # 4. Проверяем ошибки API
        if result.get('IsErroredOnProcessing'):
            err_msg = result.get('ErrorMessage')
            await status_msg.edit_text(f"⚠️ Ошибка API OCR: {err_msg}")
            return

        if 'ParsedResults' in result and result['ParsedResults']:
            raw_text = result['ParsedResults'][0]['ParsedText']
            data = extract_data(raw_text)
            
            res_text = (f"📋 **Результат:**\n\n"
                        f"🚘 **Авто:** {data['model']}\n"
                        f"🔢 **Госномер:** {data['plate']}\n"
                        f"🆔 **VIN:** `{data['vin']}`")
            await status_msg.edit_text(res_text, parse_mode="Markdown")
        else:
            await status_msg.edit_text("❌ Текст не найден. Попробуйте другое фото.")

    except Exception as e:
        # Теперь мы увидим реальную ошибку!
        await status_msg.edit_text(f"❌ Критическая ошибка: {e}")
        
    finally:
        # Уборка мусора
        if os.path.exists(original_path): os.remove(original_path)
        if os.path.exists(work_path) and work_path != original_path: os.remove(work_path)

async def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
