import requests
import time

def test_llm_service():
    url = "http://192.168.0.103:5000/polish"
    raw_text = "呃...那個，今天的天氣，好像不錯，對吧？"
    
    print(f"Sending raw text: {raw_text}")
    
    try:
        start_time = time.time()
        response = requests.post(url, json={"text": raw_text})
        response.raise_for_status()
        
        result = response.json()
        end_time = time.time()
        
        print(f"Response Code: {response.status_code}")
        print(f"Polished Text: {result.get('polished_text')}")
        print(f"Time Taken: {end_time - start_time:.2f} seconds")
        
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to LLM service. Is it running on port 5000?")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    test_llm_service()
