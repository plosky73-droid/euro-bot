import asyncio
import os
import re
import requests
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = '8502395795:AAEO--Am5pbn2XL5X0SOV1gEBpzOHOErojk'
OCR_API_KEY = 'K82846104288957'

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def extract_data(text):
    text_upper = text.upper()
    
    # 1. ГОСНОМЕР (Ищем формат: буква, 3 цифры, 2 буквы, регион)
    plate_match = re.search(r'[ABCEHKMOPTXYАВЕКМНОРСТХУ]\d{3}[ABCEHKMOPTXYАВЕКМНОРСТХУ]{2}\d{2,3}', text_upper.replace(' ', ''))
    plate = plate_match.group(0) if plate_match else "Не найден"

    # 2. VIN (Улучшенный поиск)
    # Удаляем госномер из строки поиска, чтобы он не мешался
    text_for_vin = text_upper.replace(plate, '')
    # Убираем все лишнее, кроме латиницы и цифр
    clean_vin_text = re.sub(r'[^A-Z0-9]', '', text_for_vin)
    
    # Ищем 17 символов, которые начинаются на типичные для РФ иномарок буквы (X, Z, W, S, T)
    # или просто любую комбинацию из 17 знаков, которая НЕ включает в себя мусор
    vin_match = re.search(r'[XWZTYSJ][A-Z0-9]{16}', clean_vin_text)
    
    if not vin_match:
        # Запасной вариант: ищем любые 17 символов
        vin_match = re.search(r'[A-Z0-9]{17}', clean_vin_text)
        
    vin = vin_match.group(0) if vin_match else "Не найден"
    
    # 3. МАРКА
    model = "SKODA YETI" if "YETI" in text_upper or "ЙЕТИ" in text_upper else "Не определена"
    if model == "Не определена":
        for brand in ['KIA', 'HYUNDAI', 'TOYOTA', 'LADA', 'RENAULT']:
            if brand in text_upper:
                model = brand
                break

    return {"plate": plate, "vin": vin, "model": model}

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    status_msg = await message.answer("🔍 Фильтруем данные...")
    photo = message.photo[-1]
    path = f"{photo.file_id}.jpg"
    
    await bot.download_file((await bot.get_file(photo.file_id)).file_path, path)
    
    try:
        # Сжатие для ускорения
        with Image.open(path) as img:
            img.thumbnail((1500, 1500))
            img.save("work.jpg", quality=85)

        r = requests.post('https://api.ocr.space/parse/image', 
                          files={'file': open("work.jpg", 'rb')}, 
                          data={'apikey': OCR_API_KEY, 'language': 'rus', 'OCREngine': 2})
        
        raw_text = r.json()['ParsedResults'][0]['ParsedText']
        data = extract_data(raw_text)
        
        res_text = (f"✅ **Данные проверены:**\n\n"
                    f"🚘 **Авто:** {data['model']}\n"
                    f"🔢 **Госномер:** {data['plate']}\n"
                    f"🆔 **VIN:** `{data['vin']}`")
        
        # Добавляем кнопку для будущего PDF (пока просто макет)
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📄 Сформировать ДКП (PDF)", callback_data="make_pdf")]
        ])
        
        await status_msg.edit_text(res_text, parse_mode="Markdown", reply_markup=kb)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка распознавания. Попробуйте еще раз.")
    finally:
        if os.path.exists(path): os.remove(path)
        if os.path.exists("work.jpg"): os.remove("work.jpg")

# Запуск сервера здоровья для Render
class Health(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")

threading.Thread(target=lambda: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 8080))), Health).serve_forever(), daemon=True).start()

if __name__ == '__main__':
    asyncio.run(dp.start_polling(bot))
