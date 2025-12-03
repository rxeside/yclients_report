import requests
import pandas as pd
from datetime import datetime
import sys
import os

PARTNER_TOKEN = '4pbzfstkd5chu79nke99'
COMPANY_ID = 1056080
LOGIN = 'reg@rkb12.ru'
PASSWORD = 'X@zu12sho!'


def get_user_token(partner_token, login, password):
    url = 'https://api.yclients.com/api/v1/auth'
    headers = {
        'Accept': 'application/vnd.yclients.v2+json',
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {partner_token}',
    }
    data = {
        'login': login,
        'password': password,
    }

    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        return response.json().get('data', {}).get('user_token')
    except Exception as e:
        print(f"Ошибка авторизации: {e}")
        if 'response' in locals():
            print(f"Ответ сервера: {response.text}")
        return None


def get_daily_records(partner_token, user_token, company_id, date):
    url = f"https://api.yclients.com/api/v1/records/{company_id}"
    params = {
        'start_date': date,
        'end_date': date,
        'count': 200
    }
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


def get_attendance_status(code):
    statuses = {
        1: 'Клиент пришел',
        0: 'Ожидание клиента',
        -1: 'Клиент не пришел',
        2: 'Клиент подтвердил'
    }
    return statuses.get(code, 'Неизвестный статус')


def create_excel(records, date_str):
    data_rows = []

    print(f"Обработка {len(records)} записей...")

    for record in records:
        # Обработка услуг
        services = record.get('services', []) or []
        services_titles = ", ".join([s.get('title', '') for s in services])
        total_cost = sum([s.get('cost', 0) for s in services])

        # Обработка клиента/комментария (Ваша логика)
        client = record.get('client') or {}
        patient_name = client.get('name', 'N/A')
        patient_phone = client.get('phone', 'N/A')
        comment = record.get('comment', '')

        if patient_name == 'N/A' and comment:
            # Простая эмуляция вашей логики парсинга комментария
            import re
            patient_name = comment.strip()
            phone_match = re.search(r'[78]?\d{10}', comment)
            if phone_match:
                patient_phone = phone_match.group(0)
                patient_name = comment.replace(patient_phone, '').strip()

        # Формируем строку для таблицы
        # Парсим дату из строки ISO
        visit_dt = datetime.fromisoformat(record['datetime'])
        visit_time = visit_dt.strftime('%H:%M')

        row = {
            'Время': visit_time,
            'Пациент': patient_name,
            'Телефон': patient_phone,
            'Врач': record.get('staff', {}).get('name', 'N/A'),
            'Специализация': record.get('staff', {}).get('specialization', 'N/A'),
            'Услуга': services_titles,
            'Стоимость': total_cost,
            'Статус визита': get_attendance_status(record.get('attendance')),
            'Комментарий': comment
        }
        data_rows.append(row)

    # Создаем DataFrame (таблицу)
    df = pd.DataFrame(data_rows)

    filename = f"report_{date_str}.xlsx"

    # Сохраняем в Excel
    try:
        # Получаем путь к папке, где лежит запущенный exe файл
        if getattr(sys, 'frozen', False):
            application_path = os.path.dirname(sys.executable)
        else:
            application_path = os.path.dirname(os.path.abspath(__file__))

        full_path = os.path.join(application_path, filename)

        df.to_excel(full_path, index=False)
        print(f"\nГотово! Отчет сохранен в файл:\n{full_path}")
    except Exception as e:
        print(f"Ошибка при сохранении файла: {e}")
        print("Убедитесь, что файл не открыт в Excel!")


def main():
    print("--- ГЕНЕРАТОР ОТЧЕТОВ YCLIENTS ---")

    # Если передали дату при запуске (через консоль), берем её, иначе спрашиваем или берем сегодня
    if len(sys.argv) > 1:
        report_date = sys.argv[1]
    else:
        today = datetime.now().strftime('%Y-%m-%d')
        user_input = input(f"Введите дату отчета (формат YYYY-MM-DD) [Enter для {today}]: ").strip()
        report_date = user_input if user_input else today

    print(f"1. Авторизация ({LOGIN})...")
    token = get_user_token(PARTNER_TOKEN, LOGIN, PASSWORD)

    if token:
        print("   Успешно.")
        print(f"2. Получение записей за {report_date}...")
        records = get_daily_records(PARTNER_TOKEN, token, COMPANY_ID, report_date)

        if records:
            print("   Записи получены.")
            create_excel(records, report_date)
        else:
            print("   Записей не найдено или произошла ошибка.")
    else:
        print("   Не удалось получить токен доступа.")

    input("\nНажмите Enter, чтобы закрыть это окно...")


if __name__ == '__main__':
    main()