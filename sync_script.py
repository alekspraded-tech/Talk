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
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("🚀 Запуск синхронизации встреч и выгрузки транскрибаций...")

headers = {"X-Auth-Token": TALK_API_KEY, "Accept": "application/json"}

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
            # Отсекаем пустые фрагменты сессий
            if record.get("duration", 0) == 0 or record.get("size", 0) == 0:
                continue
                
            rec_key = record.get("key")
            if not rec_key: continue
            
            created_date = record.get("createdDate", "").replace("Z", "").replace(":", "").replace("-", "").replace("T", "_")
            unique_db_id = f"{rec_key}_{created_date}"
            
            # --- ВЫГРУЗКА И СБОРКА ТРАНСКРИБАЦИИ ---
            full_transcript_text = None
            try:
                transcript_url = f"https://portalwash.ktalk.ru/api/recordings/{rec_key}/transcript"
                t_res = requests.get(transcript_url, headers=headers)
                
                if t_res.status_code == 200:
                    t_data = t_res.json()
                    tracks = t_data.get("tracks") or []
                    chunks_timeline = []
                    
                    # Проходим по дорожкам всех спикеров встречи
                    for track in tracks:
                        speaker_obj = track.get("speaker") or {}
                        if speaker_obj.get("isAnonymous"):
                            speaker_name = speaker_obj.get("anonymousName") or "Гость"
                        else:
                            u_info = speaker_obj.get("userInfo") or {}
                            speaker_name = f"{u_info.get('firstname', '')} {u_info.get('surname', '')}".strip() or "Спикер"
                        
                        # Собираем фразы
                        for chunk in track.get("chunks") or []:
                            start_ms = chunk.get("startTimeOffsetInMillis", 0)
                            text = chunk.get("text", "")
                            if text:
                                chunks_timeline.append((start_ms, speaker_name, text))
                    
                    # Сортируем все фразы по хронологии времени начала
                    chunks_timeline.sort(key=lambda x: x[0])
                    
                    # Форматируем в красивый текст с тайм-кодами
                    transcript_lines = []
                    for start_ms, speaker, text in chunks_timeline:
                        seconds = start_ms // 1000
                        hours = seconds // 3600
                        minutes = (seconds % 3600) // 60
                        rem_seconds = seconds % 60
                        
                        time_str = f"{hours:02d}:{minutes:02d}:{rem_seconds:02d}" if hours > 0 else f"{minutes:02d}:{rem_seconds:02d}"
                        transcript_lines.append(f"[{time_str}] {speaker}: {text}")
                    
                    if transcript_lines:
                        full_transcript_text = "\n".join(transcript_lines)
            except Exception as t_err:
                print(f"⚠️ Не удалось обработать транскрипт для {rec_key}: {t_err}")
            
            # Добавляем в пакет отправки
            to_upsert.append({
                "id": unique_db_id,
                "name": record.get("title", "Без названия"),
                "created_at": record.get("createdDate"),
                "manager_email": MANAGERS[user_id]["email"],
                "view_url": f"https://portalwash.ktalk.ru/recordings/{rec_key}",
                "transcript": full_transcript_text # Новое поле с готовым текстом диалога
            })
    
    if to_upsert:
        supabase.table("talk_records").upsert(to_upsert, on_conflict="id").execute()
        print(f"✅ Успешно синхронизировано полезных записей: {len(to_upsert)}")

print("🎉 Все доступные расшифровки выгружены!")
