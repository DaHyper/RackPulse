FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md requirements.txt ./
COPY rackpulse ./rackpulse

RUN pip install --no-cache-dir -e ".[api]"

ENV RACKPULSE_CONFIG=/app/config.yaml

VOLUME ["/app/data", "/app/config.yaml"]

EXPOSE 8080

CMD ["rackpulse", "serve", "--host", "0.0.0.0", "--port", "8080"]
