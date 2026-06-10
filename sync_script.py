import os
import requests
import time
from datetime import datetime, timedelta
from supabase import create_client, Client

# --- НАСТРОЙКИ ---
TALK_API_URL = "https://portalwash.ktalk.ru/api/Domain/recordings/v2"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

MANAGERS = {
    "45cd0d96-9fb7-40db-88bf-e1350dc28fe1": {"name": "Алексей Беликов", "email": "a.belikov@portalwash.ru"},
    "3ae59251-f4b6-4b38-9cda-ef6a56cc7127": {"name": "Евгений Журавлев", "email": "e.zhuravlev@portalwash.ru"},
    "01c7dc8e-b715-470e-9766-43c8363a2760": {"name": "Николай Киселев", "email": "n.kiselyov@portalwash.ru"},
    "db318192-e04a-4d2b-b39b-23e77643d4da": {"name": "Александр Прадед", "email": "a.praded@portalwash.ru"}
}

SUPABASE_URL = "https://jqtznmrwxswbveugfsbv.supabase.co" 
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("🛑 Ошибка: Ключ GEMINI_API_KEY не найден в GitHub Secrets!")
    exit(1)

if not SUPABASE_KEY:
    print("🛑 Ошибка: Ключ SUPABASE_SERVICE_KEY не найден в GitHub Secrets!")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("🚀 Запуск синхронизации встреч, транскрибации и ИИ-анализа...")

# --- СПИСОК ДОСТУПНЫХ МОДЕЛЕЙ (по приоритету) ---
GEMINI_MODELS = [
    "models/gemini-2.0-flash",
    "models/gemini-2.0-flash-lite",
    "models/gemini-flash-latest"
]

# --- ФУНКЦИЯ ДЛЯ ВЫЗОВА GEMINI С ПЕРЕКЛЮЧЕНИЕМ МОДЕЛЕЙ ---
def call_gemini_with_fallback(prompt, max_retries_per_model=2):
    """
    Пытается вызвать Gemini последовательно на разных моделях
    При ошибке 503 переключается на следующую модель
    """
    for model_idx, model_name in enumerate(GEMINI_MODELS):
        print(f"   🔄 Попытка {model_idx + 1}/{len(GEMINI_MODELS)}: {model_name}")
        
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GEMINI_API_KEY}"
        
        gemini_payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2000,
                "responseMimeType": "text/plain"
            }
        }
        
        for attempt in range(max_retries_per_model):
            try:
                g_res = requests.post(
                    gemini_url, 
                    json=gemini_payload, 
                    headers={"Content-Type": "application/json"},
                    timeout=60
                )
                
                if g_res.status_code == 200:
                    g_data = g_res.json()
                    result = g_data['candidates'][0]['content']['parts'][0]['text']
                    print(f"   ✅ Успех на модели {model_name}")
                    return result
                
                # Ошибка перегрузки - пробуем другую модель
                if g_res.status_code in [429, 503]:
                    print(f"   ⚠️ Модель {model_name} перегружена (Код {g_res.status_code})")
                    break  # Переходим к следующей модели
                
                # Другие ошибки - пробуем ещё раз на той же модели
                if attempt < max_retries_per_model - 1:
                    wait_time = 5
                    print(f"   ⏳ Ошибка {g_res.status_code}, повтор через {wait_time} сек...")
                    time.sleep(wait_time)
                else:
                    print(f"   ❌ Модель {model_name} не работает: {g_res.status_code}")
                    
            except requests.exceptions.Timeout:
                print(f"   ⏳ Таймаут на модели {model_name}")
                break
            except Exception as e:
                print(f"   ⚠️ Ошибка: {e}")
                break
    
    print("   ❌ Все модели недоступны!")
    return None


# --- ДИНАМИЧЕСКИЙ ПОИСК ДОСТУПНЫХ МОДЕЛЕЙ (для информации) ---
print("🔍 Проверка доступности моделей Gemini...")
available_models = []

for model_name in GEMINI_MODELS:
    test_url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GEMINI_API_KEY}"
    test_payload = {"contents": [{"parts": [{"text": "test"}]}]}
    
    try:
        test_res = requests.post(test_url, json=test_payload, timeout=10)
        if test_res.status_code == 200:
            available_models.append(model_name)
            print(f"   ✅ {model_name} - доступна")
        elif test_res.status_code == 503:
            print(f"   ⚠️ {model_name} - перегружена (будет использована при fallback)")
            available_models.append(model_name)
        else:
            print(f"   ❌ {model_name} - ошибка {test_res.status_code}")
    except:
        print(f"   ❌ {model_name} - недоступна")

if not available_models:
    print("🛑 Ни одна модель Gemini недоступна! Проверьте API ключ.")
    exit(1)

print(f"🎯 Будет использован fallback между: {available_models}\n")

# Шаг 0. Загружаем существующие записи
existing_summaries = {}
try:
    res = supabase.table("talk_records").select("id", "summary").execute()
    if res.data:
        existing_summaries = {str(row["id"]): row.get("summary") for row in res.data}
        print(f"📚 Загружено {len(existing_summaries)} существующих записей\n")
except Exception as e:
    print(f"⚠️ Ошибка чтения базы: {e}")

headers = {"X-Auth-Token": TALK_API_KEY, "Accept": "application/json"}
date_limit = datetime.utcnow() - timedelta(days=7)

total_processed = 0
total_summarized = 0

