# Stage 1: Build React Frontend
FROM node:18-alpine as frontend_build
WORKDIR /app/frontend

# Copy frontend dependency files
COPY package.json package-lock.json ./
RUN npm ci

# Copy frontend source code
COPY . .

# Build the frontend (outputs to /app/frontend/dist)
RUN npm run build

# Stage 2: Python Backend Runtime
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend requirements
COPY backend/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend /app/backend

# Copy built frontend assets from Stage 1
COPY --from=frontend_build /app/frontend/dist /app/dist

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
