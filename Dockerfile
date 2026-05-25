FROM python:3.12-slim

WORKDIR /app

# Fonts needed for PNG rendering (Pillow does not bundle any).
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (cached as a separate layer from the source code).
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY backend/app /app/app
COPY frontend /app/frontend

# Layout inside the container:
#   /app/app         <- backend (FastAPI)
#   /app/frontend    <- frontend (single index.html)
# main.py's _find_frontend_dir() handles both this layout and the
# dev layout (backend/../frontend).

EXPOSE 8000

# Run uvicorn. Railway passes the port via $PORT;
# locally and as a fallback we use 8000.
# Shell form (not exec) is needed so ${PORT} gets interpolated.
CMD python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
