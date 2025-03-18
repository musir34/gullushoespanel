
from models import db, Order, SiparisIstatistikleri, Product
from sqlalchemy import func
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def hesapla_istatistikler(baslangic_tarihi, bitis_tarihi, periyot_tipi):
    """Belirli bir periyot için satış istatistiklerini hesaplar"""
    try:
        # Satış verileri
        satis_verileri = db.session.query(
            func.sum(Order.amount).label('toplam_ciro'),
            func.count(Order.id).label('toplam_siparis')
        ).filter(
            Order.order_date.between(baslangic_tarihi, bitis_tarihi),
            Order.status != 'Cancelled'
        ).first()

        # Maliyet hesaplama
        maliyet_verileri = db.session.query(
            func.sum(Product.cost_try * Order.quantity).label('toplam_maliyet')
        ).join(
            Order, Order.product_main_id == Product.product_main_id
        ).filter(
            Order.order_date.between(baslangic_tarihi, bitis_tarihi),
            Order.status != 'Cancelled'
        ).first()

        toplam_ciro = float(satis_verileri.toplam_ciro or 0)
        toplam_maliyet = float(maliyet_verileri.toplam_maliyet or 0)
        toplam_kar = toplam_ciro - toplam_maliyet
        kar_orani = (toplam_kar / toplam_ciro * 100) if toplam_ciro > 0 else 0

        # İstatistikleri kaydet
        istatistik = SiparisIstatistikleri(
            baslangic_tarihi=baslangic_tarihi,
            bitis_tarihi=bitis_tarihi,
            periyot_tipi=periyot_tipi,
            toplam_siparis=satis_verileri.toplam_siparis,
            toplam_ciro=toplam_ciro,
            toplam_maliyet=toplam_maliyet,
            toplam_kar=toplam_kar,
            kar_orani=kar_orani
        )
        
        db.session.add(istatistik)
        db.session.commit()
        
        logger.info(f"{periyot_tipi} istatistikler başarıyla kaydedildi")
        
    except Exception as e:
        logger.error(f"İstatistik hesaplama hatası: {e}")
        db.session.rollback()

def gunluk_istatistik_kontrolu():
    """Her gün çalıştırılacak kontrol fonksiyonu"""
    bugun = datetime.now()
    
    # Haftalık istatistik kontrolü (her pazartesi)
    if bugun.weekday() == 0:  # 0 = Pazartesi
        hafta_basi = bugun - timedelta(days=7)
        hesapla_istatistikler(hafta_basi, bugun, 'haftalik')
    
    # Aylık istatistik kontrolü (her ayın 1'i)
    if bugun.day == 1:
        ay_basi = bugun.replace(day=1) - timedelta(days=1)
        ay_basi = ay_basi.replace(day=1)
        hesapla_istatistikler(ay_basi, bugun, 'aylik')
