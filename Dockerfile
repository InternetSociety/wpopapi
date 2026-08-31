FROM python:3.14-slim

# Install system dependencies for GDAL/Rasterio
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY docker-entrypoint.sh /usr/local/bin/wpopapi-entrypoint
RUN chmod +x /usr/local/bin/wpopapi-entrypoint

RUN mkdir -p /app/data/tiles

VOLUME /app/data

EXPOSE 8002

ENTRYPOINT ["/usr/local/bin/wpopapi-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
