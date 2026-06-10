import os
import requests
from supabase import create_client, Client

TALK_API_URL = "https://portalwash.ktalk.ru/api/Domain/recordings/v2"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

# Ключ от Supabase
SUPABASE_URL = "https://jqtznmrwxswbveugfsbv.supabase.co" 
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

headers = {"X-Auth-Token": TALK_API_KEY, "Accept": "application/json"}

print(f"🕵️ Ищем записи, сканируем до 20 страниц...")

# Увеличим глубину поиска до 20 страниц
for page in range(1, 21):
    response = requests.get(TALK_API_URL, headers=headers, params={"page": page, "size": 50})
    data = response.json()
    records = data.get("entities", [])
    
    if not records:
        print(f"-> На странице {page} записей нет.")
        break

    for record in records:
        # Проверяем, есть ли наши целевые ID в списке (на всякий случай)
        rid = record.get("id")
        title = record.get("title", "").lower()
        
        # Если находим запись — выводим всё, что есть
        if rid in ["LQkycroHPleWOb7J5M5a", "GQc6RuIfwq7MZ2Moc50E"]:
            print(f"\n✅ НАШЛИ ВАШУ ЗАПИСЬ: {record.get('title')}")
            print(f"Автор (createdBy): {record.get('createdBy')}")
            print(f"Владелец (owner): {record.get('owner')}")
            print(f"---")
        
        # Также выведем ID автора любой записи, которая выглядит как ваша
        if "встреча" in title or "синк" in title or "запись" in title:
             if record.get('createdBy'):
                # Выведем случайную встречу для примера, чтобы понять структуру автора
                pass 

    print(f"Просканирована страница {page}...")
