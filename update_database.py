
import psycopg2
import os
from logger_config import app_logger

# Veritabanı bağlantı bilgilerini buraya ekleyin
DB_URL = os.environ.get('DATABASE_URL')

def add_category_name_column():
    """Veritabanı tablosuna category_name sütunu ekler"""
    try:
        app_logger.info("Veritabanı güncelleme işlemi başlatılıyor...")
        
        # Veritabanına bağlan
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        
        # Sütunun var olup olmadığını kontrol et
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='products' AND column_name='category_name'")
        result = cursor.fetchone()
        
        if not result:
            app_logger.info("category_name sütunu ekleniyor...")
            # Sütun yoksa ekle
            cursor.execute("ALTER TABLE products ADD COLUMN category_name VARCHAR(255)")
            conn.commit()
            app_logger.info("category_name sütunu başarıyla eklendi.")
        else:
            app_logger.info("category_name sütunu zaten mevcut.")
            
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        app_logger.error(f"Veritabanı güncellenirken hata: {str(e)}")
        return False

if __name__ == "__main__":
    add_category_name_column()
