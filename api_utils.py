
import logging
from functools import wraps
from lock_manager import LockManager

logger = logging.getLogger(__name__)

def with_resource_lock(resource_type, resource_id_func):
    """
    Belirli bir kaynağı kilitleyen dekoratör.
    
    Args:
        resource_type: Kaynak tipi (örn: "product", "order")
        resource_id_func: Kaynağın ID'sini döndüren fonksiyon
        
    Kullanım:
        @with_resource_lock("product", lambda req: req.args.get("barcode"))
        def update_product(request):
            # İşlemler...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Resource ID'yi belirle
            if 'request' in kwargs:
                resource_id = resource_id_func(kwargs['request'])
            else:
                # İlk argümanın request olduğunu varsayalım
                resource_id = resource_id_func(args[0]) if args else None
                
            if not resource_id:
                logger.warning(f"Kaynak ID'si belirlenemedi: {resource_type}")
                return func(*args, **kwargs)
                
            lock_key = f"{resource_type}_{resource_id}"
            
            # Kilidi al
            acquired = LockManager.acquire_lock(lock_key, timeout=30)
            if not acquired:
                logger.error(f"Kilit alınamadı: {lock_key}")
                raise Exception(f"Sistem yoğun, lütfen tekrar deneyin. Kaynak: {resource_type}_{resource_id}")
                
            try:
                # Asıl fonksiyonu çalıştır
                return func(*args, **kwargs)
            finally:
                # Kilidi serbest bırak
                LockManager.release_lock(lock_key)
                
        return wrapper
    return decorator

# API isteklerini sıraya koyan fonksiyon
async def queue_api_request(request_func, *args, **kwargs):
    """
    API isteklerini sıraya koyarak çalıştırır.
    Eş zamanlı istekleri önler.
    
    Args:
        request_func: Asıl API isteğini yapan fonksiyon
        
    Returns:
        API isteğinin sonucu
    """
    # API istekleri için genel bir kilit
    lock_acquired = LockManager.acquire_lock("api_requests", timeout=60)
    if not lock_acquired:
        logger.error("API istekleri için kilit alınamadı")
        raise Exception("Sistem şu anda çok yoğun, lütfen biraz bekleyip tekrar deneyin.")
        
    try:
        # Asıl API isteğini yap
        return await request_func(*args, **kwargs)
    finally:
        # Kilidi serbest bırak
        LockManager.release_lock("api_requests")
