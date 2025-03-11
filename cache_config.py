
import redis
import os

# Redis bağlantı ayarları
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Redis istemcisini oluştur
try:
    redis_client = redis.from_url(REDIS_URL)
    redis_client.ping()  # Bağlantıyı test et
    print("Redis bağlantısı başarıyla kuruldu")
except redis.ConnectionError:
    print("Redis bağlantısı kurulamadı, sahte redis istemcisi kullanılıyor")
    
    # Redis bağlantısı yoksa sahte bir redis istemcisi oluştur
    class FakeRedis:
        def __init__(self):
            self.data = {}
            
        def get(self, key):
            return self.data.get(key)
            
        def setex(self, key, time, value):
            self.data[key] = value
            return True
            
        def delete(self, key):
            if key in self.data:
                del self.data[key]
            return True
    
    redis_client = FakeRedis()


import os
from redis import Redis

redis_client = Redis(
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=int(os.environ.get('REDIS_PORT', 6379)),
    db=0,
    decode_responses=True
)

# Önbellek süreleri (saniye)
CACHE_TIMES = {
    'orders': 300,  # 5 dakika
    'products': 600,  # 10 dakika
    'user_data': 1800  # 30 dakika
}
