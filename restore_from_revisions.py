import requests
import json
from config import WP_URL, WP_USERNAME, WP_APP_PASSWORD

auth = (WP_USERNAME, WP_APP_PASSWORD)
data = json.load(open('memory/handoffs.json'))

# All post IDs that have been published
post_ids = [
    (slug, article.get('tool_name'), article.get('wp_post_id'))
    for slug, article in data.items()
    if article.get('wp_post_id') and article.get('status') in ('published', 'draft_live')
]

restored = 0
failed = 0

for slug, tool_name, wp_id in post_ids:
    # Get all revisions
    resp = requests.get(
        f'{WP_URL}/wp-json/wp/v2/posts/{wp_id}/revisions',
        auth=auth,
        timeout=30
    )

    if resp.status_code != 200:
        print(f'Could not fetch revisions for {tool_name}: {resp.status_code}')
        failed += 1
        continue

    revisions = resp.json()
    if not revisions:
        print(f'No revisions found for {tool_name}')
        failed += 1
        continue

    # Find the best revision — longest rendered content
    # (that's the clean publisher version)
    best = None
    best_len = 0

    for rev in revisions:
        rendered = rev.get('content', {}).get('rendered', '')
        # Skip revisions that are just schema blocks (under 5000 chars)
        if len(rendered) > best_len and len(rendered) > 5000:
            best = rev
            best_len = len(rendered)

    if not best:
        print(f'No good revision found for {tool_name} — skipping')
        failed += 1
        continue

    # Restore from best revision using rendered HTML
    clean_content = best.get('content', {}).get('rendered', '')
    rev_date = best.get('date', 'unknown')

    update_resp = requests.post(
        f'{WP_URL}/wp-json/wp/v2/posts/{wp_id}',
        json={'content': clean_content},
        auth=auth,
        timeout=30
    )

    if update_resp.status_code in (200, 201):
        print(f'✓ Restored: {tool_name} (post {wp_id}) — {len(clean_content)} chars from revision {rev_date}')
        restored += 1
    else:
        print(f'✗ Failed: {tool_name} (post {wp_id}) — {update_resp.status_code}')
        failed += 1

print(f'\nDone — {restored} restored, {failed} failed')
