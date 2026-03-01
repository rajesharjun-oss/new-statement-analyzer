import google.generativeai as genai
import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

def test_config():
    api_key = os.getenv("GEMINI_API_KEY", "").split(",")[0].strip()
    if not api_key:
        print("No API key")
        return
        
    print(f"Testing with key ending in ...{api_key[-4:]}")
    
    # Try without transport='rest' first
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        # Simple test prompt
        response = model.generate_content("Say hello")
        print(f"Success (Default): {response.text}")
    except Exception as e:
        print(f"Failed (Default): {e}")

    # Try with 'gemini-1.5-flash-latest'
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content("Say hello")
        print(f"Success (latest): {response.text}")
    except Exception as e:
        print(f"Failed (latest): {e}")

test_config()
