import os
import requests

# --- НАСТРОЙКИ КОНТУР.ТОЛК ---
TALK_API_URL = "https://portalwash.ktalk.ru/api/Domain/recordings/v2"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

def test_talk_emails():
    headers = {
        "X-Auth-Token": TALK_API_KEY,
        "Accept": "application/json"
    }
    
    print("🤖 Запуск диагностического сканирования создателей встреч...")
    
    try:
        response = requests.get(TALK_API_URL, headers=headers)
        if response.status_code != 200:
            print(f"🛑 Ошибка API: Код {response.status_code}")
            return

        data = response.json()
        records = data.get("entities", [])
        
        if not records:
            print("ℹ️ Записей на первой странице вообще нет.")
            return
            
        print(f"--- НАЙДЕНЫ СЛЕДУЮЩИЕ СОЗДАТЕЛИ ВСТРЕЧ (Всего {len(records)} записей): ---")
        
        found_emails = set()
        for record in records:
            if not isinstance(record, dict):
                continue
            
            # Извлекаем данные создателя
            created_by = record.get("createdBy", {})
            title = record.get("title", "Без названия")
            
            if isinstance(created_by, dict):
                email = created_by.get("email")
                login = created_by.get("login")
                name = f"{created_by.get('surname', '')} {created_by.get('firstname', '')}".strip()
                
                info_str = f"Встреча: '{title}' -> Владелец: [{name}] | Email: '{email}' | Login: '{login}'"
                found_emails.add(info_str)
        
        for info in sorted(found_emails):
            print(info)
            
        print("----------------------------------------------------------------")
        print("💡 Сравните эти Email и Login со списком ваших менеджеров.")

    except Exception as e:
        print(f"🛑 Системная ошибка: {e}")

if __name__ == "__main__":
    test_talk_emails()
