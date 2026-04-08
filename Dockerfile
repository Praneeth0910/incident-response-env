FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY README.md .
RUN pip install --no-cache-dir .

COPY . .

RUN chmod +x start.sh

EXPOSE 7860

CMD ["./start.sh"]