from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Integer, Float, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

db = SQLAlchemy()
Base = declarative_base()

class Shipment(db.Model):
    __tablename__ = 'shipments'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
    shipping_cost = db.Column(db.Float, nullable=False)
    shipping_provider = db.Column(db.String(100))
    date_shipped = db.Column(db.DateTime, default=datetime.utcnow)

class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    expense_type = db.Column(db.String(100))
    description = db.Column(db.String(255))
    amount = db.Column(db.Float, nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)



class ExcelUpload(db.Model):
    __tablename__ = 'excel_uploads'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ExcelUpload filename={self.filename}, upload_time={self.upload_time}>"

# Sipariş Fişi
class SiparisFisi(db.Model):
    __tablename__ = 'siparis_fisi'

    siparis_id = db.Column(db.Integer, primary_key=True)
    urun_model_kodu = db.Column(db.String(255))
    renk = db.Column(db.String(100))
    kalemler_json = db.Column(db.Text, default='[]')  # Her renk için ayrı kayıt

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


# İade siparişleri (Base kullanıyor!)
class ReturnOrder(Base):
    __tablename__ = 'return_orders'
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number = Column(String)
    return_request_number = Column(String)
    status = Column(String)
    return_date = Column(DateTime)
    process_date = Column(DateTime)  # İşlem tarihi
    customer_first_name = Column(String)
    customer_last_name = Column(String)
    cargo_tracking_number = Column(String)
    cargo_provider_name = Column(String)
    cargo_sender_number = Column(String)
    cargo_tracking_link = Column(String)
    processed_by = Column(String)  # İşlemi yapan kullanıcı
    return_reason = Column(String)  # İade nedeni (Beden/Numara Uyumsuzluğu, vs.)
    customer_explanation = Column(String)  # Müşteri açıklaması
    return_category = Column(String)  # İade kategorisi (Ürün Kaynaklı, Müşteri Kaynaklı, vs.)
    notes = Column(String)  # Ek notlar
    approval_reason = Column(String)  # Onay/red nedeni
    refund_amount = Column(Float)  # İade edilecek tutar

# İade ürünleri (Base kullanıyor!)
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
    claim_line_item_id = Column(String)
    product_condition = Column(String)  # Ürün durumu (Hasarlı, Kullanılmış, Yeni gibi)
    damage_description = Column(String)  # Hasar açıklaması
    inspection_notes = Column(String)  # İnceleme notları
    return_to_stock = Column(Boolean, default=False)  # Stoğa geri alınacak mı?


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

#Analiz ve hesaplar için kullanılacak tablo 
class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    product_barcode = db.Column(db.String, db.ForeignKey('products.barcode'))
    product_name = db.Column(db.String)
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float)
    unit_cost = db.Column(db.Float)
    commission = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order = db.relationship('Order', backref=db.backref('items', lazy=True))
    product = db.relationship('Product')


# models.py (veya sizin kullandığınız modele ekleyin)

# Temel sipariş modeli - tüm statüler için ortak alanlar
class OrderBase(db.Model):
    __abstract__ = True
    
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String, index=True)
    order_date = db.Column(db.DateTime, index=True)
    merchant_sku = db.Column(db.String)
    product_barcode = db.Column(db.String)
    original_product_barcode = db.Column(db.String)
    line_id = db.Column(db.String)
    match_status = db.Column(db.String)
    customer_name = db.Column(db.String)
    customer_surname = db.Column(db.String)
    customer_address = db.Column(db.Text)
    shipping_barcode = db.Column(db.String)
    product_name = db.Column(db.String)
    product_code = db.Column(db.String)
    amount = db.Column(db.Float)
    discount = db.Column(db.Float, default=0.0)
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
    details = db.Column(db.Text)
    quantity = db.Column(db.Integer)
    commission = db.Column(db.Float, default=0.0)
    product_cost_total = db.Column(db.Float, default=0.0)
    
    # Mevcut sisteme uyumluluk için status alanı (eski uygulamalar için)
    status = db.Column(db.String)

# Yeni sipariş tablosu (Created)
class OrderCreated(OrderBase):
    __tablename__ = 'orders_created'
    
    # Bu statüye özel alanlar eklenebilir
    creation_time = db.Column(db.DateTime, default=datetime.utcnow)

# İşleme alınan sipariş tablosu (Picking)
class OrderPicking(OrderBase):
    __tablename__ = 'orders_picking'
    
    # Bu statüye özel alanlar
    picking_start_time = db.Column(db.DateTime, default=datetime.utcnow)
    picked_by = db.Column(db.String)
    
# Kargodaki sipariş tablosu (Shipped)
class OrderShipped(OrderBase):
    __tablename__ = 'orders_shipped'
    
    # Bu statüye özel alanlar
    shipping_time = db.Column(db.DateTime, default=datetime.utcnow)
    tracking_updated = db.Column(db.Boolean, default=False)

