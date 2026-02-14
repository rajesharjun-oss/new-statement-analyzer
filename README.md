<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Run and deploy your AI Studio app

This contains everything you need to run your app locally.

View your app in AI Studio: https://ai.studio/apps/drive/19v6lMOKrwyS8J7NIFdcEsJlPKW9vtOgI

# Run and deploy your AI Studio app

This contains everything you need to run your app locally.

View your app in AI Studio: https://ai.studio/apps/drive/19v6lMOKrwyS8J7NIFdcEsJlPKW9vtOgI

## Run Locally (Docker - Recommended)

1.  Set the `OPENAI_API_KEY` in `.env`:
    `cp .env.example .env`
    (Then edit `.env` with your key)

2.  Run with Docker Compose:
    `docker-compose up --build`

3.  Open http://localhost:8000

## Run Locally (Manual)

**Prerequisites:** Node.js, Python 3.10+

1.  **Backend**:
    ```bash
    cd backend
    pip install -r requirements.txt
    uvicorn main:app --reload
    ```

2.  **Frontend**:
    ```bash
    npm install
    npm run dev
    ```

Note: The backend requires `OPENAI_API_KEY` for OCR fallback and advanced categorization.
