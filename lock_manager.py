
import threading
import time
import logging

logger = logging.getLogger(__name__)

class LockManager:
    """
    Kritik kaynaklar için kilit yönetimi sağlayan sınıf.
    Aynı anda yapılan API isteklerinde ve veritabanı işlemlerinde
    tutarlılığı korumak için kullanılır.
    """
    _locks = {}
    _lock = threading.RLock()  # Ana kilit

    @classmethod
    def acquire_lock(cls, resource_id, timeout=60):
        """
        Belirli bir kaynak için kilit alır.
        
        Args:
            resource_id: Kilitlenecek kaynağın ID'si (örn: "product_update", "order_123")
            timeout: Azami bekleme süresi (saniye)
            
        Returns:
            bool: Kilit başarılı şekilde alındıysa True
        """
        with cls._lock:
            if resource_id not in cls._locks:
                cls._locks[resource_id] = threading.Lock()
                
        lock = cls._locks[resource_id]
        acquired = lock.acquire(blocking=True, timeout=timeout)
        
        if acquired:
            logger.debug(f"Kilit alındı: {resource_id}")
        else:
            logger.warning(f"Kilit alınamadı (timeout): {resource_id}")
            
        return acquired

    @classmethod
    def release_lock(cls, resource_id):
        """
        Kaynağın kilidini serbest bırakır.
        
        Args:
            resource_id: Kilidi serbest bırakılacak kaynağın ID'si
        """
        with cls._lock:
            if resource_id in cls._locks:
                try:
                    cls._locks[resource_id].release()
                    logger.debug(f"Kilit serbest bırakıldı: {resource_id}")
                except RuntimeError:
                    logger.error(f"Kilit zaten serbest: {resource_id}")
