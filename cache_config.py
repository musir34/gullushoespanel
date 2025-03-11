
import os
import logging
import redis

# Loglama ayarları
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis bağlantısını yeniden nasıl kuracağımızı belirleyen değişken
USE_MOCK_REDIS = True

# Redis bağlantı ayarları
try:
    if USE_MOCK_REDIS:
        # DummyRedis sınıfı - Redis olmadan çalışabilmek için
        class DummyRedis:
            def __init__(self):
                self.storage = {}
                logger.info("Mock Redis başlatıldı - Önbellek bellek içinde çalışıyor")
            
            def get(self, key):
                if key in self.storage:
                    logger.debug(f"Mock Redis: '{key}' anahtarı önbellekten alındı")
                    return self.storage[key]
                logger.debug(f"Mock Redis: '{key}' anahtarı önbellekte bulunamadı")
                return None
            
            def set(self, key, value, **kwargs):
                self.storage[key] = value
                logger.debug(f"Mock Redis: '{key}' anahtarı önbelleğe kaydedildi")
                return True
            
            def setex(self, key, time, value):
                self.storage[key] = value
                logger.debug(f"Mock Redis: '{key}' anahtarı {time} saniyelik süreyle önbelleğe kaydedildi")
                return True
            
            def delete(self, *keys):
                for key in keys:
                    if key in self.storage:
                        del self.storage[key]
                        logger.debug(f"Mock Redis: '{key}' anahtarı önbellekten silindi")
                return True
            
            def ping(self):
                return True
        
        redis_client = DummyRedis()
        redis_active = True
        logger.info("Mock Redis aktif - Önbellek bellek içinde çalışıyor")
    else:
        # Gerçek Redis istemcisi
        redis_client = redis.Redis(
            host='127.0.0.1',
            port=6379,
            db=0,
            socket_connect_timeout=1,
            socket_timeout=1,
            retry_on_timeout=False
        )
        # Bağlantıyı test et
        redis_client.ping()
        redis_active = True
        logger.info("Redis bağlantısı başarıyla kuruldu.")
except Exception as e:
    logger.warning(f"Redis bağlantısı kurulamadı, bellek içi önbellek kullanılıyor: {str(e)}")
    # Bağlantı başarısız olduğunda DummyRedis kullan
    class DummyRedis:
        def __init__(self):
            self.storage = {}
            logger.info("Fallback Mock Redis başlatıldı")
        
        def get(self, key):
            if key in self.storage:
                return self.storage[key]
            return None
        
        def set(self, key, value, **kwargs):
            self.storage[key] = value
            return True
        
        def setex(self, key, time, value):
            self.storage[key] = value
            return True
        
        def delete(self, *keys):
            for key in keys:
                if key in self.storage:
                    del self.storage[key]
            return True
        
        def ping(self):
            return True

    redis_client = DummyRedis()
    redis_active = True  # Sahte Redis aktif

# Önbellek süreleri (saniye)
CACHE_TIMES = {
    'product_list': 3600,    # 1 saat
    'order_list': 300,       # 5 dakika
    'sales_data': 1800,      # 30 dakika
    'profit_analysis': 1200  # 20 dakika
}
