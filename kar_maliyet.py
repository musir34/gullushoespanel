
from flask import Blueprint, render_template, request, jsonify
from models import db, Order, Product
from sqlalchemy import func
from datetime import datetime, timedelta
import logging

kar_maliyet_bp = Blueprint('kar_maliyet', __name__)

@kar_maliyet_bp.route('/kar-analiz')
def kar_analiz():
    return render_template('kar_analiz.html')

@kar_maliyet_bp.route('/api/kar-analiz', methods=['GET'])
def get_kar_analiz():
    try:
        # Tarih aralığı al
        baslangic = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        bitis = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        
        # Satış verileri
        satis_verileri = db.session.query(
            Order.product_main_id,
            func.sum(Order.amount).label('toplam_satis'),
            func.sum(Order.quantity).label('toplam_adet'),
            Product.cost_try.label('birim_maliyet')
        ).join(
            Product, Order.product_main_id == Product.product_main_id
        ).filter(
            Order.order_date.between(baslangic, bitis),
            Order.status != 'Cancelled'
        ).group_by(
            Order.product_main_id,
            Product.cost_try
        ).all()

        sonuclar = []
        toplam_kar = 0
        toplam_ciro = 0
        toplam_maliyet = 0

        for veri in satis_verileri:
            birim_maliyet = float(veri.birim_maliyet or 0)
            toplam_satis = float(veri.toplam_satis or 0)
            toplam_adet = int(veri.toplam_adet or 0)
            
            toplam_maliyet_urun = birim_maliyet * toplam_adet
            kar = toplam_satis - toplam_maliyet_urun
            
            toplam_kar += kar
            toplam_ciro += toplam_satis
            toplam_maliyet += toplam_maliyet_urun
            
            sonuclar.append({
                'urun_id': veri.product_main_id,
                'toplam_satis': round(toplam_satis, 2),
                'toplam_adet': toplam_adet,
                'birim_maliyet': round(birim_maliyet, 2),
                'toplam_maliyet': round(toplam_maliyet_urun, 2),
                'kar': round(kar, 2),
                'kar_orani': round((kar / toplam_satis * 100) if toplam_satis > 0 else 0, 2)
            })

        return jsonify({
            'success': True,
            'sonuclar': sonuclar,
            'ozet': {
                'toplam_kar': round(toplam_kar, 2),
                'toplam_ciro': round(toplam_ciro, 2),
                'toplam_maliyet': round(toplam_maliyet, 2),
                'genel_kar_orani': round((toplam_kar / toplam_ciro * 100) if toplam_ciro > 0 else 0, 2)
            }
        })

    except Exception as e:
        logging.error(f"Kar analizi hesaplanırken hata: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
