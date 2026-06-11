import os
import requests
import time
from datetime import datetime, timedelta
from supabase import create_client, Client

# --- НАСТРОЙКИ ---
TALK_API_URL = "https://portalwash.ktalk.ru/api/Domain/recordings/v2"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

# ВАЖНО: Старый ID (01c7dc8e...) принадлежал Юлии. 
# Замените заглушку ниже на реальный ID Николая, когда поймаете его в логах консоли.
MANAGERS = {
    "45cd0d96-9fb7-40db-88bf-e1350dc28fe1": {"name": "Алексей Беликов", "email": "a.belikov@portalwash.ru"},
    "3ae59251-f4b6-4b38-9cda-ef6a56cc7127": {"name": "Евгений Журавлев", "email": "e.zhuravlev@portalwash.ru"},
    "НАСТОЯЩИЙ_ID_НИКОЛАЯ_ИЗ_КТАЛК": {"name": "Николай Киселев", "email": "n.kiselyov@portalwash.ru"},
    "db318192-e04a-4d2b-b39b-23e77643d4da": {"name": "Александр Прадед", "email": "a.praded@portalwash.ru"}
}

SUPABASE_URL = "https://jqtznmrwxswbveugfsbv.supabase.co" 
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not SUPABASE_KEY:
    print("ERROR: SUPABASE_SERVICE_KEY not found!")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("Starting sync with OpenAI AI (via Bothub)...")

# --- CHECK AVAILABLE AI SERVICES ---
OPENAI_AVAILABLE = False

if OPENAI_API_KEY:
    print("Checking OpenAI (Bothub) API availability...")
    url = "https://openai.bothub.ru/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "test"}],
        "max_tokens": 5
    }
    
    try:
        test_res = requests.post(url, json=payload, headers=headers, timeout=10)
        if test_res.status_code == 200:
            OPENAI_AVAILABLE = True
            print("   OpenAI (Bothub) is available and will be used")
        else:
            print(f"   OpenAI (Bothub) returned error {test_res.status_code}: {test_res.text}")
    except Exception as e:
        print(f"   OpenAI (Bothub) connection error: {e}")

if not OPENAI_AVAILABLE:
    print("WARNING: OpenAI AI service is not available! AI analysis will be skipped.")
    print("   Add OPENAI_API_KEY to GitHub Secrets")

# --- AI CALL FUNCTION WITH RETRY LOGIC ---
def call_openai(prompt, timeout_seconds=30):
    """Call OpenAI API via Bothub with automatic exponential backoff for 429 errors"""
    url = "https://openai.bothub.ru/v1/chat/completions"
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": "You are an AI assistant for sales quality control. Analyze dialogues and provide structured reports."
            },
            {
                "role": "user",
                "content": prompt[:8000]
            }
        ],
        "temperature": 0.2,
        "max_tokens": 1500
    }
    
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    max_retries = 5
    backoff_factor = 2
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout_seconds)
            
            if response.status_code == 200:
                data = response.json()
                if 'choices' in data and data['choices']:
                    return data['choices'][0]['message']['content']
            
            elif response.status_code == 429:
                sleep_time = backoff_factor ** (attempt + 1)
                print(f"   [429 Too Many Requests] Лимит Bothub исчерпан. Ждем {sleep_time} сек. (Попытка {attempt + 1}/{max_retries})...")
                time.sleep(sleep_time)
                continue
                
            else:
                print(f"   OpenAI error: {response.status_code}, Details: {response.text}")
                return None
                
        except Exception as e:
            print(f"   OpenAI exception: {e}")
            time.sleep(3)
            
    print("   OpenAI failed after maximum retries due to rate limiting.")
    return None

# --- LOAD CACHE ---
print("\nLoading existing records from Supabase...")
existing_summaries = {}
try:
    res = supabase.table("talk_records").select("id", "summary").execute()
    if res.data:
        existing_summaries = {str(row["id"]): row.get("summary") for row in res.data}
        print(f"   Loaded {len(existing_summaries)} records")
except Exception as e:
    print(f"   Error: {e}")

headers = {"X-Auth-Token": TALK_API_KEY, "Accept": "application/json"}

total_processed = 0
total_summarized = 0
total_errors = 0

