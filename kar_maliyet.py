
from flask import Blueprint, jsonify, render_template, send_file
from models import db, Order, Product
from sqlalchemy import func
import pandas as pd
import logging

# Blueprint tanımı
kar_maliyet_bp = Blueprint('kar_maliyet', __name__)

# Logger ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def hesapla_kar(order):
    try:
        satis_fiyati = float(order.amount or 0)
        urun_maliyeti = float(order.vat_base_amount or 0)
        
        urun_barkodlari = order.product_barcode.split(', ') if order.product_barcode else []
        
        if urun_barkodlari:
            birincil_barkod = urun_barkodlari[0]
            urun = Product.query.filter_by(barcode=birincil_barkod).first()
            
            if urun and urun.cost_try:
                urun_maliyeti = urun.cost_try
        
        komisyon_orani = 0.15
        komisyon_tutari = satis_fiyati * komisyon_orani
        kargo_ucreti = 30
        paketleme_maliyeti = 10
        kdv_orani = 0.18
        kdv = satis_fiyati * kdv_orani
        
        net_kar = satis_fiyati - (urun_maliyeti + komisyon_tutari + kargo_ucreti + paketleme_maliyeti + kdv)
        kar_marji = (net_kar / satis_fiyati * 100) if satis_fiyati > 0 else 0
        
        return net_kar, urun_maliyeti, kar_marji
    except Exception as e:
        logger.error(f"Kar hesaplama hatası: {str(e)}")
        return 0, 0, 0

@kar_maliyet_bp.route('/kar_analiz_sayfasi')
def kar_analiz_sayfasi():
    try:
        siparisler = Order.query.all()
        analiz_sonucu = []
        toplam_kar = 0
        toplam_satis = 0

        for siparis in siparisler:
            net_kar, urun_maliyeti, kar_marji = hesapla_kar(siparis)
            
            if siparis.product_barcode:
                birincil_barkod = siparis.product_barcode.split(', ')[0]
                urun = Product.query.filter_by(barcode=birincil_barkod).first()
                dolar_maliyeti = urun.cost_usd if urun else None
            else:
                dolar_maliyeti = None

            toplam_kar += net_kar
            toplam_satis += float(siparis.amount or 0)

            analiz_sonucu.append({
                "siparis_no": siparis.order_number,
                "satis_fiyati": float(siparis.amount or 0),
                "urun_maliyeti": urun_maliyeti,
                "dolar_maliyeti": dolar_maliyeti,
                "net_kar": net_kar,
                "kar_marji": kar_marji
            })

        kar_marji = (toplam_kar / toplam_satis * 100) if toplam_satis > 0 else 0

        return render_template('kar_analiz.html',
                             siparisler=analiz_sonucu,
                             toplam_kar=toplam_kar,
                             toplam_satis=toplam_satis,
                             kar_marji=kar_marji)
    except Exception as e:
        logger.error(f"Kar analiz sayfası hatası: {str(e)}")
        return render_template('error.html', error=str(e))

@kar_maliyet_bp.route('/kar_analiz_excel')
def kar_analiz_excel():
    try:
        siparisler = Order.query.all()
        data = []
        
        for siparis in siparisler:
            net_kar, urun_maliyeti, kar_marji = hesapla_kar(siparis)
            data.append({
                "Sipariş No": siparis.order_number,
                "Satış Fiyatı": siparis.amount,
                "Ürün Maliyeti": urun_maliyeti,
                "Net Kâr": net_kar,
                "Kâr Marjı (%)": kar_marji
            })

        df = pd.DataFrame(data)
        excel_path = "/tmp/kar_analiz.xlsx"
        df.to_excel(excel_path, index=False)
        
        return send_file(excel_path, as_attachment=True, download_name="kar_analiz.xlsx")
    except Exception as e:
        logger.error(f"Excel oluşturma hatası: {str(e)}")
        return jsonify({"error": str(e)}), 500
