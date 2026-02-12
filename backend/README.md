# Backend Setup Instructions

## 1. Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

## 2. Set Environment Variables

Create a `.env` file in the `backend/` directory:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

## 3. Start the Backend Server

```bash
python main.py
```

Server will run on `http://localhost:8000`

## 4. Open the Frontend

Simply open `frontend/index.html` in your browser, or use a simple HTTP server:

```bash
cd frontend
python -m http.server 3000
```

Then visit `http://localhost:3000`

## 5. Test

Upload a PDF bank statement and verify:
- Summary displays correctly
- Totals match
- Excel downloads successfully
