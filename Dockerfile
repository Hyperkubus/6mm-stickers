FROM python:3.12-slim-bookworm

# librsvg2-bin gives us rsvg-convert (used by sheets.py + preview.py); the
# fonts match what the generator's font stack expects so labels render the
# same way they do on a host install. Pinned to bookworm because the font
# package names are stable there.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        librsvg2-bin \
        fonts-firacode \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir flask==3.0.3 gunicorn==22.0.0

COPY . .

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", \
     "--chdir", "/app/webapp", "app:app"]
