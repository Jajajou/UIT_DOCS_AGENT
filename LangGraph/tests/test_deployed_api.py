import os
import sys
import httpx

def check_deployment(url: str):
    print(f"Checking deployment at {url}...")
    try:
        # LangGraph API has an /info endpoint
        response = httpx.get(f"{url}/info", timeout=10.0)
        if response.status_code == 200:
            print("✅ Deployment is healthy and responding to /info.")
            print(f"Server Info: {response.json()}")
            return True
        else:
            print(f"❌ Deployment returned status code {response.status_code}.")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Failed to connect to deployment: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = os.getenv("LANGGRAPH_URL", "http://localhost:8123")
    
    # Strip trailing slash
    url = url.rstrip('/')
    
    success = check_deployment(url)
    sys.exit(0 if success else 1)