from flask import Blueprint, render_template, request, jsonify
from models import db, Order, Product, YeniSiparis, SiparisUrun
from datetime import datetime
import json
from logger_config import app_logger, order_logger
import traceback

logger = order_logger

siparisler_bp = Blueprint('siparisler_bp', __name__)

@siparisler_bp.route('/yeni-siparis', methods=['GET', 'POST'])
def yeni_siparis():
    if request.method == 'GET':
        # Mevcut siparişleri getir
        siparisler = YeniSiparis.query.order_by(YeniSiparis.siparis_tarihi.desc()).all()
        return render_template('yeni_siparis.html', siparisler=siparisler)

    # POST isteği için
    try:
        # Hem JSON hem de form verisi desteği
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
            # Form verisi içindeki ürünleri JSON'dan parse et
            data = {
                'musteri_adi': data.get('musteri_adi'),
                'musteri_soyadi': data.get('musteri_soyadi'),
                'musteri_adres': data.get('musteri_adres'),
                'musteri_telefon': data.get('musteri_telefon'),
                'toplam_tutar': float(data.get('toplam_tutar', 0)),
                'notlar': data.get('notlar', ''),
                'urunler': json.loads(data.get('urunler', '[]'))
            }

        # Sipariş numarası oluştur
        siparis_no = f"SP{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Yeni sipariş oluştur
        yeni_siparis = YeniSiparis(
            siparis_no=siparis_no,
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
        logger.info(f"Sipariş başarıyla kaydedildi: {siparis_no}") #added logging
        return jsonify({'success': True, 'message': 'Sipariş başarıyla kaydedildi'})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Sipariş kaydedilirken hata oluştu: {e}\n{traceback.format_exc()}") #added logging and traceback
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
        logger.error(f"Ürün getirilirken hata oluştu: {e}") #added logging
        return jsonify({'success': False, 'message': str(e)})
@siparisler_bp.route('/kendi-siparislerim')
def kendi_siparislerim():
    try:
        # YeniSiparis tablosundan tüm siparişleri al
        siparisler = YeniSiparis.query.order_by(YeniSiparis.siparis_tarihi.desc()).all()
        
        return render_template('kendi_siparislerim.html', siparisler=siparisler)
    except Exception as e:
        logger.error(f"Kendi siparişleri listelenirken hata: {str(e)}")
        flash('Siparişler yüklenirken bir hata oluştu.', 'danger')
        return redirect(url_for('home.home'))

@siparisler_bp.route('/siparis-detay/<siparis_no>')
def siparis_detay(siparis_no):
    try:
        siparis = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        if not siparis:
            return "Sipariş bulunamadı", 404
            
        urunler = SiparisUrun.query.filter_by(siparis_id=siparis.id).all()
        
        return render_template('siparis_detay_partial.html', 
                             siparis=siparis, 
                             urunler=urunler)
    except Exception as e:
        logger.error(f"Sipariş detayı görüntülenirken hata: {str(e)}")
        return "Bir hata oluştu", 500
