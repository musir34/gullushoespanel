
import os
import logging
import redis

# Redis bağlantı ayarları - hata yönetimi eklenmiş
try:
    redis_client = redis.Redis(host='0.0.0.0', port=6379, db=0, socket_connect_timeout=2, socket_timeout=2)
    # Bağlantıyı test et
    redis_client.ping()
    redis_active = True
    logging.info("Redis bağlantısı başarıyla kuruldu.")
except Exception as e:
    logging.warning(f"Redis bağlantısı kurulamadı, önbellek devre dışı: {str(e)}")
    # Dummy Redis client
    class DummyRedis:
        def get(self, key):
            return None
        def set(self, key, value, **kwargs):
            pass
        def setex(self, key, time, value):
            pass
        def delete(self, *keys):
            pass
        def ping(self):
            return False

    redis_client = DummyRedis()
    redis_active = False

# Önbellek süreleri (saniye)
CACHE_TIMES = {
    'product_list': 3600,  # 1 saat
    'order_list': 300,     # 5 dakika
    'sales_data': 1800     # 30 dakika
}
