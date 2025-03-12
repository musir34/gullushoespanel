
from flask import Blueprint, jsonify, render_template
from models import db, Order
from sqlalchemy import func

kar_maliyet_bp = Blueprint('kar_maliyet', __name__)

def hesapla_kar(order):
    """
    Sipariş için net kâr hesaplayan fonksiyon.
    Eğer ürünün dolar maliyeti varsa, onu kullanır.
    """
    satis_fiyati = order.amount or 0
    
    # Ürün maliyeti hesaplama (önce $ cinsinden maliyet kontrolü)
    urun_maliyeti = order.vat_base_amount or 0  # Varsayılan maliyet
    
    # Ürün barkodundan Product tablosunda maliyet bilgisi var mı kontrol et
    urun_barkodlari = order.product_barcode.split(', ') if order.product_barcode else []
    
    if urun_barkodlari:
        # Birincil barkodu kullan
        birincil_barkod = urun_barkodlari[0]
        # Product tablosundaki ürünü sorgula
        urun = db.session.query(Product).filter_by(barcode=birincil_barkod).first()
        
        if urun and urun.cost_usd:
            # Güncel dolar kurunu çekmek için bir fonksiyon eklenmeli
            # Şimdilik sabit bir kur kullanıyoruz (gerçek uygulamada API'den çekilmeli)
            dolar_kuru = 30.0  # Örnek kur (TL/USD)
            urun_maliyeti = urun.cost_usd * dolar_kuru
    
    komisyon_orani = 0.15  # Trendyol komisyonu (%15 varsayılan)
    komisyon_tutari = satis_fiyati * komisyon_orani
    kargo_ucreti = 30  # Ortalama bir değer, sipariş bazlı ayarlanabilir
    paketleme_maliyeti = 10  # Ortalama paketleme gideri
    kdv_orani = 0.18
    kdv = satis_fiyati * kdv_orani

    # Net kâr hesaplama
    net_kar = satis_fiyati - (urun_maliyeti + komisyon_tutari + kargo_ucreti + paketleme_maliyeti + kdv)
    return net_kar, urun_maliyeti  # Maliyeti de döndür

@kar_maliyet_bp.route('/kar_analiz', methods=['GET'])
def kar_analiz():
    """
    Tüm siparişlerin kâr analizini yapar ve toplam net kârı döndürür.
    """
    siparisler = Order.query.all()
    toplam_kar = sum(hesapla_kar(siparis) for siparis in siparisler)

    return jsonify({
        "toplam_kar": toplam_kar,
        "siparis_sayisi": len(siparisler)
    })


import pandas as pd
from flask import send_file

@kar_maliyet_bp.route('/kar_analiz_excel', methods=['GET'])
def kar_analiz_excel():
    """
    Kâr analizini Excel dosyası olarak indir.
    """
    siparisler = Order.query.all()
    data = [{
        "Sipariş No": siparis.order_number,
        "Satış Fiyatı": siparis.amount,
        "Ürün Maliyeti": siparis.vat_base_amount,
        "Net Kâr": hesapla_kar(siparis)
    } for siparis in siparisler]

    df = pd.DataFrame(data)
    file_path = "/tmp/kar_analiz.xlsx"
    df.to_excel(file_path, index=False)

    return send_file(file_path, as_attachment=True)




@kar_maliyet_bp.route('/kar_analiz_sayfasi')
def kar_analiz_sayfasi():
    siparisler = Order.query.all()
    analiz_sonucu = []
    
    for siparis in siparisler:
        net_kar, urun_maliyeti = hesapla_kar(siparis)
        
        # Ürün barkodundan Product tablosunda maliyet bilgisi var mı kontrol et
        urun_barkodlari = siparis.product_barcode.split(', ') if siparis.product_barcode else []
        dolar_maliyeti = None
        
        if urun_barkodlari:
            birincil_barkod = urun_barkodlari[0]
            urun = db.session.query(Product).filter_by(barcode=birincil_barkod).first()
            if urun:
                dolar_maliyeti = urun.cost_usd
        
        analiz_sonucu.append({
            "siparis_no": siparis.order_number,
            "satis_fiyati": siparis.amount,
            "urun_maliyeti": urun_maliyeti,
            "dolar_maliyeti": dolar_maliyeti,
            "net_kar": net_kar
        })

    toplam_kar = sum(item["net_kar"] for item in analiz_sonucu)
    toplam_satis = sum(item["satis_fiyati"] or 0 for item in analiz_sonucu)
    
    # Kar marjı hesaplama
    kar_marji = (toplam_kar / toplam_satis * 100) if toplam_satis > 0 else 0

    return render_template('kar_analiz.html', 
                          siparisler=analiz_sonucu, 
                          toplam_kar=toplam_kar,
                          toplam_satis=toplam_satis,
                          kar_marji=kar_marji)
