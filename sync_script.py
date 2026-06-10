import requests

# Вставьте ваш API ключ Gemini
GEMINI_API_KEY = "ВАШ_API_КЛЮЧ"

def list_gemini_models():
    """Запрашивает и выводит список доступных моделей Gemini"""
    
    print("🔍 Запрос списка доступных моделей Gemini...")
    print("-" * 50)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    
    try:
        response = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            
            if not models:
                print("❌ Модели не найдены")
                return
            
            print(f"✅ Найдено моделей: {len(models)}\n")
            
            # Фильтруем только те, что поддерживают generateContent
            text_models = []
            for model in models:
                name = model.get("name", "unknown")
                methods = model.get("supportedGenerationMethods", [])
                
                if "generateContent" in methods:
                    text_models.append(name)
                    print(f"📝 {name} (поддерживает generateContent)")
                else:
                    print(f"⚙️ {name} (не поддерживает generateContent)")
            
            print("\n" + "=" * 50)
            print(f"🎯 Модели для текстовой генерации ({len(text_models)} шт.):")
            for m in text_models:
                print(f"   - {m}")
                
        else:
            print(f"❌ Ошибка API: Код {response.status_code}")
            print(f"Ответ: {response.text}")
            
    except requests.exceptions.Timeout:
        print("❌ Таймаут: Сервер не отвечает")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    # Вариант 1: Указать ключ прямо в коде
    list_gemini_models()
    
    # Вариант 2: Взять из переменной окружения (раскомментировать если нужно)
    # import os
    # GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    # if GEMINI_API_KEY:
    #     list_gemini_models()
    # else:
    #     print("🛑 Установите переменную окружения GEMINI_API_KEY")