# Teslim edilen sipariş tablosu (Delivered)
class OrderDelivered(OrderBase):
    __tablename__ = 'orders_delivered'
    
    # Bu statüye özel alanlar
    delivery_date = db.Column(db.DateTime)
    delivery_confirmed = db.Column(db.Boolean, default=False)
    
# İptal edilen sipariş tablosu (Cancelled)
class OrderCancelled(OrderBase):
    __tablename__ = 'orders_cancelled'
    
    # Bu statüye özel alanlar
    cancellation_date = db.Column(db.DateTime, default=datetime.utcnow)
    cancellation_reason = db.Column(db.String)
    
# Arşivlenen sipariş tablosu (Archived)
class OrderArchived(OrderBase):
    __tablename__ = 'orders_archived'
    
    # Bu statüye özel alanlar
    archive_date = db.Column(db.DateTime, default=datetime.utcnow)
    archive_reason = db.Column(db.String)

# Geriye dönük uyumluluk için mevcut sipariş tablosunu da tutalım
class Order(db.Model):
    __tablename__ = 'orders'
    __table_args__ = (
        db.Index('idx_order_number', 'order_number'),
        db.Index('idx_status', 'status'),
        db.Index('idx_order_date', 'order_date'),
    )

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
    discount = db.Column(db.Float, default=0.0)
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
    details = db.Column(db.Text)
    archive_date = db.Column(db.DateTime)
    archive_reason = db.Column(db.String)
    quantity = db.Column(db.Integer)
    delivery_date = db.Column(db.DateTime)
    commission = db.Column(db.Float, default=0.0)
    product_cost_total = db.Column(db.Float, default=0.0)




class ProductArchive(db.Model):
    __tablename__ = 'product_archive'

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
    archive_date = db.Column(db.DateTime, default=datetime.utcnow)


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
    cost_usd = db.Column(db.Float, default=0.0)  # Maliyet (USD cinsinden)
    cost_date = db.Column(db.DateTime)  # Maliyet girişi tarihi
    cost_try = db.Column(db.Float, default=0) #tl karşılığı

    def __init__(self, barcode, original_product_barcode, title, product_main_id, 
                 quantity, images, variants, size, color, archived, locked, on_sale,
                 reject_reason, sale_price, list_price, currency_type, cost_usd=0.0, cost_try=0.0, cost_date=None):
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
        self.cost_usd = cost_usd
        self.cost_date = cost_date
        self.cost_try = cost_try  # <- Doğrusu budur!


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
class YeniSiparis(db.Model):
    __tablename__ = 'yeni_siparisler'

    id = db.Column(db.Integer, primary_key=True)
    siparis_no = db.Column(db.String, unique=True)
    musteri_adi = db.Column(db.String)
    musteri_soyadi = db.Column(db.String)
    musteri_adres = db.Column(db.Text)
    musteri_telefon = db.Column(db.String)
    siparis_tarihi = db.Column(db.DateTime, default=datetime.utcnow)
    toplam_tutar = db.Column(db.Float)
    durum = db.Column(db.String, default='Yeni')
    notlar = db.Column(db.Text)

class SiparisUrun(db.Model):
    __tablename__ = 'siparis_urunler'

    id = db.Column(db.Integer, primary_key=True)
    siparis_id = db.Column(db.Integer, db.ForeignKey('yeni_siparisler.id'))
    urun_barkod = db.Column(db.String)
    urun_adi = db.Column(db.String)
    adet = db.Column(db.Integer)
    birim_fiyat = db.Column(db.Float)
    toplam_fiyat = db.Column(db.Float)
    renk = db.Column(db.String)
    beden = db.Column(db.String)
    urun_gorseli = db.Column(db.String)

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

# Veritabanı modelleri burada tanımlanacak

class Return(db.Model):
    """İade bilgilerini tutan tablo"""
    __tablename__ = 'returns'

    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.String(50), unique=True, nullable=False)
    order_number = db.Column(db.String(50))
    order_line_id = db.Column(db.String(50))
    status = db.Column(db.String(50))
    reason = db.Column(db.String(255))
    barcode = db.Column(db.String(100))
    product_name = db.Column(db.String(255))
    product_color = db.Column(db.String(50))
    product_size = db.Column(db.String(50))
    quantity = db.Column(db.Integer, default=0)
    customer_name = db.Column(db.String(100))
    address = db.Column(db.Text)
    create_date = db.Column(db.DateTime)
    last_modified_date = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    details = db.Column(db.Text)  # İade ile ilgili tüm detaylar JSON olarak saklanır

    def __repr__(self):
        return f"<Return {self.claim_id}>"
class UserLog(db.Model):
    __tablename__ = 'user_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))
    page_url = db.Column(db.String(255))
    
    user = db.relationship('User', backref=db.backref('logs', lazy=True))
