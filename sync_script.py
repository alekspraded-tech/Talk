import os
import requests
import time
from datetime import datetime, timedelta
from supabase import create_client, Client

# --- НАСТРОЙКИ ---
TALK_API_URL = "https://portalwash.ktalk.ru/api/Domain/recordings/v2"
TALK_API_KEY = "C1DM4licsSxT6f0I9Ms89GSELXTSCCTf"

# Актуальный список менеджеров
MANAGERS = {
    "45cd0d96-9fb7-40db-88bf-e1350dc28fe1": {"name": "Алексей Беликов", "email": "a.belikov@portalwash.ru"},
    "3ae59251-f4b6-4b38-9cda-ef6a56cc7127": {"name": "Евгений Журавлев", "email": "e.zhuravlev@portalwash.ru"},
    "b3a8158c-de22-485c-9cee-43c13c9de592": {"name": "Валерий Старостин", "email": "v.starostin@portalwash.ru"},
    "db318192-e04a-4d2b-b39b-23e77643d4da": {"name": "Александр Прадед", "email": "a.praded@portalwash.ru"}
}

SUPABASE_URL = "https://jqtznmrwxswbveugfsbv.supabase.co" 
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not SUPABASE_KEY:
    print("ERROR: SUPABASE_SERVICE_KEY not found!")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("Starting sync with OpenAI AI (via Bothub Gateway)...")

# --- CHECK AVAILABLE AI SERVICES ---
OPENAI_AVAILABLE = False

if OPENAI_API_KEY:
    print("Checking OpenAI (Bothub) API availability...")
    url = "https://openai.bothub.chat/v1/chat/completions"
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
    print("   Please check your OPENAI_API_KEY in GitHub Secrets")

# --- AI CALL FUNCTION WITH RETRY LOGIC ---
def call_openai(prompt, timeout_seconds=30):
    """Call OpenAI API via Bothub with automatic exponential backoff for 429 errors"""
    url = "https://openai.bothub.chat/v1/chat/completions"
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": "Ты — эксперт по методологии продаж и контролю качества диалогов. Ты детально анализируешь транскрипты встреч, объективно выставляешь баллы и пишешь конструктивные комментарии строго на РУССКОМ языке."
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
        created_by
