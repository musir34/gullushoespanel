
import os
from sqlalchemy import create_engine, text
from models import db
from app import app

def add_category_name_column():
    """
    Veritabanındaki products tablosuna category_name sütununu ekler
    """
    try:
        with app.app_context():
            # Veritabanı bağlantısı al
            engine = db.engine

            # Sütunun mevcut olup olmadığını kontrol et
            inspect_query = text("SELECT column_name FROM information_schema.columns WHERE table_name='products' AND column_name='category_name'")
            result = engine.execute(inspect_query).fetchall()
            
            if not result:
                # Sütun mevcut değilse ekle
                print("'category_name' sütunu ekleniyor...")
                alter_table_query = text("ALTER TABLE products ADD COLUMN category_name VARCHAR(255)")
                engine.execute(alter_table_query)
                print("'category_name' sütunu başarıyla eklendi!")
            else:
                print("'category_name' sütunu zaten mevcut.")
                
            return True
    except Exception as e:
        print(f"Hata oluştu: {e}")
        return False

if __name__ == "__main__":
    add_category_name_column()
