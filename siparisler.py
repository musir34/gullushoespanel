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
    logger.debug(">> yeni_siparis fonksiyonu çağrıldı. Request method: %s", request.method)

    if request.method == 'GET':
        try:
            logger.debug("GET isteği alındı, mevcut siparişler getiriliyor.")

            # Arama parametrelerini al
            siparis_no = request.args.get('siparis_no', '').strip()
            musteri_adi = request.args.get('musteri_adi', '').strip()
            durum = request.args.get('durum', '').strip()
            logger.debug("Alınan arama parametreleri -> siparis_no: '%s', musteri_adi: '%s', durum: '%s'",
                         siparis_no, musteri_adi, durum)

            # Temel sorgu
            query = YeniSiparis.query
            logger.debug("Temel sorgu oluşturuldu: %s", query)

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
            logger.debug("Siparişler listesi: %s", siparisler)

            return render_template('yeni_siparis.html', siparisler=siparisler)
        except Exception as e:
            logger.error("Siparişler getirilirken hata: %s", e)
            logger.debug("Traceback: %s", traceback.format_exc())
            return jsonify({'success': False, 'error': str(e)}), 500

    # POST isteği için
    try:
        logger.debug("POST isteği alındı, sipariş oluşturma süreci başlıyor.")
        logger.debug("Request Headers: %s", request.headers)
        logger.debug("Request Content-Type: %s", request.content_type)

        # Veri formatını kontrol et ve işle
        if request.is_json:
            logger.debug("İstek JSON formatında.")
            data = request.get_json()
        else:
            logger.debug("İstek FORM formatında.")
            form_data = request.form
            logger.debug("Form verisi: %s", form_data)
            
            # Form verisi içinde JSON string olabilir
            urunler = []
            try:
                urunler_json = form_data.get('urunler')
                if urunler_json:
                    urunler = json.loads(urunler_json)
            except json.JSONDecodeError as e:
                logger.error("Ürünler JSON çözümlenemedi: %s", e)
                urunler = []
                
            data = {
                'musteri_adi': form_data.get('musteri_adi', ''),
                'musteri_soyadi': form_data.get('musteri_soyadi', ''),
                'musteri_adres': form_data.get('musteri_adres', ''),
                'musteri_telefon': form_data.get('musteri_telefon', ''),
                'toplam_tutar': float(form_data.get('toplam_tutar', 0) or 0),
                'notlar': form_data.get('notlar', ''),
                'durum': form_data.get('durum', 'Yeni'),
                'urunler': urunler
            }

        logger.debug("İşlenecek data: %s", data)
        
        # Veri doğrulama
        if not data.get('musteri_adi'):
            return jsonify({'success': False, 'error': 'Müşteri adı boş olamaz'}), 400
        if not data.get('musteri_soyadi'):
            return jsonify({'success': False, 'error': 'Müşteri soyadı boş olamaz'}), 400
        if not data.get('musteri_adres'):
            return jsonify({'success': False, 'error': 'Müşteri adresi boş olamaz'}), 400
        if not data.get('musteri_telefon'):
            return jsonify({'success': False, 'error': 'Müşteri telefonu boş olamaz'}), 400
        if not data.get('urunler'):
            return jsonify({'success': False, 'error': 'Sipariş en az bir ürün içermelidir'}), 400

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
            durum=data.get('durum', 'Yeni'),
            notlar=data.get('notlar', '')
        )
        logger.debug("YeniSiparis nesnesi oluşturuldu: %s", yeni_siparis)

        db.session.add(yeni_siparis)
        db.session.flush()  # ID almak için flush
        logger.debug("Sipariş veritabanına eklendi, ID alındı: %s", yeni_siparis.id)

        # Ürünleri kaydet
        for urun in data['urunler']:
            logger.debug("Siparişe eklenecek ürün: %s", urun)
            
            # Ürün verilerini doğrula ve varsayılan değerler ata
            urun_barkod = urun.get('barkod', '')
            urun_adi = urun.get('urun_adi', '')
            
            try:
                adet = int(urun.get('adet', 1))
                if adet <= 0:
                    adet = 1
            except (ValueError, TypeError):
                adet = 1
                
            try:
                birim_fiyat = float(urun.get('birim_fiyat', 0))
                if birim_fiyat < 0:
                    birim_fiyat = 0
            except (ValueError, TypeError):
                birim_fiyat = 0
                
            try:
                toplam_fiyat = adet * birim_fiyat
            except (ValueError, TypeError):
                toplam_fiyat = 0
            
            siparis_urun = SiparisUrun(
                siparis_id=yeni_siparis.id,
                urun_barkod=urun_barkod,
                urun_adi=urun_adi,
                adet=adet,
                birim_fiyat=birim_fiyat,
                toplam_fiyat=toplam_fiyat,
                renk=urun.get('renk', ''),
                beden=urun.get('beden', ''),
                urun_gorseli=urun.get('urun_gorseli', '')
            )
            db.session.add(siparis_urun)
            logger.debug("SiparisUrun eklendi: %s", siparis_urun)

        db.session.commit()
        logger.info("Sipariş başarıyla kaydedildi: %s", siparis_no)
        return jsonify({
            'success': True, 
            'message': 'Sipariş başarıyla kaydedildi',
            'siparis_no': siparis_no  # Başarılı yanıtta sipariş numarasını da gönder
        })

    except Exception as e:
        db.session.rollback()
        logger.error("Sipariş kaydedilirken hata oluştu: %s", e)
        logger.debug("Traceback: %s", traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@siparisler_bp.route('/api/product/<barcode>')
def get_product(barcode):
    logger.debug(">> get_product fonksiyonu çağrıldı. Ürün sorgulanıyor, barkod: %s", barcode)
    try:
        logger.debug("Veritabanında ürün aranıyor...")
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
        logger.debug("Traceback: %s", traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@siparisler_bp.route('/api/siparisler/search', methods=['GET'])
def siparis_ara():
    """
    Siparişlerde hızlı arama için API endpoint'i
    """
    logger.debug(">> siparis_ara fonksiyonu çağrıldı.")
    try:
        search_query = request.args.get('q', '').strip()
        field = request.args.get('field', 'all')
        logger.debug("Arama parametreleri -> q: '%s', field: '%s'", search_query, field)

        if not search_query:
            logger.debug("Arama terimi belirtilmedi, boş sonuç döndürülüyor.")
            return jsonify({
                'success': True,
                'siparisler': [],
                'message': 'Arama terimi belirtilmedi'
            })

        # Base query
        logger.debug("Temel sorgu oluşturuluyor.")
        query = YeniSiparis.query

        # Arama alanına göre filtreleme
        if field == 'siparis_no':
            logger.debug("Sipariş numarası alanında arama yapılıyor: %s", search_query)
            query = query.filter(YeniSiparis.siparis_no.ilike(f'%{search_query}%'))
        elif field == 'musteri':
            logger.debug("Müşteri alanında arama yapılıyor: %s", search_query)
            query = query.filter(
                (YeniSiparis.musteri_adi + ' ' + YeniSiparis.musteri_soyadi).ilike(f'%{search_query}%')
            )
        elif field == 'durum':
            logger.debug("Durum alanında arama yapılıyor: %s", search_query)
            query = query.filter(YeniSiparis.durum.ilike(f'%{search_query}%'))
        else:  # 'all' veya başka bir değer için
            logger.debug("Tüm alanlarda arama yapılıyor: %s", search_query)
            query = query.filter(
                db.or_(
                    YeniSiparis.siparis_no.ilike(f'%{search_query}%'),
                    (YeniSiparis.musteri_adi + ' ' + YeniSiparis.musteri_soyadi).ilike(f'%{search_query}%'),
                    YeniSiparis.durum.ilike(f'%{search_query}%')
                )
            )

        # Siparişleri al ve son 100 ile sınırla
        siparisler = query.order_by(YeniSiparis.siparis_tarihi.desc()).limit(100).all()
        logger.debug("Toplam %d sipariş bulundu. (Limit 100)", len(siparisler))

        # JSON için formatla
        sonuclar = [{
            'siparis_no': s.siparis_no,
            'musteri': f"{s.musteri_adi} {s.musteri_soyadi}",
            'tutar': float(s.toplam_tutar),
            'tarih': s.siparis_tarihi.strftime('%d.%m.%Y %H:%M') if s.siparis_tarihi else '',
            'durum': s.durum
        } for s in siparisler]

        logger.debug("Arama sonucu listesi oluşturuldu: %s", sonuclar)
        logger.debug("Arama terimi: %s, Alan: %s", search_query, field)

        return jsonify({
            'success': True,
            'siparisler': sonuclar,
            'count': len(sonuclar)
        })

    except Exception as e:
        logger.error("Sipariş arama sırasında hata: %s", e)
        logger.debug("Traceback: %s", traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@siparisler_bp.route('/kendi-siparislerim')
def kendi_siparislerim():
    logger.debug(">> kendi_siparislerim fonksiyonu çağrıldı.")
    try:
        # Arama parametreleri
        siparis_no = request.args.get('siparis_no', '').strip()
        logger.debug("Alınan siparis_no arama parametresi: '%s'", siparis_no)

        # Temel sorgu
        query = YeniSiparis.query
        logger.debug("Temel sorgu oluşturuldu: %s", query)

        # Sipariş numarasına göre filtreleme
        if siparis_no:
            logger.debug("Sipariş numarasına göre filtreleme uygulanıyor: %s", siparis_no)
            query = query.filter(YeniSiparis.siparis_no.ilike(f'%{siparis_no}%'))

        # Siparişleri getir
        siparisler = query.order_by(YeniSiparis.siparis_tarihi.desc()).all()
        logger.debug("Toplam %d adet sipariş bulundu.", len(siparisler))
        logger.debug("Sipariş listesi: %s", siparisler)

        return render_template('kendi_siparislerim.html', siparisler=siparisler)
    except Exception as e:
        logger.error("Kendi siparişleri listelenirken hata: %s", e)
        logger.debug("Traceback: %s", traceback.format_exc())
        flash('Siparişler yüklenirken bir hata oluştu.', 'danger')
        return redirect(url_for('home.home'))


@siparisler_bp.route('/siparis-detay/<siparis_no>')
def siparis_detay(siparis_no):
    logger.debug(">> siparis_detay fonksiyonu çağrıldı. Sipariş detayları isteniyor, sipariş no: %s", siparis_no)
    try:
        siparis = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        logger.debug("Veritabanında sipariş araması yapıldı. Bulunan sipariş: %s", siparis)

        if not siparis:
            logger.debug("Sipariş bulunamadı, sipariş no: %s", siparis_no)
            return jsonify({'success': False, 'error': 'Sipariş bulunamadı'}), 404

        urunler = SiparisUrun.query.filter_by(siparis_id=siparis.id).all()
        logger.debug("Siparişe ait %d adet ürün bulundu.", len(urunler))
        logger.debug("Ürünler: %s", urunler)
        
        # Response formatını istekte HTML, JSON gibi tercih edilene göre belirle
        accept_header = request.headers.get('Accept', '')
        if 'application/json' in accept_header:
            # JSON yanıtı oluştur
            urun_listesi = []
            for urun in urunler:
                urun_listesi.append({
                    'id': urun.id,
                    'barkod': urun.urun_barkod,
                    'urun_adi': urun.urun_adi,
                    'adet': urun.adet,
                    'birim_fiyat': urun.birim_fiyat,
                    'toplam_fiyat': urun.toplam_fiyat,
                    'renk': urun.renk or '',
                    'beden': urun.beden or '',
                    'urun_gorseli': urun.urun_gorseli or ''
                })
                
            return jsonify({
                'success': True,
                'siparis': {
                    'siparis_no': siparis.siparis_no,
                    'musteri_adi': siparis.musteri_adi,
                    'musteri_soyadi': siparis.musteri_soyadi,
                    'musteri_adres': siparis.musteri_adres,
                    'musteri_telefon': siparis.musteri_telefon,
                    'toplam_tutar': float(siparis.toplam_tutar or 0),
                    'durum': siparis.durum,
                    'siparis_tarihi': siparis.siparis_tarihi.isoformat() if siparis.siparis_tarihi else None,
                    'notlar': siparis.notlar or ''
                },
                'urunler': urun_listesi
            })
        else:
            # HTML şablonu döndür
            return render_template('siparis_detay_partial.html',
                                  siparis=siparis,
                                  urunler=urunler)
    except Exception as e:
        logger.error("Sipariş detayı görüntülenirken hata: %s", e)
        logger.debug("Traceback: %s", traceback.format_exc())
        
        # Hata yanıtı formatını belirle
        accept_header = request.headers.get('Accept', '')
        if 'application/json' in accept_header:
            return jsonify({'success': False, 'error': str(e)}), 500
        else:
            return "Bir hata oluştu: " + str(e), 500


@siparisler_bp.route('/siparis-guncelle/<siparis_no>', methods=['POST'])
def siparis_guncelle(siparis_no):
    logger.debug(">> siparis_guncelle fonksiyonu çağrıldı. Sipariş güncelleme isteği alındı, sipariş no: %s", siparis_no)
    try:
        logger.debug("Güncellenecek siparişi veritabanından çekme işlemi...")
        siparis = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        logger.debug("Veritabanında bulunan sipariş: %s", siparis)

        if not siparis:
            logger.debug("Güncellenecek sipariş bulunamadı, sipariş no: %s", siparis_no)
            return jsonify({'success': False, 'error': 'Sipariş bulunamadı'}), 404

        # İstek içeriğini kontrol et
        logger.debug("Request Content-Type: %s", request.content_type)
        if request.is_json:
            data = request.get_json()
        else:
            # Form verisi olabilir
            form_data = request.form
            
            # Form içinde JSON dizesi kontrolü
            urunler = []
            try:
                urunler_json = form_data.get('urunler')
                if urunler_json:
                    urunler = json.loads(urunler_json)
            except json.JSONDecodeError as e:
                logger.error("Ürünler JSON çözümlenemedi: %s", e)
                urunler = []
                
            data = {
                'musteri_adi': form_data.get('musteri_adi', siparis.musteri_adi),
                'musteri_soyadi': form_data.get('musteri_soyadi', siparis.musteri_soyadi), 
                'musteri_adres': form_data.get('musteri_adres', siparis.musteri_adres),
                'musteri_telefon': form_data.get('musteri_telefon', siparis.musteri_telefon),
                'durum': form_data.get('durum', siparis.durum),
                'notlar': form_data.get('notlar', siparis.notlar),
                'urunler': urunler
            }
        
        logger.debug("Güncelleme için gelen data: %s", data)

        # Veri doğrulama
        if not data.get('musteri_adi'):
            return jsonify({'success': False, 'error': 'Müşteri adı boş olamaz'}), 400
        if not data.get('musteri_soyadi'):
            return jsonify({'success': False, 'error': 'Müşteri soyadı boş olamaz'}), 400
        if not data.get('musteri_adres'):
            return jsonify({'success': False, 'error': 'Müşteri adresi boş olamaz'}), 400
        if not data.get('musteri_telefon'):
            return jsonify({'success': False, 'error': 'Müşteri telefonu boş olamaz'}), 400

        # Temel bilgileri güncelle
        eski_durum = siparis.durum
        logger.debug("Mevcut sipariş durumu: %s", eski_durum)

        siparis.musteri_adi = data.get('musteri_adi', siparis.musteri_adi)
        siparis.musteri_soyadi = data.get('musteri_soyadi', siparis.musteri_soyadi)
        siparis.musteri_adres = data.get('musteri_adres', siparis.musteri_adres)
        siparis.musteri_telefon = data.get('musteri_telefon', siparis.musteri_telefon)
        
        # Durum değişikliği kontrolü
        yeni_durum = data.get('durum')
        if yeni_durum and yeni_durum != eski_durum:
            logger.info("Sipariş durumu değişti: %s -> %s", eski_durum, yeni_durum)
            siparis.durum = yeni_durum
        
        siparis.notlar = data.get('notlar', siparis.notlar)

        # Ürünleri güncelle
        if 'urunler' in data and data['urunler']:
            logger.debug("Siparişe ait ürünler güncelleniyor. Var olan ürünler silinecek, yenileri eklenecek...")
            # Önce mevcut ürünleri sil
            silinen_sayisi = SiparisUrun.query.filter_by(siparis_id=siparis.id).delete()
            logger.debug("Mevcut %d adet ürün silindi.", silinen_sayisi)

            # Yeni ürünleri ekle
            toplam_tutar = 0
            for urun in data['urunler']:
                logger.debug("Yeni eklenecek ürün: %s", urun)
                
                # Değerleri güvenli bir şekilde al
                try:
                    adet = int(urun.get('adet', 1))
                    if adet <= 0:
                        adet = 1
                except (ValueError, TypeError):
                    adet = 1
                    
                try:
                    birim_fiyat = float(urun.get('birim_fiyat', 0))
                    if birim_fiyat < 0:
                        birim_fiyat = 0
                except (ValueError, TypeError):
                    birim_fiyat = 0
                
                barkod = urun.get('barkod', '')
                urun_adi = urun.get('urun_adi', '')
                
                yeni_urun = SiparisUrun(
                    siparis_id=siparis.id,
                    urun_barkod=barkod,
                    urun_adi=urun_adi,
                    adet=adet,
                    birim_fiyat=birim_fiyat,
                    toplam_fiyat=adet * birim_fiyat,
                    renk=urun.get('renk', ''),
                    beden=urun.get('beden', ''),
                    urun_gorseli=urun.get('urun_gorseli', '')
                )
                db.session.add(yeni_urun)
                toplam_tutar += yeni_urun.toplam_fiyat

            siparis.toplam_tutar = toplam_tutar
            logger.debug("Yeni toplam_tutar hesaplandı: %s", siparis.toplam_tutar)

        db.session.commit()
        logger.info("Sipariş başarıyla güncellendi: %s", siparis_no)
        return jsonify({
            'success': True, 
            'message': 'Sipariş başarıyla güncellendi',
            'siparis': {
                'siparis_no': siparis.siparis_no,
                'durum': siparis.durum,
                'toplam_tutar': float(siparis.toplam_tutar or 0)
            }
        })

    except Exception as e:
        db.session.rollback()
        logger.error("Sipariş güncellenirken hata oluştu: %s", e)
        logger.debug("Traceback: %s", traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@siparisler_bp.route('/siparis-sil/<siparis_no>', methods=['DELETE'])
def siparis_sil(siparis_no):
    logger.debug(">> siparis_sil fonksiyonu çağrıldı. Sipariş silme isteği alındı, sipariş no: %s", siparis_no)
    try:
        logger.debug("Silinecek siparişi veritabanından çekme işlemi...")
        siparis = YeniSiparis.query.filter_by(siparis_no=siparis_no).first()
        logger.debug("Veritabanında bulunan sipariş: %s", siparis)

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
        logger.debug("Traceback: %s", traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500
