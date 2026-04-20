import urllib.request
import json
import time

def test_cross_meeting_rag(question):
    url = 'https://meetchi-backend-705495828555.asia-southeast1.run.app/api/v1/rag/ask'
    data = {
        'question': question,
        'user_upn': 'test@company.com',
        'top_k': 5
    }
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})

    start = time.time()
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            end = time.time()
            result['time_taken'] = end - start
            return result
    except Exception as e:
        return {'error': str(e)}

if __name__ == '__main__':
    q1 = test_cross_meeting_rag('有提到專案進度或時程安排嗎？')
    q2 = test_cross_meeting_rag('會議中討論的最大的技術挑戰或瓶頸為何？')
    q3 = test_cross_meeting_rag('我是一隻小貓咪，喵喵喵，這跟會議無關')
    
    with open('rag_test_results.json', 'w', encoding='utf-8') as f:
        json.dump({'q1': q1, 'q2': q2, 'q3': q3}, f, ensure_ascii=False, indent=2)
