import requests
import json
import re
from config import WP_URL, WP_USERNAME, WP_APP_PASSWORD

auth = (WP_USERNAME, WP_APP_PASSWORD)
data = json.load(open('memory/handoffs.json'))

def strip_h1(html):
    """Remove the first H1 tag from content."""
    return re.sub(r'<h1[^>]*>.*?</h1>', '', html, count=1, flags=re.DOTALL).strip()

def strip_emojis(html):
    """Remove emoji characters from content."""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F9FF"
        "\U00002600-\U000027BF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002702-\U000027B0"
        "]+",
        flags=re.UNICODE
    )
    return emoji_pattern.sub('', html)

def clean_content(html):
    """Apply all publisher cleaning rules."""
    html = strip_h1(html)
    html = strip_emojis(html)
    return html.strip()

post_ids = [
    (slug, article.get('tool_name'), article.get('wp_post_id'))
    for slug, article in data.items()
    if article.get('wp_post_id') and article.get('status') in ('published', 'draft_live')
]

restored = 0
failed   = 0

for slug, tool_name, wp_id in post_ids:
    # Get revisions
    resp = requests.get(
        f'{WP_URL}/wp-json/wp/v2/posts/{wp_id}/revisions',
        auth=auth, timeout=30
    )

    if resp.status_code != 200:
        print(f'Could not fetch revisions for {tool_name}')
        failed += 1
        continue

    revisions = resp.json()

    # Find longest revision over 5000 chars
    best = None
    best_len = 0
    for rev in revisions:
        rendered = rev.get('content', {}).get('rendered', '')
        if len(rendered) > best_len and len(rendered) > 5000:
            best = rev
            best_len = len(rendered)

    if not best:
        # Fall back to article_html from handoffs
        raw_html = data[slug].get('article_html', '')
        if not raw_html:
            print(f'No content found for {tool_name} — skipping')
            failed += 1
            continue
        source = 'handoffs.json'
        content = raw_html
    else:
        content = best.get('content', {}).get('rendered', '')
        source  = f'revision {best.get("date", "unknown")}'

    # Clean the content
    cleaned = clean_content(content)

    # Push back to WordPress
    update_resp = requests.post(
        f'{WP_URL}/wp-json/wp/v2/posts/{wp_id}',
        json={'content': cleaned},
        auth=auth, timeout=30
    )

    if update_resp.status_code in (200, 201):
        print(f'✓ {tool_name} (post {wp_id}) — {len(cleaned)} chars from {source}')
        restored += 1
    else:
        print(f'✗ Failed: {tool_name} (post {wp_id}) — {update_resp.status_code}')
        failed += 1

print(f'\nDone — {restored} restored and cleaned, {failed} failed')
print('Check your live site — articles should now be clean with no double titles or emojis.')
