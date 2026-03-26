<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# AI Bank Statement Analyzer

A powerful AI-driven tool for extracting, validating, and categorizing transactions from Nigerian bank statements (PDF, Excel, CSV).

## 🚀 Supported Banks (Verified)
- **Access Bank** (Searchable & OCR)
- **UBA** (Searchable & OCR)
- **WEMA Bank**
- **FCMB**
- **Zenith Bank**
- **GTBank / GTCO** (Multi-statement support)
- **Providus Bank**
- **Sterling Bank**
- **First Bank (FBN)**

## 🛠️ Run Locally (Manual)

**Prerequisites:** Node.js, Python 3.10+

1. **Environment Setup**:
   Create a `.env` file in the project root:
   ```bash
   GEMINI_API_KEY="your_key_here" # Supports comma-separated keys for rotation
   OPENAI_API_KEY="optional_fallback_key"
   ```

2. **Backend**:
   ```bash
   cd backend
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```

3. **Frontend**:
   ```bash
   # From the project root
   npm install
   npm run dev
   ```

## 🐳 Run Locally (Docker)

1. `cp .env.example .env` (Add your keys)
2. `docker-compose up --build`
3. Open http://localhost:8000

---
*Powered by Gemini 2.0 Flash for high-accuracy financial OCR.*
