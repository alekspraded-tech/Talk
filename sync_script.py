import os
import requests

# Ключ от Толка
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

# Ваши ключи записей (часть URL после /recordings/)
target_ids = ["LQkycroHPleWOb7J5M5a", "GQc6RuIfwq7MZ2Moc50E"]

headers = {"X-Auth-Token": TALK_API_KEY, "Accept": "application/json"}

print("🔍 Прямой запрос информации о записях...")

for rec_id in target_ids:
    url = f"https://portalwash.ktalk.ru/api/Domain/recordings/{rec_id}"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Запись: {data.get('title')}")
        print(f"   Автор (createdBy): {data.get('createdBy')}")
        print(f"   Владелец (owner): {data.get('owner')}")
        print(f"   Полная структура данных: {data}")
    else:
        print(f"\n❌ Ошибка получения {rec_id}: {response.status_code} - {response.text}")
