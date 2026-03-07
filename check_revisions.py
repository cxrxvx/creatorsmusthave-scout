import requests
from config import WP_URL, WP_USERNAME, WP_APP_PASSWORD

auth = (WP_USERNAME, WP_APP_PASSWORD)

# Check revisions for Jasper AI post
resp = requests.get(f'{WP_URL}/wp-json/wp/v2/posts/132/revisions', auth=auth, timeout=30)
print(f'Status: {resp.status_code}')

if resp.status_code == 200:
    revisions = resp.json()
    print(f'Found {len(revisions)} revisions')
    for i, rev in enumerate(revisions):
        content = rev.get('content', {}).get('raw', '')
        rendered = rev.get('content', {}).get('rendered', '')
        date = rev.get('date', 'unknown')
        print(f'\nRevision {i+1}: {date}')
        print(f'  Raw length: {len(content)} chars')
        print(f'  Rendered length: {len(rendered)} chars')
        print(f'  First 200 chars: {content[:200] or rendered[:200]}')
else:
    print(f'Error: {resp.text[:300]}')
