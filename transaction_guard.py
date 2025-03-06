
import time
import logging
import threading
from functools import wraps
from flask import request, jsonify

logger = logging.getLogger(__name__)

# İşlem takibi için global değişkenler
_active_transactions = {}
_transaction_lock = threading.Lock()

def prevent_concurrent_transactions(transaction_type):
    """
    Aynı tipte işlemlerin eş zamanlı çalışmasını engelleyen dekoratör.
    
    Args:
        transaction_type: İşlem tipi (örn: "order_create", "stock_update")
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            client_ip = request.remote_addr
            transaction_key = f"{transaction_type}_{client_ip}"
            
            with _transaction_lock:
                # Aynı işlem tipinin zaten çalışıp çalışmadığını kontrol et
                current_time = time.time()
                if transaction_key in _active_transactions:
                    last_transaction_time = _active_transactions[transaction_key]
                    # Son 5 saniye içinde aynı işlem yapıldıysa engelle
                    if current_time - last_transaction_time < 5:
                        logger.warning(f"Eş zamanlı işlem engellendi: {transaction_key}")
                        return jsonify({
                            'success': False, 
                            'error': 'Çok hızlı işlem yapıyorsunuz. Lütfen biraz bekleyin.'
                        }), 429
                
                # İşlemi kaydet
                _active_transactions[transaction_key] = current_time
            
            try:
                # Asıl fonksiyonu çalıştır
                return func(*args, **kwargs)
            finally:
                # 5 saniyeden eski işlem kayıtlarını temizle
                with _transaction_lock:
                    for key in list(_active_transactions.keys()):
                        if current_time - _active_transactions[key] > 5:
                            del _active_transactions[key]
                
        return wrapper
    return decorator
