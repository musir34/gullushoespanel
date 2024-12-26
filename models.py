from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.ext.declarative import declarative_base
import uuid


db = SQLAlchemy()
Base = declarative_base()

class DailyStats(db.Model):
    __tablename__ = 'daily_stats'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    order_count = db.Column(db.Integer, default=0)
    product_stats = db.Column(db.JSON)  # En çok üretilen ürünlerin istatistikleri
    color_stats = db.Column(db.JSON)    # Renk dağılımı istatistikleri
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Sipariş Fişi
class SiparisFisi(db.Model):
    __tablename__ = 'siparis_fisi'

    siparis_id = db.Column(db.Integer, primary_key=True)
    urun_model_kodu = db.Column(db.String(255))
    renk = db.Column(db.String(100))

    # Yeni barkod alanları
    barkod_35 = db.Column(db.String(100))
    barkod_36 = db.Column(db.String(100))
    barkod_37 = db.Column(db.String(100))
    barkod_38 = db.Column(db.String(100))
    barkod_39 = db.Column(db.String(100))
    barkod_40 = db.Column(db.String(100))
    barkod_41 = db.Column(db.String(100))

    # Beden alanları
    beden_35 = db.Column(db.Integer, default=0)
    beden_36 = db.Column(db.Integer, default=0)
    beden_37 = db.Column(db.Integer, default=0)
    beden_38 = db.Column(db.Integer, default=0)
    beden_39 = db.Column(db.Integer, default=0)
    beden_40 = db.Column(db.Integer, default=0)
    beden_41 = db.Column(db.Integer, default=0)

    # Fiyat / adet vb.
    cift_basi_fiyat = db.Column(db.Float, default=0)
    toplam_adet = db.Column(db.Integer, default=0)
    toplam_fiyat = db.Column(db.Float, default=0)

    # Tarihler
    created_date = db.Column(db.DateTime, default=None)
    print_date = db.Column(db.DateTime, default=None)

    # Teslim kayıtları (JSON string)
    teslim_kayitlari = db.Column(db.Text, default=None)
    kalan_adet = db.Column(db.Integer, default=0)

    # Ürün görseli
    image_url = db.Column(db.String)

    def __init__(
        self,
        urun_model_kodu,
        renk,
        barkod_35,
        barkod_36,
        barkod_37,
        barkod_38,
        barkod_39,
        barkod_40,
        barkod_41,
        beden_35,
        beden_36,
        beden_37,
        beden_38,
        beden_39,
        beden_40,
        beden_41,
        cift_basi_fiyat,
        toplam_adet,
        toplam_fiyat,
        image_url
    ):
        # Ürün bilgileri
        self.urun_model_kodu = urun_model_kodu
        self.renk = renk

        # Barkodlar
        self.barkod_35 = barkod_35
        self.barkod_36 = barkod_36
        self.barkod_37 = barkod_37
        self.barkod_38 = barkod_38
        self.barkod_39 = barkod_39
        self.barkod_40 = barkod_40
        self.barkod_41 = barkod_41

        # Beden adetleri
        self.beden_35 = beden_35
        self.beden_36 = beden_36
        self.beden_37 = beden_37
        self.beden_38 = beden_38
        self.beden_39 = beden_39
        self.beden_40 = beden_40
        self.beden_41 = beden_41

        # Fiyat
        self.cift_basi_fiyat = cift_basi_fiyat
        self.toplam_adet = toplam_adet
        self.toplam_fiyat = toplam_fiyat

        # Görsel
        self.image_url = image_url

    

# İade siparişleri için veritabanı modeli 
class ReturnOrder(Base): 
    __tablename__ = 'return_orders' 
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number = Column(String) 
    return_request_number = Column(String) 
    status = Column(String) 
    return_date = Column(DateTime) 
    customer_first_name = Column(String) 
    customer_last_name = Column(String)
    cargo_tracking_number = Column(String)
    cargo_provider_name = Column(String)
    cargo_sender_number = Column(String)
    cargo_tracking_link = Column(String)

# İade ürünleri için veritabanı modeli 
class ReturnProduct(Base):
    __tablename__ = 'return_products'
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    return_order_id = Column(PG_UUID(as_uuid=True), ForeignKey('return_orders.id'))
    product_id = Column(String)
    barcode = Column(String)
    model_number = Column(String)
    size = Column(String)
    color = Column(String)
    quantity = Column(Integer)
    reason = Column(String)
    claim_line_item_id = Column(String)  # Yeni alan eklendi



# Kullanıcı Modeli
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(150), nullable=False)
    last_name = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), default='worker')
    status = db.Column(db.String(50), default='pending')
    totp_secret = db.Column(db.String(16))  # 16 karakterlik base32 string
    totp_confirmed = db.Column(db.Boolean, default=False)

