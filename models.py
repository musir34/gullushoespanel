from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.ext.declarative import declarative_base
import uuid

db = SQLAlchemy()
Base = declarative_base()

#Sipariş Fişi Tablosu
class SiparisFisiDetay(db.Model):
    __tablename__ = 'siparis_fisi_detay'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    siparis_id = db.Column(db.Integer, db.ForeignKey('siparis_fisi.siparis_id'), nullable=False)
    urun_model_kodu = db.Column(db.String(50), nullable=False)
    renk = db.Column(db.String(20), nullable=False)
    beden_35 = db.Column(db.Integer, nullable=False, default=0)
    beden_36 = db.Column(db.Integer, nullable=False, default=0)
    beden_37 = db.Column(db.Integer, nullable=False, default=0)
    beden_38 = db.Column(db.Integer, nullable=False, default=0)
    beden_39 = db.Column(db.Integer, nullable=False, default=0)
    beden_40 = db.Column(db.Integer, nullable=False, default=0)
    beden_41 = db.Column(db.Integer, nullable=False, default=0)
    cift_basi_fiyat = db.Column(db.Numeric(10,2), nullable=False)
    toplam_adet = db.Column(db.Integer, nullable=False)
    toplam_fiyat = db.Column(db.Numeric(10,2), nullable=False)
    image_url = db.Column(db.String(255))

class SiparisFisi(db.Model):
    __tablename__ = 'siparis_fisi'

    siparis_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    detaylar = db.relationship('SiparisFisiDetay', backref='fis', lazy=True, cascade="all, delete-orphan")
    toplam_fiyat = db.Column(db.Numeric(10,2), nullable=False, default=0)
    

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