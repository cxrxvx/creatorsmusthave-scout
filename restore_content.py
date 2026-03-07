import json, requests
from config import WP_URL, WP_USERNAME, WP_APP_PASSWORD

auth = (WP_USERNAME, WP_APP_PASSWORD)
data = json.load(open('memory/handoffs.json'))

restored = 0
failed = 0

for slug, article in data.items():
    wp_id = article.get('wp_post_id')
    content = article.get('article_html', '')

    if not wp_id or not content:
        print(f'Skipping {article.get("tool_name")} — no post ID or no content')
        continue

    resp = requests.post(
        f'{WP_URL}/wp-json/wp/v2/posts/{wp_id}',
        json={'content': content},
        auth=auth,
        timeout=30
    )

    if resp.status_code in (200, 201):
        print(f'Restored: {article.get("tool_name")} (post {wp_id}) — {len(content)} chars')
        restored += 1
    else:
        print(f'FAILED: {article.get("tool_name")} (post {wp_id}) — {resp.status_code}')
        failed += 1

print(f'\nDone — {restored} restored, {failed} failed')