# Modellerin tanımlanması
class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String)
    order_date = db.Column(db.DateTime)
    merchant_sku = db.Column(db.String)
    product_barcode = db.Column(db.String)
    original_product_barcode = db.Column(db.String)
    status = db.Column(db.String)
    line_id = db.Column(db.String)
    match_status = db.Column(db.String)
    customer_name = db.Column(db.String)
    customer_surname = db.Column(db.String)
    customer_address = db.Column(db.Text)
    shipping_barcode = db.Column(db.String)
    product_name = db.Column(db.String)
    product_code = db.Column(db.String)
    amount = db.Column(db.Float)
    discount = db.Column(db.Float)
    currency_code = db.Column(db.String)
    vat_base_amount = db.Column(db.Float)
    package_number = db.Column(db.String)
    stockCode = db.Column(db.String)
    estimated_delivery_start = db.Column(db.DateTime)
    images = db.Column(db.String)
    product_model_code = db.Column(db.String)
    estimated_delivery_end = db.Column(db.DateTime)
    origin_shipment_date = db.Column(db.DateTime)
    product_size = db.Column(db.String)
    product_main_id = db.Column(db.String)
    cargo_provider_name = db.Column(db.String)
    agreed_delivery_date = db.Column(db.DateTime)
    product_color = db.Column(db.String)
    cargo_tracking_link = db.Column(db.String)
    shipment_package_id = db.Column(db.String)
    details = db.Column(db.Text)  # JSON formatında saklanacak
    archive_date = db.Column(db.DateTime)
    archive_reason = db.Column(db.String)
    




class Product(db.Model):
    __tablename__ = 'products'

    barcode = db.Column(db.String, primary_key=True)
    original_product_barcode = db.Column(db.String)
    title = db.Column(db.String)
    hidden = db.Column(db.Boolean, default=False)
    product_main_id = db.Column(db.String)
    quantity = db.Column(db.Integer)
    images = db.Column(db.String)
    variants = db.Column(db.String)
    size = db.Column(db.String)
    color = db.Column(db.String)
    archived = db.Column(db.Boolean)
    locked = db.Column(db.Boolean)
    on_sale = db.Column(db.Boolean)
    reject_reason = db.Column(db.String)
    sale_price = db.Column(db.Float)
    list_price = db.Column(db.Float)
    currency_type = db.Column(db.String)

    def __init__(self, barcode, original_product_barcode, title, product_main_id, 
                 quantity, images, variants, size, color, archived, locked, on_sale,
                 reject_reason, sale_price, list_price, currency_type):
        self.barcode = barcode
        self.original_product_barcode = original_product_barcode
        self.title = title
        self.product_main_id = product_main_id
        self.quantity = quantity
        self.images = images
        self.variants = variants
        self.size = size
        self.color = color
        self.archived = archived
        self.locked = locked
        self.on_sale = on_sale
        self.reject_reason = reject_reason
        self.sale_price = sale_price
        self.list_price = list_price
        self.currency_type = currency_type




# Arşiv Modeli
class Archive(db.Model):
    __tablename__ = 'archive'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String)
    order_date = db.Column(db.DateTime)
    merchant_sku = db.Column(db.String)
    product_barcode = db.Column(db.String)
    original_product_barcode = db.Column(db.String)
    status = db.Column(db.String)
    line_id = db.Column(db.String)
    match_status = db.Column(db.String)
    customer_name = db.Column(db.String)
    customer_surname = db.Column(db.String)
    customer_address = db.Column(db.Text)
    shipping_barcode = db.Column(db.String)
    product_name = db.Column(db.String)
    product_code = db.Column(db.String)
    amount = db.Column(db.Float)
    discount = db.Column(db.Float)
    currency_code = db.Column(db.String)
    vat_base_amount = db.Column(db.Float)
    package_number = db.Column(db.String)
    stockCode = db.Column(db.String)
    estimated_delivery_start = db.Column(db.DateTime)
    images = db.Column(db.String)
    product_model_code = db.Column(db.String)
    estimated_delivery_end = db.Column(db.DateTime)
    origin_shipment_date = db.Column(db.DateTime)
    product_size = db.Column(db.String)
    product_main_id = db.Column(db.String)
    cargo_provider_name = db.Column(db.String)
    agreed_delivery_date = db.Column(db.DateTime)
    product_color = db.Column(db.String)
    cargo_tracking_link = db.Column(db.String)
    shipment_package_id = db.Column(db.String)
    details = db.Column(db.Text)  # JSON formatında saklanacak
    archive_date = db.Column(db.DateTime, default=datetime.utcnow)
    archive_reason = db.Column(db.String)

    def __repr__(self):
        return f"<Archive {self.order_number}>"
        

# Değişim Modeli
class Degisim(db.Model):
    __tablename__ = 'degisim'

    degisim_no = db.Column(db.String, primary_key=True)
    siparis_no = db.Column(db.String)
    ad = db.Column(db.String)
    soyad = db.Column(db.String)
    adres = db.Column(db.Text)
    telefon_no = db.Column(db.String)
    urun_barkod = db.Column(db.String)
    urun_model_kodu = db.Column(db.String)
    urun_renk = db.Column(db.String)
    urun_beden = db.Column(db.String)
    degisim_tarihi = db.Column(db.DateTime, default=datetime.utcnow)
    degisim_durumu = db.Column(db.String)
    kargo_kodu = db.Column(db.String)
    degisim_nedeni = db.Column(db.String, nullable=True)

    def __repr__(self):
        return f"<Exchange {self.degisim_no}>"