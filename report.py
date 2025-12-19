import requests
import pandas as pd
from datetime import datetime
import sys
import os
import re
from concurrent.futures import ThreadPoolExecutor  # Библиотека для ускорения (потоки)

# --- НАСТРОЙКИ ---
PARTNER_TOKEN = '4pbzfstkd5chu79nke99'
COMPANY_ID = 1056080
LOGIN = 'reg@rkb12.ru'
PASSWORD = 'X@zu12sho!'

# Словари для русской даты
RU_MONTHS = {
    1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля', 5: 'мая', 6: 'июня',
    7: 'июля', 8: 'августа', 9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
}
RU_DAYS = {
    0: 'Понедельник', 1: 'Вторник', 2: 'Среда', 3: 'Четверг',
    4: 'Пятница', 5: 'Суббота', 6: 'Воскресенье'
}


def get_user_token(partner_token, login, password):
    url = 'https://api.yclients.com/api/v1/auth'
    headers = {
        'Accept': 'application/vnd.yclients.v2+json',
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {partner_token}',
    }
    data = {'login': login, 'password': password}

    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        return response.json().get('data', {}).get('user_token')
    except Exception as e:
        print(f"Ошибка авторизации: {e}")
        return None


def get_daily_records(partner_token, user_token, company_id, date):
    url = f"https://api.yclients.com/api/v1/records/{company_id}"
    params = {'start_date': date, 'end_date': date, 'count': 1000}
    headers = {
        'Accept': 'application/vnd.yclients.v2+json',
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {partner_token}, User {user_token}',
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get('data', [])
    except Exception as e:
        print(f"Ошибка получения записей: {e}")
        return None


def get_full_client_info(partner_token, user_token, company_id, client_id):
    """
    Получает полную карточку одного клиента.
    """
    url = f"https://api.yclients.com/api/v1/client/{company_id}/{client_id}"
    headers = {
        'Accept': 'application/vnd.yclients.v2+json',
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {partner_token}, User {user_token}',
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)  # Добавил таймаут
        if response.status_code == 200:
            return client_id, response.json().get('data', {})
        return client_id, {}
    except:
        return client_id, {}


def format_russian_date(date_str):
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    day_name = RU_DAYS[dt.weekday()]
    month_name = RU_MONTHS[dt.month]
    return f"{day_name} {dt.day} {month_name}"


def create_excel_visual(records, date_str, partner_token, user_token, company_id):
    """Создает красивый Excel отчет, сгруппированный по врачам"""
    print(f"Обработка {len(records)} записей...")

    # Кэш для клиентов
    clients_cache = {}

    # Регулярка для даты
    date_pattern = r'\d{2}[./]\d{2}[./]\d{2,4}'

    # --- ЭТАП 1: ОПРЕДЕЛЯЕМ, КОГО НУЖНО ДОГРУЗИТЬ ---
    ids_to_load = set()

    print("Анализ недостающих данных...")
    for record in records:
        record_comment = record.get('comment', '')
        client = record.get('client') or {}
        client_note = client.get('comment', '')
        client_id = client.get('id')

        # Если даты нет ни в комментарии к записи, ни в кратком комментарии клиента
        if not re.search(date_pattern, record_comment) and \
                not re.search(date_pattern, client_note):
            if client_id:
                ids_to_load.add(client_id)

    # --- ЭТАП 2: БЫСТРАЯ ПАРАЛЛЕЛЬНАЯ ЗАГРУЗКА ---
    if ids_to_load:
        print(f"Загрузка полных карточек для {len(ids_to_load)} клиентов...")

        # Используем 5 потоков, чтобы уложиться в лимиты API YClients (5 запросов в секунду)
        with ThreadPoolExecutor(max_workers=5) as executor:
            # Запускаем задачи параллельно
            futures = [
                executor.submit(get_full_client_info, partner_token, user_token, company_id, cid)
                for cid in ids_to_load
            ]

            # Собираем результаты по мере выполнения
            for future in futures:
                cid, data = future.result()
                if data:
                    clients_cache[cid] = data
        print("Данные загружены.")

    # --- ЭТАП 3: ФОРМИРОВАНИЕ ТАБЛИЦЫ ---
    doctors_data = {}

    for record in records:
        staff = record.get('staff') or {}
        staff_name = staff.get('name', 'Неизвестный врач')
        staff_spec = staff.get('specialization') or 'Специалист'

        staff_spec = staff_spec.replace('Врач-', '').replace('врач-', '').strip()
        if staff_spec:
            staff_spec = staff_spec[0].upper() + staff_spec[1:]

        staff_id = staff.get('id', 0)

        if staff_id not in doctors_data:
            doctors_data[staff_id] = {
                'name': staff_name,
                'spec': staff_spec,
                'records': []
            }

        # Парсим время визита
        visit_dt = datetime.fromisoformat(record['datetime'])

        # Первая колонка пустая
        mark = " "

        # Данные пациента
        client = record.get('client') or {}
        client_id = client.get('id')
        patient_name = client.get('name', '')

        # --- Логика поиска Даты Рождения ---
        info_col = ""

        record_comment = record.get('comment', '')
        dob_match = re.search(date_pattern, record_comment)

        if not dob_match:
            # Сначала ищем в тех данных, что пришли сразу
            client_note = client.get('comment', '')
            dob_match = re.search(date_pattern, client_note)

            # Если не нашли, смотрим в кэше (который мы уже заполнили на Этапе 2)
            if not dob_match and client_id and client_id in clients_cache:
                full_note = clients_cache[client_id].get('comment', '')
                dob_match = re.search(date_pattern, full_note)

        if dob_match:
            info_col = dob_match.group(0).replace('/', '.')

        doctors_data[staff_id]['records'].append({
            'time': visit_dt,
            'time_str': visit_dt.strftime('%H:%M'),
            'patient': patient_name,
            'info': info_col,
            'mark': mark
        })

    filename = f"raspisanie_{date_str}.xlsx"
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(application_path, filename)

    writer = pd.ExcelWriter(full_path, engine='xlsxwriter')
    workbook = writer.book
    worksheet = workbook.add_worksheet('Расписание')

    # --- СТИЛИ ---
    fmt_main_header = workbook.add_format({
        'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter',
        'bottom': 1
    })
    fmt_doc_header = workbook.add_format({
        'bold': True, 'bg_color': '#E0E0E0', 'border': 1, 'align': 'left'
    })
    fmt_cell = workbook.add_format({'border': 1, 'align': 'left', 'font_size': 11})
    fmt_time = workbook.add_format({'border': 1, 'align': 'center', 'font_size': 11})
    fmt_mark = workbook.add_format({'border': 1, 'align': 'center', 'bold': True})

    worksheet.set_column('A:A', 3)
    worksheet.set_column('B:B', 8)
    worksheet.set_column('C:C', 35)
    worksheet.set_column('D:D', 18)

    # --- ЗАПИСЬ ДАННЫХ ---
    current_row = 0

    # Заголовок даты
    rus_date = format_russian_date(date_str)
    worksheet.merge_range(current_row, 0, current_row, 3, rus_date, fmt_main_header)
    current_row += 2

    # Сортируем врачей
    sorted_staff_ids = sorted(doctors_data.keys(), key=lambda k: doctors_data[k]['spec'])

    for staff_id in sorted_staff_ids:
        doc = doctors_data[staff_id]

        # Заголовок врача (только имя)
        header_text = doc['name']
        worksheet.merge_range(current_row, 0, current_row, 3, header_text, fmt_doc_header)
        current_row += 1

        # Сортируем записи по времени
        doc['records'].sort(key=lambda x: x['time'])

        for rec in doc['records']:
            worksheet.write(current_row, 0, rec['mark'], fmt_mark)
            worksheet.write(current_row, 1, rec['time_str'], fmt_time)
            worksheet.write(current_row, 2, rec['patient'], fmt_cell)
            worksheet.write(current_row, 3, rec['info'], fmt_cell)
            current_row += 1

        # Пустая строка после каждого врача
        current_row += 1

    # Настройки печати
    worksheet.set_portrait()
    worksheet.fit_to_pages(1, 0)

    writer.close()
    print(f"\nГотово! Файл сохранен: {full_path}")


def main():
    print("--- ГЕНЕРАТОР РАСПИСАНИЯ ---")

    if len(sys.argv) > 1:
        report_date = sys.argv[1]
    else:
        today = datetime.now().strftime('%Y-%m-%d')
        user_input = input(f"Введите дату (YYYY-MM-DD) [Enter для {today}]: ").strip()
        report_date = user_input if user_input else today

    print(f"Авторизация...")
    token = get_user_token(PARTNER_TOKEN, LOGIN, PASSWORD)

    if token:
        print(f"Запрос данных за {report_date}...")
        records = get_daily_records(PARTNER_TOKEN, token, COMPANY_ID, report_date)

        if records:
            create_excel_visual(records, report_date, PARTNER_TOKEN, token, COMPANY_ID)
        else:
            print("Записей не найдено.")
    else:
        print("Ошибка авторизации.")

    input("\nНажмите Enter для выхода...")


if __name__ == '__main__':
    main()