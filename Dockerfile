FROM python:3.11-slim

WORKDIR /app

# Sistem araçları ve derleme kütüphaneleri (curl_cffi ve lxml için)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Bağımlılıkları yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kaynak kodlarını kopyala
COPY . .

# Veri klasörü (SQLite veritabanı ve önbellek için kalıcı alan)
VOLUME ["/app/veri"]

# Web Platformu (8795) ve Kontrol Merkezi (8999) portları
EXPOSE 8795 8999

# Varsayılan başlangıç komutu (Docker Compose ile servis bazında özelleştirilebilir)
CMD ["python", "sunucu.py", "--port", "8795", "--ag", "--acma"]
