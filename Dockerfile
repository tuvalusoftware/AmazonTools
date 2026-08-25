FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies, then Chromium + the system libs it needs
# (--with-deps resolves the same libnss3/libatk/... set apt would need
# manually, so there's no separate apt-get step to keep in sync).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Copy application source
COPY . .

# Placeholder data directory — the named volume shadows this at runtime
RUN mkdir -p data

VOLUME ["/app/data"]

ARG WEB_PORT=8080
EXPOSE $WEB_PORT

CMD ["python", "main.py"]
