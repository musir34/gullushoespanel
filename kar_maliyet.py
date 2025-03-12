
from flask import Blueprint, jsonify, render_template
from models import db, Order
from sqlalchemy import func

kar_maliyet_bp = Blueprint('kar_maliyet', __name__)

def hesapla_kar(order):
    """
    Sipariş için net kâr hesaplayan fonksiyon.
    """
    satis_fiyati = order.amount or 0
    urun_maliyeti = order.vat_base_amount or 0  # Ürün maliyetini buradan çekiyoruz
    komisyon_orani = 0.15  # Trendyol komisyonu (%15 varsayılan)
    komisyon_tutari = satis_fiyati * komisyon_orani
    kargo_ucreti = 30  # Ortalama bir değer, sipariş bazlı ayarlanabilir
    paketleme_maliyeti = 10  # Ortalama paketleme gideri
    kdv_orani = 0.18
    kdv = satis_fiyati * kdv_orani

    # Net kâr hesaplama
    net_kar = satis_fiyati - (urun_maliyeti + komisyon_tutari + kargo_ucreti + paketleme_maliyeti + kdv)
    return net_kar

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
    analiz_sonucu = [{
        "siparis_no": siparis.order_number,
        "satis_fiyati": siparis.amount,
        "urun_maliyeti": siparis.vat_base_amount,
        "net_kar": hesapla_kar(siparis)
    } for siparis in siparisler]

    toplam_kar = sum(item["net_kar"] for item in analiz_sonucu)

    return render_template('kar_analiz.html', siparisler=analiz_sonucu, toplam_kar=toplam_kar)
