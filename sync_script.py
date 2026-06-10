import os
import requests
from supabase import create_client, Client

# --- НАСТРОЙКИ КОНТУР.ТОЛК ---
# Точный адрес API из вашей спецификации (с учетом регистра букв!)
TALK_API_URL = "https://portalwash.ktalk.ru/api/Domain/recordings/v2"
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
    print("🛑 Ошибка: Секретный ключ SUPABASE_SERVICE_KEY не найден в GitHub Secrets!")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def sync_talk_to_supabase():
    print(f"Запрос данных из Контур.Толк по официальному пути: {TALK_API_URL}...")
    
    # Способ 1: Спецификация OpenAPI (Bearer)
    headers_bearer = {
        "Authorization": f"Bearer {TALK_API_KEY}",
        "Accept": "application/json"
    }
    
    # Способ 2: Классический Контур (X-Auth-Token)
    headers_auth_token = {
        "X-Auth-Token": TALK_API_KEY,
        "Accept": "application/json"
    }
    
    response = None
    
    # Пробуем первый вариант авторизации
    print("Пробуем авторизацию через 'Authorization: Bearer'...")
    res1 = requests.get(TALK_API_URL, headers=headers_bearer)
    if res1.status_code == 200:
        response = res1
        print("🎯 Авторизация через Bearer успешна!")
    else:
        print(f"❌ Авторизация через Bearer выдала код {res1.status_code}")
        
        # Если первый не подошел, пробуем второй вариант
        print("Пробуем авторизацию через 'X-Auth-Token'...")
        res2 = requests.get(TALK_API_URL, headers=headers_auth_token)
        if res2.status_code == 200:
            response = res2
            print("🎯 Авторизация через X-Auth-Token успешна!")
        else:
            print(f"🛑 Оба способа авторизации отклонены сервером (Код {res2.status_code})")
            print(f"Ответ сервера: {res2.text[:300]}")
            return

    # Разбираем успешный ответ
    try:
        data = response.json()
    except Exception as json_err:
        print(f"🛑 Ответ сервера не является JSON. Текст: {response.text[:300]}")
        return

    records = data.get("entities", [])
    print(f"Успешно получено. Всего записей на странице API: {len(records)}")
    
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
        print("ℹ️ Подключение успешно! Но звонков от нужных 3 менеджеров на этой странице нет.")
        return

    print(f"🚀 Найдено {len(payload)} записей менеджеров. Отправка в Supabase...")
    result = supabase.table("talk_records").upsert(payload, on_conflict="id").execute()
    print("✅ ВСЕ ДАННЫЕ УСПЕШНО ЗАПИСАНЫ В SUPABASE!")
