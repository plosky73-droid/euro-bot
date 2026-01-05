import asyncio
import os
import re
import requests
from PIL import Image
from fpdf import FPDF
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# --- НАСТРОЙКИ ---
API_TOKEN = '8502395795:AAEO--Am5pbn2XL5X0SOV1gEBpzOHOErojk'
OCR_API_KEY = 'K82846104288957'

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
user_data = {} # Временное хранилище данных

def extract_data(text):
    text_upper = text.upper()
    
    # 1. ГОСНОМЕР
    plate_match = re.search(r'[ABCEHKMOPTXYАВЕКМНОРСТХУ]\d{3}[ABCEHKMOPTXYАВЕКМНОРСТХУ]{2}\d{2,3}', text_upper.replace(' ', ''))
    plate = plate_match.group(0) if plate_match else "Не найден"

    # 2. VIN (С защитой от заголовков)
    # Удаляем слова-паразиты, которые OCR путает с VIN
    garbage = ["CERTIFICAT", "IMMATRICULATION", "РОССИЙСКАЯ", "ФЕДЕРАЦИЯ", "СВИДЕТЕЛЬСТВО"]
    clean_text = text_upper
    for word in garbage:
        clean_text = clean_text.replace(word, "")
    
    clean_vin_text = re.sub(r'[^A-Z0-9]', '', clean_text)
    
    # Ищем 17 символов. В СТС VIN обычно идет после госномера.
    vin_matches = re.findall(r'[A-Z0-9]{17}', clean_vin_text)
    vin = "Не найден"
    for m in vin_matches:
        if not m.startswith("000"): # Исключаем пустые поля
            vin = m
            break

    # 3. МАРКА
    model = "SKODA YETI" if "YETI" in text_upper else "Легковой автомобиль"
    return {"plate": plate, "vin": vin, "model": model}

def create_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    # Используем стандартный шрифт (для русского языка в идеале нужен .ttf файл, 
    # но для теста используем латиницу или стандарт)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(40, 10, "DOGOVOR KUPLI-PRODAJI (DKP)")
    pdf.ln(20)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Vehicle: {data['model']}", ln=True)
    pdf.cell(200, 10, txt=f"Plate Number: {data['plate']}", ln=True)
    pdf.cell(200, 10, txt=f"VIN: {data['vin']}", ln=True)
    pdf.ln(10)
    pdf.multi_cell(0, 10, txt="Prodavec podtverjdaet peredachu transportnogo sredstva...")
    
    file_path = f"dkp_{data['vin']}.pdf"
    pdf.output(file_path)
    return file_path

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    status_msg = await message.answer("🛠 Обработка документа...")
    photo = message.photo[-1]
    path = f"{photo.file_id}.jpg"
    await bot.download_file((await bot.get_file(photo.file_id)).file_path, path)
    
    try:
        with Image.open(path) as img:
            img.thumbnail((1500, 1500))
            img.save("work.jpg", quality=85)

        r = requests.post('https://api.ocr.space/parse/image', 
                          files={'file': open("work.jpg", 'rb')}, 
                          data={'apikey': OCR_API_KEY, 'language': 'rus', 'OCREngine': 2})
        
        result = r.json()
        raw_text = result['ParsedResults'][0]['ParsedText']
        data = extract_data(raw_text)
        
        # Сохраняем данные пользователя
        user_data[message.from_user.id] = data
        
        res_text = (f"✅ **Данные успешно извлечены!**\n\n"
                    f"🚘 **Авто:** {data['model']}\n"
                    f"🔢 **Госномер:** {data['plate']}\n"
                    f"🆔 **VIN:** `{data['vin']}`")
        
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📄 Скачать ДКП (PDF)", callback_data="get_pdf")]
        ])
        await status_msg.edit_text(res_text, parse_mode="Markdown", reply_markup=kb)
        
    except:
        await status_msg.edit_text("❌ Ошибка. Попробуйте сделать фото крупнее.")
    finally:
        if os.path.exists(path): os.remove(path)

@dp.callback_query(F.data == "get_pdf")
async def send_dkp(callback: types.CallbackQuery):
    data = user_data.get(callback.from_user.id)
    if data:
        pdf_path = create_pdf(data)
        await callback.message.answer_document(types.FSInputFile(pdf_path), caption="Ваш договор готов!")
        os.remove(pdf_path)
    else:
        await callback.answer("Данные не найдены. Загрузите фото снова.")

# Health check для Render
class Health(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")

threading.Thread(target=lambda: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 8080))), Health).serve_forever(), daemon=True).start()

if __name__ == '__main__':
    asyncio.run(dp.start_polling(bot))
