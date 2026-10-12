FROM python:3.11-slim

# Temel paketler
WORKDIR /app

# Bağımlılıkları yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodlarını kopyala
COPY . .

# Veri klasörü (SQLite veritabanı ve önbellek için kalıcı alan)
VOLUME ["/app/veri"]

# Port
EXPOSE 8795

# Ağ modunda başlat, tarayıcı açma
CMD ["python", "sunucu.py", "--port", "8795", "--ag", "--acma"]
