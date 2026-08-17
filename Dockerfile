FROM python:3.12-slim

WORKDIR /app

# System dependencies required by Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies and Playwright browser in one layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium --with-deps

# Copy application source
COPY . .

# Placeholder data directory — the named volume shadows this at runtime
RUN mkdir -p data

VOLUME ["/app/data"]

ARG WEB_PORT=8080
EXPOSE $WEB_PORT

CMD ["python", "main.py"]
