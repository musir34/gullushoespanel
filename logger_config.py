
import logging
import logging.handlers
import os

def setup_logger(name, log_file, level=logging.INFO):
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # Performans için buffer size artırılıyor
    handler = logging.handlers.RotatingFileHandler(
        log_file, 
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3,
        buffering=8192
    )
    
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10000000, backupCount=5
    )
    handler.setFormatter(formatter)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)
    
    return logger

# Ana loglayıcıları oluştur
app_logger = setup_logger('app', 'logs/app.log')
order_logger = setup_logger('orders', 'logs/orders.log')
api_logger = setup_logger('api', 'logs/api.log')
