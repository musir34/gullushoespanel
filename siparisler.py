from flask import Blueprint, render_template, request, jsonify
from models import db, Order, Product, YeniSiparis, SiparisUrun # Assuming YeniSiparis and SiparisUrun models are defined
from datetime import datetime
import json

siparisler_bp = Blueprint('siparisler_bp', __name__)

@siparisler_bp.route('/yeni-siparis', methods=['POST'])
def yeni_siparis():
    try:
        data = request.get_json()

        # Yeni sipariş oluştur
        yeni_siparis = YeniSiparis(
            musteri_adi=data['musteri_adi'],
            musteri_soyadi=data['musteri_soyadi'],
            musteri_adres=data['musteri_adres'],
            musteri_telefon=data['musteri_telefon'],
            toplam_tutar=data['toplam_tutar'],
            notlar=data.get('notlar', '')
        )

        db.session.add(yeni_siparis)
        db.session.flush()  # ID almak için flush

        # Ürünleri kaydet
        for urun in data['urunler']:
            siparis_urun = SiparisUrun(
                siparis_id=yeni_siparis.id,
                urun_barkod=urun['barkod'],
                urun_adi=urun['urun_adi'],
                adet=urun['adet'],
                birim_fiyat=urun['birim_fiyat'],
                toplam_fiyat=urun['adet'] * urun['birim_fiyat'],
                renk=urun.get('renk', ''),
                beden=urun.get('beden', ''),
                urun_gorseli=urun.get('urun_gorseli', '')
            )
            db.session.add(siparis_urun)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Sipariş başarıyla kaydedildi'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@siparisler_bp.route('/api/product/<barcode>')
def get_product(barcode):
    try:
        product = Product.query.filter_by(barcode=barcode).first()
        if product:
            return jsonify({
                'success': True,
                'product': {
                    'barcode': product.barcode,
                    'title': product.title,
                    'product_main_id': product.product_main_id,
                    'color': product.color,
                    'size': product.size,
                    'images': product.images,
                    'sale_price': float(product.sale_price or 0),
                    'quantity': product.quantity
                }
            })
        return jsonify({'success': False, 'message': 'Ürün bulunamadı'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})