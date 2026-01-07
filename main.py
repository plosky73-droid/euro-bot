import asyncio
import os
import re
import requests
import logging
from PIL import Image
from fpdf import FPDF
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# --- НАСТРОЙКИ ---
API_TOKEN = '8502395795:AAEO--Am5pbn2XL5X0SOV1gEBpzOHOErojk'
OCR_API_KEY = 'K82846104288957'

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- СОСТОЯНИЯ ---
class Form(StatesGroup):
    waiting_for_sts = State()
    waiting_for_vu = State()
    waiting_for_osago = State()

# --- ВСПОМОГАТЕЛЬНЫЕ КЛАВИАТУРЫ ---
def get_manual_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="Ввести вручную ✍️")
    return builder.as_markup(resize_keyboard=True)

# --- ЛОГИКА ИЗВЛЕЧЕНИЯ ДАННЫХ ---
def extract_data(text, doc_type="sts"):
    text_upper = text.upper().replace(' ', '').replace('-', '')
    res = {}

    if doc_type == "sts":
        # Госномер: буква 3 цифры 2 буквы 2-3 цифры
        plate_match = re.search(r'[ABCEHKMOPTXYАВЕКМНОРСТХУ]\d{3}[ABCEHKMOPTXYАВЕКМНОРСТХУ]{2}\d{2,3}', text_upper)
        res['plate'] = plate_match.group(0) if plate_match else "Не найден"
        
        # VIN: 17 символов (исключая технические заголовки)
        clean_vin_text = re.sub(r'[^A-Z0-9]', '', text.upper())
        vin_matches = re.findall(r'[A-Z0-9]{17}', clean_vin_text)
        # Убираем ложные срабатывания (например, если в заголовке СТС нашлось 17 знаков)
        res['vin'] = next((m for m in vin_matches if not m.startswith("000") and "CERTIFICAT" not in m), "Не найден")
        res['model'] = "SKODA YETI" if "YETI" in text.upper() else "Легковой автомобиль"

    elif doc_type == "vu":
        # Ищем 10 цифр подряд
        vu_match = re.search(r'\b\d{10}\b', text_upper)
        res['vu_number'] = vu_match.group(0) if vu_match else None

    elif doc_type == "osago":
        # Серия (3 буквы) + 10 цифр
        osago_match = re.search(r'[А-ЯA-Z]{3}\d{10}', text_upper)
        res['osago'] = osago_match.group(0) if osago_match else None

    return res

# --- ГЕНЕРАЦИЯ PDF ---
def create_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    # Примечание: Для полноценного русского языка в PDF нужно подключать .ttf шрифт
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(40, 10, "EVROPROTOKOL DATA")
    pdf.ln(20)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, txt=f"Vehicle: {data.get('model', '-')}", ln=True)
    pdf.cell(0, 10, txt=f"Plate: {data.get('plate', '-')}", ln=True)
    pdf.cell(0, 10, txt=f"VIN: {data.get('vin', '-')}", ln=True)
    pdf.cell(0, 10, txt=f"Driver License: {data.get('vu_number', '-')}", ln=True)
    pdf.cell(0, 10, txt=f"OSAGO: {data.get('osago', '-')}", ln=True)
    
    file_path = f"doc_{data.get('vin', 'result')}.pdf"
    pdf.output(file_path)
    return file_path

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🚗 **Добро пожаловать!**\n\nЯ помогу собрать данные для Европротокола.\n"
        "Пришлите **фото СТС** (лицевая сторона) или нажмите кнопку для ручного ввода.",
        reply_markup=get_manual_kb(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.waiting_for_sts)

# Обработка СТС (фото или текст)
@dp.message(Form.waiting_for_sts)
async def process_sts(message: types.Message, state: FSMContext):
    if message.text == "Ввести вручную ✍️":
        await message.answer("Введите данные в формате: Марка Модель, Госномер, VIN")
        return

    raw_text = ""
    if message.photo:
        raw_text = await perform_ocr(message)
    else:
        raw_text = message.text

    if raw_text:
        extracted = extract_data(raw_text, "sts")
        await state.update_data(sts_data=extracted)
        await message.answer(
            f"✅ **Данные авто:**\nМарка: {extracted['model']}\nНомер: {extracted['plate']}\nVIN: {extracted['vin']}\n\n"
            "Теперь пришлите **фото ВУ** (права) или введите 10 цифр номера текстом.",
            reply_markup=get_manual_kb(),
            parse_mode="Markdown"
        )
        await state.set_state(Form.waiting_for_vu)

