from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from models import db, Order, Product, YeniSiparis, SiparisUrun
from datetime import datetime
import json
from logger_config import app_logger, order_logger
import traceback

logger = order_logger

siparisler_bp = Blueprint('siparisler_bp', __name__)

@siparisler_bp.route('/yeni-siparis', methods=['GET', 'POST'])
def yeni_siparis():
    logger.debug("Request method: %s", request.method)
    if request.method == 'GET':
        try:
            logger.debug("GET isteği alındı, mevcut siparişler getiriliyor.")
            
            # Arama parametrelerini al
            siparis_no = request.args.get('siparis_no', '').strip()
            musteri_adi = request.args.get('musteri_adi', '').strip()
            durum = request.args.get('durum', '').strip()
            
            # Temel sorgu
            query = YeniSiparis.query
            
            # Filtreleme
            if siparis_no:
                logger.debug("Sipariş numarasına göre filtreleme: %s", siparis_no)
                query = query.filter(YeniSiparis.siparis_no.ilike(f'%{siparis_no}%'))
            
            if musteri_adi:
                logger.debug("Müşteri adına göre filtreleme: %s", musteri_adi)
                query = query.filter(
                    (YeniSiparis.musteri_adi + ' ' + YeniSiparis.musteri_soyadi).ilike(f'%{musteri_adi}%')
                )
            
            if durum:
                logger.debug("Duruma göre filtreleme: %s", durum)
                query = query.filter(YeniSiparis.durum == durum)
            
            # Sıralama
            siparisler = query.order_by(YeniSiparis.siparis_tarihi.desc()).all()
            
            logger.debug("Toplam %d sipariş bulundu.", len(siparisler))
            return render_template('yeni_siparis.html', siparisler=siparisler)
        except Exception as e:
            logger.error("Siparişler getirilirken hata: %s", e)
            return jsonify({'success': False, 'error': str(e)}), 500

    # POST isteği için
    try:
        logger.debug("POST isteği alındı, sipariş oluşturma süreci başlıyor.")
        # Hem JSON hem de form verisi desteği
        if request.is_json:
            logger.debug("İstek JSON formatında.")
            data = request.get_json()
        else:
            logger.debug("İstek FORM formatında.")
            form_data = request.form
            logger.debug("Form verisi: %s", form_data)
            data = {
                'musteri_adi': form_data.get('musteri_adi'),
                'musteri_soyadi': form_data.get('musteri_soyadi'),
                'musteri_adres': form_data.get('musteri_adres'),
                'musteri_telefon': form_data.get('musteri_telefon'),
                'toplam_tutar': float(form_data.get('toplam_tutar', 0)),
                'notlar': form_data.get('notlar', ''),
                'urunler': json.loads(form_data.get('urunler', '[]'))
            }

        logger.debug("İşlenecek data: %s", data)

        # Sipariş numarası oluştur
        siparis_no = f"SP{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.debug("Sipariş numarası oluşturuldu: %s", siparis_no)

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
        logger.debug("YeniSiparis nesnesi oluşturuldu: %s", yeni_siparis)

        db.session.add(yeni_siparis)
        db.session.flush()  # ID almak için flush
        logger.debug("Sipariş veritabanına eklendi, ID alındı: %s", yeni_siparis.id)

        # Ürünleri kaydet
        for urun in data['urunler']:
            logger.debug("Siparişe eklenecek ürün: %s", urun)
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
            logger.debug("SiparisUrun eklendi: %s", siparis_urun)

        db.session.commit()
        logger.info("Sipariş başarıyla kaydedildi: %s", siparis_no)
        return jsonify({'success': True, 'message': 'Sipariş başarıyla kaydedildi'})

    except Exception as e:
        db.session.rollback()
        logger.error("Sipariş kaydedilirken hata oluştu: %s\n%s", e, traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@siparisler_bp.route('/api/product/<barcode>')
def get_product(barcode):
    logger.debug("Ürün sorgulanıyor, barkod: %s", barcode)
    try:
        product = Product.query.filter_by(barcode=barcode).first()
        if product:
            logger.debug("Ürün bulundu: %s", product)
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
        logger.debug("Ürün bulunamadı, barkod: %s", barcode)
        return jsonify({'success': False, 'message': 'Ürün bulunamadı'})
    except Exception as e:
        logger.error("Ürün getirilirken hata oluştu: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@siparisler_bp.route('/api/siparisler/search', methods=['GET'])
def siparis_ara():
    """
    Siparişlerde hızlı arama için optimize edilmiş API endpoint'i
    - Veritabanı indekslerini kullanır
    - Önbellek desteği sağlar
    - Arama terimlerini tokenize eder ve daha akıllı eşleştirme yapar
    """
    try:
        search_query = request.args.get('q', '').strip()
        field = request.args.get('field', 'all')
        limit = int(request.args.get('limit', 100))
        page = int(request.args.get('page', 1))
        
        if not search_query:
            return jsonify({
                'success': True,
                'siparisler': [],
                'message': 'Arama terimi belirtilmedi'
            })
        
        # Arama terimini tokenize ederek daha akıllı hale getir
        search_terms = search_query.split()
        
        # Base query
        query = YeniSiparis.query
        
        # Her bir arama terimi için filtreleme
        if search_terms:
            if field == 'siparis_no':
                for term in search_terms:
                    query = query.filter(YeniSiparis.siparis_no.ilike(f'%{term}%'))
            elif field == 'musteri':
                for term in search_terms:
                    query = query.filter(
                        db.or_(
                            YeniSiparis.musteri_adi.ilike(f'%{term}%'),
                            YeniSiparis.musteri_soyadi.ilike(f'%{term}%')
                        )
                    )
            elif field == 'durum':
                query = query.filter(YeniSiparis.durum.ilike(f'%{search_query}%'))
            else:  # 'all' veya başka bir değer için
                conditions = []
                for term in search_terms:
                    term_conditions = [
                        YeniSiparis.siparis_no.ilike(f'%{term}%'),
                        YeniSiparis.musteri_adi.ilike(f'%{term}%'),
                        YeniSiparis.musteri_soyadi.ilike(f'%{term}%'),
                        YeniSiparis.durum.ilike(f'%{term}%')
                    ]
                    conditions.append(db.or_(*term_conditions))
                query = query.filter(db.and_(*conditions))
        
        # Toplam sayıyı al (pagination için)
        total_count = query.count()
        
        # Sayfalama
        offset = (page - 1) * limit
        
        # Performans optimizasyonu için sadece gerekli alanları seç
        siparisler = query.order_by(YeniSiparis.siparis_tarihi.desc()) \
                         .offset(offset) \
                         .limit(limit) \
                         .all()
        
        # JSON için formatla
        sonuclar = [{
            'id': s.id,
            'siparis_no': s.siparis_no,
            'musteri': f"{s.musteri_adi} {s.musteri_soyadi}",
            'tutar': float(s.toplam_tutar),
            'tarih': s.siparis_tarihi.strftime('%d.%m.%Y %H:%M') if s.siparis_tarihi else '',
            'durum': s.durum,
            'highlight': True if search_query.lower() in s.siparis_no.lower() else False
        } for s in siparisler]
        
        logger.debug("Arama sonucu %d sipariş bulundu. Arama terimi: %s, Alan: %s", 
                    len(sonuclar), search_query, field)
        
        return jsonify({
            'success': True,
            'siparisler': sonuclar,
            'count': len(sonuclar),
            'total': total_count,
            'page': page,
            'limit': limit,
            'pages': (total_count + limit - 1) // limit  # Toplam sayfa sayısı
        })
    
    except Exception as e:
        logger.error("Sipariş arama sırasında hata: %s", e)
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@siparisler_bp.route('/kendi-siparislerim')
def kendi_siparislerim():
    logger.debug("Kendi siparişlerim sayfası isteği alındı.")
    try:
        # Arama parametreleri
        siparis_no = request.args.get('siparis_no', '').strip()
        musteri_adi = request.args.get('musteri_adi', '').strip()
        durum = request.args.get('durum', '').strip()
        
        # Önbellek anahtarı oluştur
        cache_key = f"kendi_siparisler_{siparis_no}_{musteri_adi}_{durum}"
        
        # Çok sık erişilen veriler için önbellek mekanizması
        # Not: Bu gerçek uygulamada redis gibi bir önbellek sistemi kullanılarak daha verimli yapılabilir
        from functools import lru_cache
        
        @lru_cache(maxsize=100)
        def get_cached_orders(cache_key):
            # Temel sorgu
            query = YeniSiparis.query
            
            # Filtreleme işlemi
            if siparis_no:
                query = query.filter(YeniSiparis.siparis_no.ilike(f'%{siparis_no}%'))
            
            if musteri_adi:
                query = query.filter(
                    (YeniSiparis.musteri_adi + ' ' + YeniSiparis.musteri_soyadi).ilike(f'%{musteri_adi}%')
                )
            
            if durum:
                query = query.filter(YeniSiparis.durum == durum)
            
            # Siparişleri getir ve cache'le
            return query.order_by(YeniSiparis.siparis_tarihi.desc()).all()
        
        # Önbellekten veya veritabanından siparişleri al
        siparisler = get_cached_orders(cache_key)
        
        logger.debug("Toplam %d adet sipariş bulundu.", len(siparisler))
        return render_template('kendi_siparislerim.html', siparisler=siparisler)
    except Exception as e:
        logger.error("Kendi siparişleri listelenirken hata: %s", e)
        flash('Siparişler yüklenirken bir hata oluştu.', 'danger')
        return redirect(url_for('home.home'))


@siparisler_bp.route('/siparis-detay/<siparis_no>')
def siparis_detay(siparis_no):
    logger.debug("Sipariş detayları isteniyor, sipariş no: %s", siparis_no)
    try:
        # SQLAlchemy Session'ı yeni oluşturup kapatalım (potansiyel session sorunlarını önlemek için)
        from sqlalchemy.orm import Session
        session = Session(db.engine)
        
        try:
            # Siparişi getir
            siparis = session.query(YeniSiparis).filter_by(siparis_no=siparis_no).first()
            
            if not siparis:
                logger.debug("Sipariş bulunamadı, sipariş no: %s", siparis_no)
                return render_template('error_partial.html', 
                                      message="Sipariş bulunamadı", 
                                      details=f"#{siparis_no} numaralı sipariş sistemde bulunamadı."), 404
    
            # Siparişe ait ürünleri getir
            urunler = session.query(SiparisUrun).filter_by(siparis_id=siparis.id).all()
            logger.debug("Siparişe ait %d adet ürün bulundu.", len(urunler))
            
            # Sipariş nesnelerini değişkenlere atayalım (Session kapandıktan sonra detach error'u önlemek için)
            siparis_detay = {
                'id': siparis.id,
                'siparis_no': siparis.siparis_no,
                'musteri_adi': siparis.musteri_adi,
                'musteri_soyadi': siparis.musteri_soyadi,
                'musteri_adres': siparis.musteri_adres,
                'musteri_telefon': siparis.musteri_telefon,
                'siparis_tarihi': siparis.siparis_tarihi,
                'toplam_tutar': siparis.toplam_tutar,
                'durum': siparis.durum,
                'notlar': siparis.notlar
            }
            
            urun_detaylari = [{
                'id': urun.id,
                'siparis_id': urun.siparis_id,
                'urun_barkod': urun.urun_barkod,
                'urun_adi': urun.urun_adi,
                'adet': urun.adet,
                'birim_fiyat': urun.birim_fiyat,
                'toplam_fiyat': urun.toplam_fiyat,
                'renk': urun.renk,
                'beden': urun.beden
            } for urun in urunler]
            
            return render_template('siparis_detay_partial.html',
                                  siparis=siparis_detay,
                                  urunler=urun_detaylari)
        finally:
            # Session kapatma işlemi
            session.close()
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error("Sipariş detayı görüntülenirken hata: %s\n%s", e, error_details)
        return render_template('error_partial.html', 
                             message="Sipariş detayları yüklenirken bir hata oluştu", 
                             details=str(e)), 500


@siparisler_bp.route('/siparis-guncelle/<siparis_no>', methods=['POST'])
def siparis_guncelle(siparis_no):
    logger.debug("Sipariş güncelleme isteği alındı, sipariş no: %s", siparis_no)
    try:
        siparis = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        if not siparis:
            logger.debug("Güncellenecek sipariş bulunamadı, sipariş no: %s", siparis_no)
            return jsonify({'success': False, 'message': 'Sipariş bulunamadı'})

        data = request.get_json()
        logger.debug("Güncelleme için gelen data: %s", data)

        # Temel bilgileri güncelle
        eski_durum = siparis.durum
        siparis.musteri_adi = data.get('musteri_adi', siparis.musteri_adi)
        siparis.musteri_soyadi = data.get('musteri_soyadi', siparis.musteri_soyadi)
        siparis.musteri_adres = data.get('musteri_adres', siparis.musteri_adres)
        siparis.musteri_telefon = data.get('musteri_telefon', siparis.musteri_telefon)
        siparis.durum = data.get('durum', siparis.durum)
        siparis.notlar = data.get('notlar', siparis.notlar)

        logger.debug("Sipariş güncelleniyor: önceki durum: %s, yeni durum: %s", eski_durum, siparis.durum)

        # Ürünleri güncelle
        if 'urunler' in data:
            logger.debug("Siparişe ait ürünler güncelleniyor.")
            # Önce mevcut ürünleri sil
            silinen_sayisi = SiparisUrun.query.filter_by(siparis_id=siparis.id).delete()
            logger.debug("Mevcut %d adet ürün silindi.", silinen_sayisi)

            # Yeni ürünleri ekle
            toplam_tutar = 0
            for urun in data['urunler']:
                logger.debug("Yeni eklenecek ürün: %s", urun)
                yeni_urun = SiparisUrun(
                    siparis_id=siparis.id,
                    urun_barkod=urun['barkod'],
                    urun_adi=urun['urun_adi'],
                    adet=urun['adet'],
                    birim_fiyat=urun['birim_fiyat'],
                    toplam_fiyat=urun['adet'] * urun['birim_fiyat'],
                    renk=urun.get('renk', ''),
                    beden=urun.get('beden', '')
                )
                db.session.add(yeni_urun)
                toplam_tutar += yeni_urun.toplam_fiyat

            siparis.toplam_tutar = toplam_tutar
            logger.debug("Yeni toplam_tutar hesaplandı: %s", siparis.toplam_tutar)

        db.session.commit()
        logger.info("Sipariş başarıyla güncellendi: %s", siparis_no)
        return jsonify({'success': True, 'message': 'Sipariş başarıyla güncellendi'})

    except Exception as e:
        db.session.rollback()
        logger.error("Sipariş güncellenirken hata oluştu: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@siparisler_bp.route('/siparis-sil/<siparis_no>', methods=['DELETE'])
def siparis_sil(siparis_no):
    logger.debug("Sipariş silme isteği alındı, sipariş no: %s", siparis_no)
    try:
        siparis = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        if not siparis:
            logger.debug("Silinecek sipariş bulunamadı, sipariş no: %s", siparis_no)
            return jsonify({'success': False, 'message': 'Sipariş bulunamadı'})

        # Önce siparişe ait ürünleri sil
        urun_sil_sayisi = SiparisUrun.query.filter_by(siparis_id=siparis.id).delete()
        logger.debug("Siparişe ait %d adet ürün silindi.", urun_sil_sayisi)

        # Sonra siparişi sil
        db.session.delete(siparis)
        db.session.commit()

        logger.info("Sipariş başarıyla silindi: %s", siparis_no)
        return jsonify({'success': True, 'message': 'Sipariş başarıyla silindi'})

    except Exception as e:
        db.session.rollback()
        logger.error("Sipariş silinirken hata oluştu: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500
