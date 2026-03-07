import json

data = json.load(open('memory/handoffs.json'))

reset = 0
for slug, article in data.items():
    if article.get('seo_done'):
        article['seo_done'] = False
        print(f'Reset: {article.get("tool_name")}')
        reset += 1

json.dump(data, open('memory/handoffs.json', 'w'), indent=2)
print(f'\nDone — {reset} articles reset and ready for SEO agent')
