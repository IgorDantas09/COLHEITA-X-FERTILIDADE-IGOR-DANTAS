FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gdal-bin \
       libgdal-dev \
       libgeos-dev \
       libproj-dev \
       gcc \
       g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY services/geo-worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY libs/agrogeo/agrogeo /app/agrogeo
COPY services/geo-worker/app /app/app

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
