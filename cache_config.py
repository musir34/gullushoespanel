
import redis
import json
from functools import wraps
from datetime import datetime, timedelta

# Redis bağlantısı
redis_client = redis.Redis(host='localhost', port=6379, db=0)

def cache_result(expiration=3600):
    """
    Fonksiyon sonuçlarını önbelleğe alan decorator
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Önbellek anahtarı oluşturma
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Önbellekte veri kontrolü
            cached_data = redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
            
            # Eğer önbellekte yoksa, fonksiyonu çalıştır
            result = func(*args, **kwargs)
            
            # Sonucu önbelleğe kaydet
            redis_client.setex(
                cache_key,
                expiration,
                json.dumps(result, default=str)
            )
            
            return result
        return wrapper
    return decorator

def clear_cache_pattern(pattern):
    """
    Belirli bir desene uyan tüm önbellek girdilerini temizler
    """
    for key in redis_client.scan_iter(f"*{pattern}*"):
        redis_client.delete(key)
