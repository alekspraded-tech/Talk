import os
import requests
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

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("🚀 Запуск синхронизации встреч, транскрибации и ИИ-анализа...")

# --- ДИНАМИЧЕСКИЙ ПОИСК ДОСТУПНОЙ МОДЕЛИ ---
print("🔍 Запрос списка доступных моделей Gemini...")
SELECTED_MODEL = "models/gemini-1.5-flash"  # Фолбек по умолчанию

try:
    list_models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    models_res = requests.get(list_models_url, headers={"Accept": "application/json"})
    
    if models_res.status_code == 200:
        available_models = models_res.json().get("models", [])
        model_names = [m["name"] for m in available_models if "generateContent" in m.get("supportedGenerationMethods", [])]
        
        print(f"📋 Доступные текстовые модели в вашем аккаунте: {model_names}")
        
        # Выбираем оптимальный вариант из того, что одобрил Google
        if "models/gemini-1.5-flash" in model_names:
            SELECTED_MODEL = "models/gemini-1.5-flash"
        elif "models/gemini-1.5-pro" in model_names:
            SELECTED_MODEL = "models/gemini-1.5-pro"
        elif model_names:
            SELECTED_MODEL = model_names[0]  # Берем первую рабочую, если стандарты недоступны
            
        print(f"🎯 ИИ-анализ будет выполнен на модели: {SELECTED_MODEL}")
    else:
        print(f"⚠️ Не удалось получить список моделей (Код {models_res.status_code}). Используем фолбек: {SELECTED_MODEL}")
except Exception as e:
    print(f"⚠️ Ошибка при опросе API моделей: {e}. Используем фолбек: {SELECTED_MODEL}")


# Шаг 0. Загружаем существующие записи, чтобы узнать, у кого уже есть ИИ-анализ
existing_summaries = {}
try:
    res = supabase.table("talk_records").select("id", "summary").execute()
    if res.data:
        existing_summaries = {str(row["id"]): row.get("summary") for row in res.data}
except Exception as e:
    print(f"⚠️ Ошибка чтения базы: {e}")

headers = {"X-Auth-Token": TALK_API_KEY, "Accept": "application/json"}
date_limit = datetime.utcnow() - timedelta(days=7)

for page in range(1, 6):
    response = requests.get(TALK_API_URL, headers=headers, params={"page": page, "size": 50})
    if response.status_code != 200: break
    
    records = response.json().get("entities", [])
    if not records: break
    
    to_upsert = []
    for record in records:
        created_by = record.get("createdBy") or {}
        user_id = created_by.get("login")
        
        if user_id in MANAGERS:
            if record.get("duration", 0) == 0 or record.get("size", 0) == 0:
                continue
                
            rec_key = record.get("key")
            if not rec_key: continue
            
            created_date = record.get("createdDate", "").replace("Z", "").replace(":", "").replace("-", "").replace("T", "_")
            unique_db_id = f"{rec_key}_{created_date}"
            
            # --- 1. СБОР ТРАНСКРИПТА ---
            full_transcript_text = None
            try:
                transcript_url = f"https://portalwash.ktalk.ru/api/recordings/{rec_key}/transcript"
                t_res = requests.get(transcript_url, headers=headers)
                
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
                            if text: chunks_timeline.append((start_ms, speaker_name, text))
                    
                    chunks_timeline.sort(key=lambda x: x[0])
                    full_transcript_text = "\n".join([f"[{c[0]//60000:02d}:{(c[0]%60000)//1000:02d}] {c[1]}: {c[2]}" for c in chunks_timeline])
            except Exception as t_err:
                print(f"⚠️ Ошибка транскрипта {rec_key}: {t_err}")

            # --- 2. ОБРАБОТКА В GEMINI ПО СЦЕНАРИЮ ---
            ai_summary = None
            
            if unique_db_id in existing_summaries and existing_summaries[unique_db_id]:
                ai_summary = existing_summaries[unique_db_id]
            elif full_transcript_text:
                print(f"🧠 Отправка транскрипта встречи '{record.get('title')}' в Gemini...")
                try:
                    # Динамический URL на основе автоматически выбранной модели
                    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/{SELECTED_MODEL}:generateContent?key={GEMINI_API_KEY}"
                    
                    prompt = (
                        "Ты — профессиональный ИИ-ассистент контроля качества отдела продаж франшизы робомоек. "
                        "Твоя задача — проанализировать текст диалога (транскрипт) встречи сотрудника с клиентом/партнером и составить краткий структурированный отчет.\n\n"
                        "СЛЕДУЙ СТРОГОМУ СЦЕНАРИЮ ИЗ 3 ПУНКТОВ:\n"
                        "1. КРАТКАЯ СУТЬ ВСТРЕЧИ: С кем была встреча, какова основная тема и текущий статус переговоров (2-3 предложения).\n"
                        "2. ДОГОВОРЕННОСТИ И СЛЕДУЮЩИЕ ШАГИ: Список конкретных задач, кто за что отвечает и зафиксированные дедлайны.\n"
                        "3. ВОПРОСЫ И ВОЗРАЖЕНИЯ КЛИЕНТА: Какие сомнения, страхи или ключевые вопросы озвучил клиент во время разговора.\n\n"
                        f"Вот текст транскрипта для анализа:\n{full_transcript_text}"
                    )
                    
                    gemini_payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.2,
                            "responseMimeType": "text/plain"
                        }
                    }
                    
                    g_res = requests.post(gemini_url, json=gemini_payload, headers={"Content-Type": "application/json"})
                    
                    if g_res.status_code == 200:
                        g_data = g_res.json()
                        ai_summary = g_data['candidates'][0]['content']['parts'][0]['text']
                    else:
                        print(f"⚠️ Ошибка Gemini (Код {g_res.status_code}): {g_res.text}")
                except Exception as g_err:
                    print(f"⚠️ Сбой сети при запросе к Gemini: {g_err}")
            
            to_upsert.append({
                "id": unique_db_id,
                "name": record.get("title", "Без названия"),
                "created_at": record.get("createdDate"),
                "manager_email": MANAGERS[user_id]["email"],
                "view_url": f"https://portalwash.ktalk.ru/recordings/{rec_key}",
                "transcript": full_transcript_text,
                "summary": ai_summary
            })
            
    if to_upsert:
        supabase.table("talk_records").upsert(to_upsert, on_conflict="id").execute()
        print(f"✅ Успешно обновлен пул записей: {len(to_upsert)}")

print("🎉 Все встречи обработаны ИИ и сохранены!")
