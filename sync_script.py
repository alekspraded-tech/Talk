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

print("🤖 Запуск диагностического сканирования API Толка...")

headers = {
    "X-Auth-Token": TALK_API_KEY,
    "Accept": "application/json"
}

try:
    # Запрашиваем первую страницу с запасом (50 штук)
    response = requests.get(TALK_API_URL, headers=headers, params={"page": 1, "size": 50})
    if response.status_code != 200:
        print(f"🛑 Ошибка Толка: Код {response.status_code}")
        exit(1)

    data = response.json()
    records = data.get("entities", [])
    
    print(f"==================================================")
    print(f"🔍 ВСЕГО НАЙДЕНО ЗАПИСЕЙ НА СТРАНИЦЕ: {len(records)}")
    print(f"==================================================")
    
    collected_records = []
    
    for idx, record in enumerate(records, 1):
        title = record.get("title") or "Без названия"
        created_date = record.get("createdDate") or "Нет даты"
        
        # Вытаскиваем все возможные поля, где Контур может прятать автора
        created_by_obj = record.get("createdBy") or {}
        
        # Различные варианты ID автора в структуре Толка
        login_val = created_by_obj.get("login") if isinstance(created_by_obj, dict) else None
        id_val = created_by_obj.get("id") if isinstance(created_by_obj, dict) else None
        name_val = created_by_obj.get("displayName") if isinstance(created_by_obj, dict) else None
        
        # Печатаем диагностику по КАЖДОЙ встрече в лог
        print(f"{idx}. Встреча: '{title}' | Дата: {created_date}")
        print(f"   -> Проверка автора: login='{login_val}', id='{id_val}', name='{name_val}'")
        
        # Проверяем, совпал ли кто-то по нашему словарю MANAGERS
        matched_manager_id = None
        if login_val in MANAGERS:
            matched_manager_id = login_val
        elif id_val in MANAGERS:
            matched_manager_id = id_val
            
        if matched_manager_id:
            manager_info = MANAGERS[matched_manager_id]
            print(f"   🎯 Совпадение! Менеджер: {manager_info['name']}")
            
            record_id = record.get("id")
            collected_records.append({
                "id": str(record_id),
                "name": title,
                "created_at": created_date,
                "manager_email": manager_info["email"],
                "view_url": f"https://portalwash.ktalk.ru/recordings/{record_id}"
            })
        else:
            print(f"   ❌ Мимо (чужой отдел или не распознан ID)")
        print("-" * 50)

    # --- ОТПРАВКА ТОГО, ЧТО НАШЛОСЬ ---
    if collected_records:
        print(f"\n🚀 Отправка распознанных встреч в количестве {len(collected_records)} шт. в Supabase...")
        supabase.table("talk_records").upsert(collected_records, on_conflict="id").execute()
        print("✅ Готово!")
    else:
        print("\nℹ️ Ни одна встреча не подошла под текущие правила фильтрации.")

except Exception as e:
    print(f"🛑 Системная ошибка диагностики: {e}")