# Обработка ВУ (фото или текст)
@dp.message(Form.waiting_for_vu)
async def process_vu(message: types.Message, state: FSMContext):
    if message.text == "Ввести вручную ✍️":
        await message.answer("Просто отправьте 10 цифр номера вашего ВУ.")
        return

    raw_text = await perform_ocr(message) if message.photo else message.text
    extracted = extract_data(raw_text, "vu")
    
    if extracted.get('vu_number'):
        await state.update_data(vu_number=extracted['vu_number'])
        await message.answer(
            f"✅ **ВУ сохранено:** {extracted['vu_number']}\n\nПришлите **фото полиса ОСАГО** или введите серию и номер (например: XXX 1234567890).",
            reply_markup=get_manual_kb(),
            parse_mode="Markdown"
        )
        await state.set_state(Form.waiting_for_osago)
    else:
        await message.answer("Не удалось найти номер ВУ (10 цифр). Попробуйте еще раз.")

# Обработка ОСАГО (фото или текст)
@dp.message(Form.waiting_for_osago)
async def process_osago(message: types.Message, state: FSMContext):
    if message.text == "Ввести вручную ✍️":
        await message.answer("Введите серию и номер полиса (например: ТТТ 0123456789).")
        return

    raw_text = await perform_ocr(message) if message.photo else message.text
    extracted = extract_data(raw_text, "osago")
    
    if extracted.get('osago'):
        all_data = await state.get_data()
        final_data = {**all_data['sts_data'], 'vu_number': all_data['vu_number'], 'osago': extracted['osago']}
        await state.update_data(final_data=final_data)

        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📄 Сформировать PDF", callback_data="get_pdf")],
            [types.InlineKeyboardButton(text="🔄 Начать заново", callback_data="restart")]
        ])
        await message.answer("✨ Все данные успешно собраны!", reply_markup=kb, reply_markup_remove=True)
    else:
        await message.answer("Полис ОСАГО не распознан. Проверьте формат (Серия + 10 цифр).")

# Функция OCR
async def perform_ocr(message: types.Message):
    status = await message.answer("⌛ Распознаю текст...")
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    path = f"{photo.file_id}.jpg"
    await bot.download_file(file.file_path, path)
    
    try:
        with Image.open(path) as img:
            img.thumbnail((1500, 1500))
            img.save("work.jpg", quality=85)

        with open("work.jpg", 'rb') as f:
            r = requests.post('https://api.ocr.space/parse/image', 
                              files={'file': f}, 
                              data={'apikey': OCR_API_KEY, 'language': 'rus', 'OCREngine': 2})
        
        result = r.json()
        parsed_text = result['ParsedResults'][0]['ParsedText']
        await status.delete()
        return parsed_text
    except Exception as e:
        await status.edit_text("❌ Ошибка распознавания.")
        return None
    finally:
        if os.path.exists(path): os.remove(path)

# Callback: Генерация PDF
@dp.callback_query(F.data == "get_pdf")
async def send_doc(callback: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    data = state_data.get('final_data')
    if data:
        path = create_pdf(data)
        await callback.message.answer_document(types.FSInputFile(path), caption="Ваш документ готов!")
        os.remove(path)
    else:
        await callback.answer("Ошибка: данные не найдены.")

@dp.callback_query(F.data == "restart")
async def restart(callback: types.CallbackQuery, state: FSMContext):
    await cmd_start(callback.message, state)

# Health check
class Health(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")

threading.Thread(target=lambda: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 8080))), Health).serve_forever(), daemon=True).start()

if __name__ == '__main__':
    asyncio.run(dp.start_polling(bot))
