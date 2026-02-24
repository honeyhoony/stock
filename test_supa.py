import requests
import os
from dotenv import load_dotenv

load_dotenv()

url = f"{os.getenv('SUPABASE_URL')}/rest/v1/my_holdings"
headers = {
    "apikey": os.getenv("SUPABASE_KEY"),
    "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}"
}

print(f"Testing PUBLIC schema at {url}")
r = requests.get(url, headers=headers)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:200]}")

print("\nTesting EERS_CHATBOT schema")
headers["Accept-Profile"] = "eers_chatbot"
r = requests.get(url, headers=headers)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:200]}")
