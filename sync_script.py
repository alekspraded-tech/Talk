import os
import requests
from datetime import datetime, timedelta
from supabase import create_client, Client

# --- НАСТРОЙКИ КОНТУР.ТОЛК ---
TALK_API_URL = "https://portalwash.ktalk.ru/api/Domain/recordings/v2"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

MANAGERS = {
    "45cd0d96-9fb7-40db-88bf-e1350dc28fe1": {"name": "Алексей Беликов", "email": "a.belikov@portalwash.ru"},
    "3ae59251-f4b6-4b38-9cda-ef6a56cc7127": {"name": "Евгений Журавлев", "email": "e.zhuravlev@portalwash.ru"},
    "01c7dc8e-b715-470e-9766-43c8363a2760": {"name": "Николай Киселев", "email": "n.kiselyov@portalwash.ru"}
}

# --- НАСТРОЙКИ SUPABASE ---
SUPABASE_URL = "https://jqtznmrwxswbveugfsbv.supabase.co" 
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_KEY:
    print("🛑 Ошибка: Ключ SUPABASE_SERVICE_KEY не найден в GitHub Secrets!")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ОСНОВНОЙ СКРИПТ ВЫГРУЗКИ ---
print("🤖 Запуск СВЕРХБЫСТРОЙ синхронизации звонков...")

date_limit = datetime.utcnow() - timedelta(days=7)
print(f"📅 Ищем новые звонки с: {date_limit.strftime('%Y-%m-%d %H:%M:%S')} UTC")

# Шаг 0. Получаем ID встреч из Supabase
existing_ids = set()
try:
    existing_data = supabase.table("talk_records").select("id").execute()
    if existing_data.data:
        existing_ids = {str(row["id"]) for row in existing_data.data}
    print(f"📦 В базе Supabase уже есть: {len(existing_ids)} шт. (будут пропущены)")
except Exception as db_err:
    print(f"⚠️ База пуста или недоступна: {db_err}")

headers = {
    "X-Auth-Token": TALK_API_KEY,
    "Accept": "application/json"
}

collected_records = []
page = 1
page_size = 50  # Увеличиваем размер страницы, чтобы забирать больше данных за один запрос
max_pages = 5   # Жёсткий ограничитель, чтобы скрипт не зависал в бесконечных циклах

try:
    while page <= max_pages:
        print(f"📦 Запрос страницы {page} из {max_pages}...")
        
        # ВАЖНО: Добавляем параметр сортировки по убыванию (desc), чтобы первыми шли новые записи
        params = {
            "page": page, 
            "size": page_size,
            "sort": "createdDate,desc"  
        }
        
        response = requests.get(TALK_API_URL, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"🛑 Ошибка Толка: Код {response.status_code}")
            break

        data = response.json()
        records = data.get("entities", [])
        
        if not records:
            print("-> Записи на странице отсутствуют.")
            break
            
        print(f"-> Проверяем {len(records)} свежих строк...")
        reached_end_of_period = False
        
        for record in records:
            if not isinstance(record, dict):
                continue
                
            # 1. Фильтр по менеджеру
            created_by = record.get("createdBy", {}) or {}
            user_id = created_by.get("login")
            if user_id not in MANAGERS:
                continue
                
            # 2. Проверка на дубликаты
            record_id = str(record.get("id"))
            if record_id in existing_ids:
                continue
                
            # 3. Проверка даты
            created_date_str = record.get("createdDate")
            if not created_date_str:
                continue
                
            clean_date_str = created_date_str.replace("Z", "").split(".")[0]
            try:
                record_date = datetime.strptime(clean_date_str, "%Y-%m-%dT%H:%M:%S")
            except:
                continue
                
            # Так как мы добавили desc-сортировку, если мы дошли до старой записи, 
            # значит все последующие тоже будут старыми.
            if record_date < date_limit:
                reached_end_of_period = True
                break
                
            # 4. Сбор данных
            view_url = f"https://portalwash.ktalk.ru/recordings/{record_id}"
            manager_info = MANAGERS[user_id]
            
            collected_records.append({
                "id": record_id,
                "name": record.get("title") or "Встреча без названия",
                "created_at": created_date_str,
                "manager_email": manager_info["email"],
                "manager_name": manager_info["name"],
                "view_url": view_url
            })

        if reached_end_of_period:
            print(f"⏳ Обнаружены записи старше 7 дней. Поиск успешно завершен.")
            break
            
        page += 1
        
    if page > max_pages:
        print(f"🛑 Достигнут лимит страниц ({max_pages}). Защита от зависания сработала.")

    # --- ОТПРАВКА ---
    if not collected_records:
        print("\nℹ️ Абсолютно новых встреч у менеджеров за 7 дней не найдено.")
    else:
        unique_payload = {item["id"]: item for item in collected_records}.values()
        unique_payload = list(unique_payload)
        
        print(f"\n📋 НАЙДЕНЫ НОВЫЕ ВСТРЕЧИ ({len(unique_payload)} шт.):")
        print("-" * 60)
        for idx, item in enumerate(unique_payload, 1):
            print(f"{idx}. [{item['manager_name']}] {item['name']} ({item['created_at']})")
        print("-" * 60)
        
        print("🚀 Отправка в Supabase...")
        final_payload = [{k: v for k, v in item.items() if k != 'manager_name'} for item in unique_payload]
        supabase.table("talk_records").insert(final_payload).execute()
        print("✅ База данных успешно обновлена!")
        
except Exception as e:
    print(f"🛑 Системная ошибка: {e}")
