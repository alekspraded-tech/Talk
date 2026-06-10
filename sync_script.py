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

print("🤖 Запуск умной синхронизации (разделение встреч в одинаковых комнатах)...")

date_limit = datetime.utcnow() - timedelta(days=7)
print(f"📅 Ищем новые звонки с: {date_limit.strftime('%Y-%m-%d %H:%M:%S')} UTC")

# Шаг 0. Получаем существующие ID из Supabase
existing_ids = set()
try:
    existing_data = supabase.table("talk_records").select("id").execute()
    if existing_data.data:
        existing_ids = {str(row["id"]) for row in existing_data.data}
    print(f"📦 В базе Supabase уже сохранено: {len(existing_ids)} шт.")
except Exception as db_err:
    print(f"⚠️ База пуста или недоступна: {db_err}")

headers = {
    "X-Auth-Token": TALK_API_KEY,
    "Accept": "application/json"
}

collected_records = []
page = 1
page_size = 50  
max_pages = 4   

try:
    while page <= max_pages:
        print(f"📦 Сканируем страницу {page}...")
        response = requests.get(TALK_API_URL, headers=headers, params={"page": page, "size": page_size})
        
        if response.status_code != 200:
            print(f"🛑 Ошибка Толка: Код {response.status_code}")
            break

        data = response.json()
        records = data.get("entities", [])
        
        if not records:
            break
            
        for record in records:
            if not isinstance(record, dict):
                continue
                
            # 1. Фильтр по менеджеру
            created_by = record.get("createdBy", {}) or {}
            user_id = created_by.get("login")
            if user_id not in MANAGERS:
                continue
                
            # 2. Проверка даты (в пределах 7 дней)
            created_date_str = record.get("createdDate")
            if not created_date_str:
                continue
                
            clean_date_str = created_date_str.replace("Z", "").split(".")[0]
            try:
                record_date = datetime.strptime(clean_date_str, "%Y-%m-%dT%H:%M:%S")
            except:
                continue
                
            if record_date < date_limit:
                continue
                
            # 3. ГЕНЕРИРУЕМ АБСОЛЮТНО УНИКАЛЬНЫЙ ID ДЛЯ НАШЕЙ БАЗЫ
            # Вместо сырого id из Толка делаем связку с датой, чтобы разные встречи в одной комнате не затирали друг друга
            raw_id = str(record.get("id"))
            timestamp_suffix = clean_date_str.replace("-", "").replace(":", "").replace("T", "_")
            unique_db_id = f"{raw_id}_{timestamp_suffix}"
            
            # Проверяем, отправляли ли мы конкретно ЭТУ сессию созвона ранее
            if unique_db_id in existing_ids:
                continue
                
            # 4. Сбор данных
            view_url = f"https://portalwash.ktalk.ru/recordings/{raw_id}"
            manager_info = MANAGERS[user_id]
            title = record.get("title") or "Встреча без названия"
            
            collected_records.append({
                "id": unique_db_id, # Новый составной ключ
                "name": title,
                "created_at": created_date_str,
                "manager_email": manager_info["email"],
                "manager_name": manager_info["name"],
                "view_url": view_url
            })

        page += 1

    # --- ОТПРАВКА СТРОГО УНИКАЛЬНЫХ СЕССИЙ ---
    if not collected_records:
        print("\nℹ️ Новых встреч не найдено.")
    else:
        # Убираем дубли, если они пришли внутри одного ответа API
        unique_payload = {item["id"]: item for item in collected_records}.values()
        unique_payload = list(unique_payload)
        
        print(f"\n📋 БУДЕТ ДОБАВЛЕНО ВСТРЕЧ С УНИКАЛЬНЫМИ НАЗВАНИЯМИ: {len(unique_payload)} шт.")
        print("-" * 60)
        for idx, item in enumerate(unique_payload, 1):
            print(f"{idx}. [{item['manager_name']}] {item['name']} ({item['created_at']})")
        print("-" * 60)
        
        print("🚀 Отправка в Supabase...")
        final_payload = [{k: v for k, v in item.items() if k != 'manager_name'} for item in unique_payload]
        
        supabase.table("talk_records").insert(final_payload).execute()
        print("✅ Все уникальные встречи успешно сохранены!")
        
except Exception as e:
    print(f"🛑 Системная ошибка: {e}")