for page in range(1, 6):
    print(f"📄 Страница {page}...")
    response = requests.get(TALK_API_URL, headers=headers, params={"page": page, "size": 50})
    if response.status_code != 200:
        print(f"   Ошибка API: {response.status_code}")
        break
    
    records = response.json().get("entities", [])
    if not records:
        print(f"   Нет записей на странице {page}")
        break
    
    to_upsert = []
    for record in records:
        created_by = record.get("createdBy") or {}
        user_id = created_by.get("login")
        
        if user_id in MANAGERS:
            if record.get("duration", 0) == 0 or record.get("size", 0) == 0:
                continue
                
            rec_key = record.get("key")
            if not rec_key:
                continue
            
            created_date = record.get("createdDate", "").replace("Z", "").replace(":", "").replace("-", "").replace("T", "_")
            unique_db_id = f"{rec_key}_{created_date}"
            
            # --- 1. СБОР ТРАНСКРИПТА ---
            full_transcript_text = None
            try:
                transcript_url = f"https://portalwash.ktalk.ru/api/recordings/{rec_key}/transcript"
                t_res = requests.get(transcript_url, headers=headers, timeout=30)
                
                if t_res.status_code == 200:
                    tracks = t_res.json().get("tracks") or []
                    chunks_timeline = []
                    
                    for track in tracks:
                        speaker_obj = track.get("speaker") or {}
                        speaker_name = speaker_obj.get("anonymousName") if speaker_obj.get("isAnonymous") else f"{(speaker_obj.get('userInfo') or {}).get('firstname', '')} {(speaker_obj.get('userInfo') or {}).get('surname', '')}".strip()
                        speaker_name = speaker_name or "Спикер"
                        
                        for chunk in track.get("chunks") or []:
                            start_ms = chunk.get("startTimeOffsetInMillis", 0)
                            text = chunk.get("text", "")
                            if text:
                                chunks_timeline.append((start_ms, speaker_name, text))
                    
                    chunks_timeline.sort(key=lambda x: x[0])
                    full_transcript_text = "\n".join([f"[{c[0]//60000:02d}:{(c[0]%60000)//1000:02d}] {c[1]}: {c[2]}" for c in chunks_timeline])
                    
            except Exception as t_err:
                print(f"   ⚠️ Ошибка транскрипта {rec_key}: {t_err}")

            # --- 2. ОБРАБОТКА В GEMINI ---
            ai_summary = None
            
            if unique_db_id in existing_summaries and existing_summaries[unique_db_id]:
                ai_summary = existing_summaries[unique_db_id]
                print(f"   📦 Кэш: '{record.get('title', 'Без названия')[:40]}'")
            elif full_transcript_text:
                print(f"   🧠 Анализ: '{record.get('title', 'Без названия')[:40]}'...")
                
                # Обрезаем слишком длинный транскрипт (первые 10 тысяч символов)
                transcript_for_analysis = full_transcript_text[:10000]
                if len(full_transcript_text) > 10000:
                    transcript_for_analysis += "\n\n... (транскрипт обрезан из-за длины)"
                
                prompt = (
                    "Ты — профессиональный ИИ-ассистент контроля качества отдела продаж франшизы робомоек. "
                    "Твоя задача — проанализировать текст диалога (транскрипт) встречи сотрудника с клиентом/партнером и составить краткий структурированный отчет.\n\n"
                    "СЛЕДУЙ СТРОГОМУ СЦЕНАРИЮ ИЗ 3 ПУНКТОВ:\n"
                    "1. КРАТКАЯ СУТЬ ВСТРЕЧИ: С кем была встреча, какова основная тема и текущий статус переговоров (2-3 предложения).\n"
                    "2. ДОГОВОРЕННОСТИ И СЛЕДУЮЩИЕ ШАГИ: Список конкретных задач, кто за что отвечает и зафиксированные дедлайны.\n"
                    "3. ВОПРОСЫ И ВОЗРАЖЕНИЯ КЛИЕНТА: Какие сомнения, страхи или ключевые вопросы озвучил клиент во время разговора.\n\n"
                    f"Вот текст транскрипта для анализа:\n{transcript_for_analysis}"
                )
                
                # Вызываем Gemini с fallback между моделями
                ai_summary = call_gemini_with_fallback(prompt)
                
                if ai_summary:
                    total_summarized += 1
                    print(f"   ✅ Анализ завершён")
                else:
                    print(f"   ⚠️ Не удалось получить анализ")
            
            to_upsert.append({
                "id": unique_db_id,
                "name": record.get("title", "Без названия"),
                "created_at": record.get("createdDate"),
                "manager_email": MANAGERS[user_id]["email"],
                "view_url": f"https://portalwash.ktalk.ru/recordings/{rec_key}",
                "transcript": full_transcript_text[:50000] if full_transcript_text else None,  # Ограничиваем длину
                "summary": ai_summary
            })
            total_processed += 1
    
    if to_upsert:
        try:
            supabase.table("talk_records").upsert(to_upsert, on_conflict="id").execute()
            print(f"   💾 Сохранено {len(to_upsert)} записей\n")
        except Exception as db_err:
            print(f"   ⚠️ Ошибка сохранения: {db_err}\n")

print("=" * 60)
print(f"🎉 Синхронизация завершена!")
print(f"   📊 Всего обработано записей: {total_processed}")
print(f"   🤖 Создано новых ИИ-анализов: {total_summarized}")
print("=" * 60)
