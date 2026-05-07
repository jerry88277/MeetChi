import requests
r=requests.get('https://meetchi-backend-705495828555.asia-southeast1.run.app/api/v1/meetings/1ca161bb-8e20-4440-94a3-f68866baeaee')
d=r.json()
print('Status:', d.get('status'))
print('Summary:', 'yes' if d.get('summary_json') else 'no')
