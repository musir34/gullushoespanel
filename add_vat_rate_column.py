
import os
import psycopg2
from logger_config import app_logger

# Veritabanı bağlantı bilgileri
DB_URL = os.environ.get('DATABASE_URL')

def add_vat_rate_column():
    """Veritabanı tablosuna vat_rate sütunu ekler"""
    try:
        app_logger.info("vat_rate sütunu ekleme işlemi başlatılıyor...")
        
        # Veritabanına bağlan
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        
        # Sütunun var olup olmadığını kontrol et
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='products' AND column_name='vat_rate'")
        result = cursor.fetchone()
        
        if not result:
            app_logger.info("vat_rate sütunu ekleniyor...")
            # Sütun yoksa ekle
            cursor.execute("ALTER TABLE products ADD COLUMN vat_rate FLOAT DEFAULT 0.18")
            conn.commit()
            app_logger.info("vat_rate sütunu başarıyla eklendi.")
        else:
            app_logger.info("vat_rate sütunu zaten mevcut.")
            
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        app_logger.error(f"vat_rate sütunu eklenirken hata: {str(e)}")
        return False

if __name__ == "__main__":
    add_vat_rate_column()
