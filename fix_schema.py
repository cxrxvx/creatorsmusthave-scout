import json, requests, re
from config import WP_URL, WP_USERNAME, WP_APP_PASSWORD

auth = (WP_USERNAME, WP_APP_PASSWORD)
data = json.load(open('memory/handoffs.json'))

for slug, article in data.items():
    wp_id = article.get('wp_post_id')
    if not wp_id or not article.get('seo_done'):
        continue

    resp = requests.get(f'{WP_URL}/wp-json/wp/v2/posts/{wp_id}', auth=auth)
    if resp.status_code != 200:
        print(f'Could not fetch: {article.get("tool_name")}')
        continue

    content = resp.json().get('content', {}).get('raw', '')
    cleaned = re.sub(r'\n*<!-- wp:html -->.*?<!-- /wp:html -->', '', content, flags=re.DOTALL).strip()

    if cleaned != content:
        requests.post(f'{WP_URL}/wp-json/wp/v2/posts/{wp_id}', json={'content': cleaned}, auth=auth)
        print(f'Fixed: {article.get("tool_name")} (post {wp_id})')
    else:
        print(f'Already clean: {article.get("tool_name")}')

print('\nDone — all schema blocks removed from post content.')
