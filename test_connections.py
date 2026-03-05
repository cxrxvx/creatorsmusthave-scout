import requests
import base64
from config import ANTHROPIC_API_KEY, WP_URL, WP_USERNAME, WP_APP_PASSWORD

print("🔍 Testing connections...\n")

# === TEST 1: WordPress ===
print("1️⃣  Testing WordPress connection...")
credentials = base64.b64encode(f"{WP_USERNAME}:{WP_APP_PASSWORD}".encode()).decode()
response = requests.get(
    f"{WP_URL}/wp-json/wp/v2/posts",
    headers={"Authorization": f"Basic {credentials}"}
)
if response.status_code == 200:
    print("✅ WordPress connected successfully!\n")
else:
    print(f"❌ WordPress failed — status code: {response.status_code}")
    print(f"   Response: {response.text[:200]}\n")

# === TEST 2: Claude API ===
print("2️⃣  Testing Claude API connection...")
import anthropic
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
message = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=50,
    messages=[{"role": "user", "content": "Say: API connection successful"}]
)
print(f"✅ Claude API connected! Response: {message.content[0].text}\n")

print("🎉 All systems go! Ready to build agents.")