from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Integer, Float, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

db = SQLAlchemy()
Base = declarative_base()

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

# Sipariş İstatistikleri Tablosu
class SiparisIstatistikleri(db.Model):
    __tablename__ = 'siparis_istatistikleri'
    
    id = db.Column(db.Integer, primary_key=True)
    baslangic_tarihi = db.Column(db.DateTime, nullable=False)
    bitis_tarihi = db.Column(db.DateTime, nullable=False)
    periyot_tipi = db.Column(db.String(10), nullable=False)  # 'haftalik' veya 'aylik'
    toplam_siparis = db.Column(db.Integer, default=0)
    toplam_ciro = db.Column(db.Float, default=0)
    toplam_maliyet = db.Column(db.Float, default=0)
    toplam_kar = db.Column(db.Float, default=0)
    kar_orani = db.Column(db.Float, default=0)
    olusturma_tarihi = db.Column(db.DateTime, default=datetime.utcnow)

# Sipariş Komisyon Tablosu
class SiparisKomisyon(db.Model):
    __tablename__ = 'siparis_komisyon'
    
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String, db.ForeignKey('orders.order_number'))
    product_barcode = db.Column(db.String)
    komisyon_orani = db.Column(db.Float)
    komisyon_tutari = db.Column(db.Float)
    platform_komisyonu = db.Column(db.Float)
    kargo_komisyonu = db.Column(db.Float)
    olusturma_tarihi = db.Column(db.DateTime, default=datetime.utcnow)

# Sipariş Modeli
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
    quantity = db.Column(db.Integer)
    delivery_date = db.Column(db.DateTime)

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
        self.cost_usd = cost_try

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