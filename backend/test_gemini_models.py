import google.generativeai as genai
import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

def list_models():
    api_key = os.getenv("GEMINI_API_KEY", "").split(",")[0].strip()
    if not api_key:
        print("No API key")
        return
        
    print(f"Listing models for key ending in ...{api_key[-4:]}")
    
    try:
        genai.configure(api_key=api_key)
        for m in genai.list_models():
            print(f"Name: {m.name}, Methods: {m.supported_generation_methods}")
    except Exception as e:
        print(f"Failed to list models: {e}")

list_models()
