import os
import requests
from supabase import create_client, Client

# --- НАСТРОЙКИ КОНТУР.ТОЛК ---
# Подставляем реальный домен portalwash вместо плейсхолдера Domain
TALK_API_URL = "https://portalwash.ktalk.ru/api/portalwash/recordings/v2"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

TARGET_EMAILS = [
    "a.belikov@portalwash.ru",
    "e.zhuravlev@portalwash.ru",
    "n.kiselyov@portalwash.ru"
]

# --- НАСТРОЙКИ SUPABASE ---
SUPABASE_URL = "https://jqtznmrwxswbveugfsbv.supabase.co" 
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_KEY:
    print("🛑 Ошибка: Ключ SUPABASE_SERVICE_KEY не найден!")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def sync_talk_to_supabase():
    print(f"Запрос данных из Контур.Толк: {TALK_API_URL}...")
    
    # Проверяем оба варианта заголовков, которые просит Контур
    variants = [
        {"Authorization": f"Bearer {TALK_API_KEY}", "Accept": "application/json"},
        {"X-Auth-Token": TALK_API_KEY, "Accept": "application/json"}
    ]
    
    response = None
    for i, headers in enumerate(variants, 1):
        try:
            res = requests.get(TALK_API_URL, headers=headers)
            if res.status_code == 200:
                response = res
                print(f"🎯 Способ авторизации #{i} сработал успешно!")
                break
            else:
                print(f"❌ Способ #{i} вернул статус: {res.status_code}")
        except Exception as e:
            print(f"Ошибка при проверке способа #{i}: {e}")
            
    if not response:
        print("🛑 Не удалось авторизоваться ни одним из способов.")
        return

    try:
        data = response.json()
    except Exception as e:
        print(f"🛑 Ответ сервера — не JSON. Текст: {response.text[:200]}")
        return

    records = data.get("entities", [])
    print(f"Успешно получено встреч от API: {len(records)}")
    
    target_emails_lower = [email.lower() for email in TARGET_EMAILS]
    payload = []
    
    for record in records:
        if not isinstance(record, dict):
            continue
            
        created_by = record.get("createdBy", {})
        owner_email = ""
        if isinstance(created_by, dict):
            owner_email = created_by.get("email") or ""
            
        owner_email = str(owner_email).lower()
        
        if owner_email in target_emails_lower:
            record_id = record.get("id")
            view_url = f"https://portalwash.ktalk.ru/recordings/{record_id}"
            
            payload.append({
                "id": str(record_id),
                "name": record.get("title") or "Встреча без названия",
                "created_at": record.get("createdDate"),
                "manager_email": owner_email,
                "view_url": view_url
            })
    
    if not payload:
        print("ℹ️ Подключение успешно, но новых звонков от 3 менеджеров нет.")
        return

    print(f"🚀 Найдено {len(payload)} записей. Отправка в Supabase...")
    supabase.table("talk_records").upsert(payload, on_conflict="id").execute()
    print("✅ ВСЕ ДАННЫЕ УСПЕШНО ЗАПИСАНЫ В SUPABASE!")

if __name__ == "__main__":
    sync_talk_to_supabase()