# --- MAIN LOOP ---
for page in range(1, 6):
    print(f"\nPage {page}...")
    
    try:
        response = requests.get(
            TALK_API_URL, 
            headers=headers, 
            params={"page": page, "size": 50},
            timeout=30
        )
    except requests.exceptions.Timeout:
        print(f"   Timeout getting page {page}")
        continue
    
    if response.status_code != 200:
        print(f"   API error: {response.status_code}")
        break
    
    records = response.json().get("entities", [])
    if not records:
        print(f"   No records on page {page}")
        break
    
    print(f"   Found {len(records)} records")
    
    to_upsert = []
    for record in records:
        created_by = record.get("createdBy") or {}
        user_id = created_by.get("login")
        
        if user_id not in MANAGERS:
            # Выводим в логи все пропущенные ID, чтобы вы могли скопировать ID Николая
            title = record.get('title', 'Untitled')[:50]
            print(f"   [Инфо] Пропущен звонок от ID: {user_id}. Название встречи: '{title}'")
            continue
        
        duration = record.get("duration", 0)
        size = record.get("size", 0)
        if duration == 0 or size == 0:
            continue
        
        rec_key = record.get("key")
        if not rec_key:
            continue
        
        created_date = record.get("createdDate", "").replace("Z", "").replace(":", "").replace("-", "").replace("T", "_")
        unique_db_id = f"{rec_key}_{created_date}"
        
        title = record.get('title', 'Untitled')[:50]
        
        # --- LOAD TRANSCRIPT ---
        full_transcript_text = None
        try:
            transcript_url = f"https://portalwash.ktalk.ru/api/recordings/{rec_key}/transcript"
            t_res = requests.get(transcript_url, headers=headers, timeout=20)
            
            if t_res.status_code == 200:
                tracks = t_res.json().get("tracks") or []
                chunks_timeline = []
                
                for track in tracks:
                    speaker_obj = track.get("speaker") or {}
                    speaker_name = speaker_obj.get("anonymousName") if speaker_obj.get("isAnonymous") else f"{(speaker_obj.get('userInfo') or {}).get('firstname', '')} {(speaker_obj.get('userInfo') or {}).get('surname', '')}".strip()
                    speaker_name = speaker_name or "Speaker"
                    
                    for chunk in track.get("chunks") or []:
                        start_ms = chunk.get("startTimeOffsetInMillis", 0)
                        text = chunk.get("text", "")
                        if text:
                            chunks_timeline.append((start_ms, speaker_name, text))
                
                chunks_timeline.sort(key=lambda x: x[0])
                full_transcript_text = "\n".join([f"[{c[0]//60000:02d}:{(c[0]%60000)//1000:02d}] {c[1]}: {c[2]}" for c in chunks_timeline])
                
        except Exception as t_err:
            print(f"   Transcript error for {title}: {t_err}")
            total_errors += 1

        # --- AI ANALYSIS ---
        ai_summary = None
        
        # Check cache first
        if unique_db_id in existing_summaries and existing_summaries[unique_db_id]:
            ai_summary = existing_summaries[unique_db_id]
            print(f"   Cached: '{title}'")
        elif full_transcript_text and OPENAI_AVAILABLE:
            print(f"   AI analysis (OpenAI): '{title}'...")
            
            prompt = (
                "You are an AI assistant for sales quality control. Analyze the dialogue:\n\n"
                "1. MEETING SUMMARY (2-3 sentences)\n"
                "2. AGREEMENTS AND NEXT STEPS\n"
                "3. CLIENT QUESTIONS AND OBJECTIONS\n\n"
                f"Transcript:\n{full_transcript_text[:5000]}"
            )
            
            ai_summary = call_openai(prompt, timeout_seconds=25)
            
            if ai_summary:
                total_summarized += 1
                print(f"   Analysis complete")
            else:
                print(f"   Failed to get analysis")
            
            time.sleep(1.5)
        
        to_upsert.append({
            "id": unique_db_id,
            "name": title,
            "created_at": record.get("createdDate"),
            "manager_email": MANAGERS[user_id]["email"],
            "view_url": f"https://portalwash.ktalk.ru/recordings/{rec_key}",
            "transcript": full_transcript_text[:50000] if full_transcript_text else None,
            "summary": ai_summary
        })
        total_processed += 1
    
    # Save page
    if to_upsert:
        try:
            supabase.table("talk_records").upsert(to_upsert, on_conflict="id").execute()
            print(f"   Saved {len(to_upsert)} records")
        except Exception as db_err:
            print(f"   Database error: {db_err}")
    
    time.sleep(1)

# --- RESULTS ---
print("\n" + "=" * 60)
print("SYNC RESULTS:")
print(f"   OpenAI AI Available: {OPENAI_AVAILABLE}")
print(f"   Processed records: {total_processed}")
print(f"   AI analyses created: {total_summarized}")
print(f"   Errors: {total_errors}")

if not OPENAI_AVAILABLE:
    print("\nWARNING: OpenAI AI service was not available!")
    print("   Add OPENAI_API_KEY to GitHub Secrets")

print("=" * 60)
