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

if not SUPABASE_KEY:
    print("ERROR: SUPABASE_SERVICE_KEY not found!")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("Starting sync with Gemini AI (with 429 error handling)...")

# --- CHECK AVAILABLE AI SERVICES ---
GEMINI_AVAILABLE = False

# Check Gemini
if GEMINI_API_KEY:
    print("Checking Gemini API availability...")
    test_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    test_payload = {"contents": [{"parts": [{"text": "test"}]}]}
    
    try:
        test_res = requests.post(
            f"{test_url}?key={GEMINI_API_KEY}",
            json=test_payload,
            timeout=10
        )
        if test_res.status_code == 200:
            GEMINI_AVAILABLE = True
            print("   Gemini is available and will be used")
        elif test_res.status_code == 429:
            GEMINI_AVAILABLE = True
            print("   Gemini is available (but currently rate-limited). Proceeding with cautious delays...")
        else:
            print(f"   Gemini returned error {test_res.status_code}")
    except Exception as e:
        print(f"   Gemini connection error: {e}")

if not GEMINI_AVAILABLE:
    print("WARNING: Gemini AI service is not available! AI analysis will be skipped.")
    print("   Add GEMINI_API_KEY to GitHub Secrets")

# --- AI CALL FUNCTION WITH RETRY LOGIC ---
def call_gemini(prompt, timeout_seconds=30):
    """Call Gemini API with automatic exponential backoff for 429 errors"""
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt[:8000]}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1500,
        }
    }
    
    max_retries = 5
    backoff_factor = 2  # Пауза будет расти: 2, 4, 8, 16, 32 сек.
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{url}?key={GEMINI_API_KEY}",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=timeout_seconds
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'candidates' in data and data['candidates']:
                    return data['candidates'][0]['content']['parts'][0]['text']
            
            elif response.status_code == 429:
                sleep_time = backoff_factor ** (attempt + 1)
                print(f"   [429 Too Many Requests] Лимит исчерпан. Ждем {sleep_time} сек. перед повтором (Попытка {attempt + 1}/{max_retries})...")
                time.sleep(sleep_time)
                continue  # Идем на следующую попытку в цикле
                
            else:
                print(f"   Gemini error: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"   Gemini exception: {e}")
            time.sleep(3)  # Небольшая пауза при сетевых сбоях
            
    print("   Gemini failed after maximum retries due to rate limiting.")
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
        elif full_transcript_text and GEMINI_AVAILABLE:
            print(f"   AI analysis (Gemini): '{title}'...")
            
            prompt = (
                "You are an AI assistant for sales quality control. Analyze the dialogue:\n\n"
                "1. MEETING SUMMARY (2-3 sentences)\n"
                "2. AGREEMENTS AND NEXT STEPS\n"
                "3. CLIENT QUESTIONS AND OBJECTIONS\n\n"
                f"Transcript:\n{full_transcript_text[:5000]}"
            )
            
            ai_summary = call_gemini(prompt, timeout_seconds=25)
            
            if ai_summary:
                total_summarized += 1
                print(f"   Analysis complete")
            else:
                print(f"   Failed to get analysis")
            
            # Базовая задержка между запросами увеличена до 5 секунд для стабильности
            time.sleep(5)
        
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
print(f"   Gemini AI Available: {GEMINI_AVAILABLE}")
print(f"   Processed records: {total_processed}")
print(f"   AI analyses created: {total_summarized}")
print(f"   Errors: {total_errors}")

if not GEMINI_AVAILABLE:
    print("\nWARNING: Gemini AI service was not available!")
    print("   Add GEMINI_API_KEY to GitHub Secrets")

print("=" * 60)
