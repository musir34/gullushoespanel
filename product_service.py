from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import base64
import aiohttp
import asyncio
import json
import traceback
from datetime import datetime
from models import db, Product
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL
import logging
from sqlalchemy.exc import SQLAlchemyError

# Loglama ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('product_service.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

product_service_bp = Blueprint('product_service', __name__)

@product_service_bp.route('/fetch-trendyol-products', methods=['POST'])
def fetch_trendyol_products_route():
    try:
        # Asenkron fonksiyonu çağır
        asyncio.run(fetch_trendyol_products_async())
        flash('Ürün kataloğu başarıyla güncellendi!', 'success')
    except Exception as e:
        logger.error(f"Hata: fetch_trendyol_products_route - {e}")
        flash('Ürün kataloğu güncellenirken bir hata oluştu.', 'danger')

    return redirect(url_for('get_products.get_products_list'))


async def fetch_trendyol_products_async():
    """
    Trendyol API'den tüm ürünleri asenkron olarak çeker
    """
    try:
        # API anahtarlarını kontrol et
        if not API_KEY or not API_SECRET or not SUPPLIER_ID:
            logger.error("API anahtarları eksik! API_KEY, API_SECRET ve SUPPLIER_ID kontrol edin.")
            return
            
        logger.info("Trendyol API'den ürünler çekiliyor...")
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/products"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        # İlk isteği yaparak toplam ürün ve sayfa sayısını alalım
        params = {
            "page": 0,
            "size": 200,  # Maksimum sayfa boyutu
            "approved": "true"  # Sadece onaylanmış ürünler
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"API Error: {response.status} - {error_text}")
                        return
                    
                    response_data = await response.json()
                    total_elements = response_data.get('totalElements', 0)
                    total_pages = response_data.get('totalPages', 1)
                    logger.info(f"Toplam ürün sayısı: {total_elements}, Toplam sayfa sayısı: {total_pages}")
                    
                    if total_elements == 0:
                        logger.warning("API'den hiç ürün alınamadı. Onaylı ürünleriniz olduğundan emin olun.")
                        return

                    # Tüm sayfalar için istek hazırlayalım
                    tasks = []
                    semaphore = asyncio.Semaphore(5)  # Aynı anda maksimum 5 istek
                    for page_number in range(total_pages):
                        params_page = params.copy()
                        params_page['page'] = page_number
                        task = fetch_products_page(session, url, headers, params_page, semaphore)
                        tasks.append(task)

                    # Asenkron olarak tüm istekleri yapalım
                    pages_data = await asyncio.gather(*tasks)

                    # Gelen ürünleri birleştirelim
                    all_products_data = []
                    for products in pages_data:
                        if products:
                            all_products_data.extend(products)

                    logger.info(f"Toplam çekilen ürün sayısı: {len(all_products_data)}")
                    
                    if not all_products_data:
                        logger.warning("İşlenecek ürün verisi bulunamadı!")
                        return

                    # Ürünleri işleyelim
                    process_all_products(all_products_data)
                    
            except aiohttp.ClientError as e:
                logger.error(f"API bağlantı hatası: {e}")
            except json.JSONDecodeError as e:
                logger.error(f"API yanıtı geçersiz JSON formatı: {e}")

    except Exception as e:
        logger.error(f"Hata: fetch_trendyol_products_async - {e}")
        # Ayrıntılı hata izini görüntüle
        import traceback
        logger.error(traceback.format_exc())


async def fetch_products_page(session, url, headers, params, semaphore):
    """
    Belirli bir sayfadaki ürünleri çeker
    """
    async with semaphore:
        try:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    page = params.get('page', 'bilinmeyen')
                    logger.error(f"Sayfa {page} için API isteği başarısız oldu: {response.status} - {error_text}")
                    return []
                    
                try:
                    data = await response.json()
                    products_data = data.get('content', [])
                    page = params.get('page', 'bilinmeyen')
                    logger.info(f"Sayfa {page} - {len(products_data)} ürün alındı")
                    
                    # Stok bilgisi olan ürünleri kontrol edelim
                    stock_products = [p for p in products_data if p.get('quantity', 0) > 0]
                    if stock_products:
                        logger.info(f"Sayfa {page} - {len(stock_products)} ürün stokta var")
                    
                    return products_data
                except json.JSONDecodeError as e:
                    page = params.get('page', 'bilinmeyen')
                    response_text = await response.text()
                    logger.error(f"Sayfa {page} - JSON çözümleme hatası: {e}")
                    logger.error(f"Ham yanıt: {response_text[:200]}...")
                    return []
                    
        except aiohttp.ClientError as e:
            logger.error(f"Hata: HTTP bağlantısı - {e}")
            return []
        except Exception as e:
            logger.error(f"Hata: fetch_products_page - {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []


def process_all_products(all_products_data):
    """
    Trendyol'dan çekilen ürünleri veritabanına kaydeder
    """
    try:
        logger.info(f"Toplam {len(all_products_data)} ürün işlenecek")
        # Mevcut ürünleri al
        existing_products = Product.query.all()
        existing_products_dict = {product.barcode: product for product in existing_products}

        # Yeni ürünleri toplu kaydetmek için liste
        new_products = []
        updated_products = []

        # Trendyol API'den gelen tüm ürünlerin barkodlarını tutalım
        api_barcodes = set()

        for product_data in all_products_data:
            try:
                # Temel ürün bilgilerini çıkar
                barcode = product_data.get('barcode', '')
                if not barcode:
                    logger.warning(f"Barkodu olmayan ürün atlandı: {product_data}")
                    continue

                api_barcodes.add(barcode)
                
                # Görsel URL'ini düzeltme
                images = product_data.get('images', [])
                image_url = ''
                if images and isinstance(images, list) and len(images) > 0:
                    image_url = images[0]
                
                # Ürün büyük/küçük harf ve özel karakter farklılıklarına karşı önlem
                original_barcode = product_data.get('barcode', '')
                
                # Ürün verilerini hazırla - Product modeline TAMAMEN uygun hale getirildi
                product_data_dict = {
                    'barcode': barcode,
                    'original_product_barcode': original_barcode,
                    'title': product_data.get('title', ''),
                    'product_main_id': str(product_data.get('productMainId', '')),
                    'quantity': product_data.get('quantity', 0),
                    'images': image_url,
                    'variants': json.dumps(product_data.get('variants', [])),
                    'size': product_data.get('size', ''),
                    'color': product_data.get('color', ''),
                    'archived': False,  # Varsayılan değer
                    'locked': False,    # Varsayılan değer
                    'on_sale': True,    # Varsayılan değer
                    'reject_reason': product_data.get('rejectReason', ''),
                    'sale_price': float(product_data.get('salePrice', 0)),
                    'list_price': float(product_data.get('listPrice', 0)),
                    'currency_type': product_data.get('currencyType', 'TRY'),
                    'hidden': False     # Varsayılan değer
                }

                if barcode in existing_products_dict:
                    # Mevcut ürünü güncelle
                    existing_product = existing_products_dict[barcode]
                    # Stok güncellemesi için önceki değeri loglayalım
                    old_quantity = existing_product.quantity
                    
                    for key, value in product_data_dict.items():
                        if hasattr(existing_product, key):  # Eğer özellik modelde varsa
                            setattr(existing_product, key, value)
                    
                    # Stok değişikliğini loglayalım
                    new_quantity = product_data_dict['quantity']
                    if old_quantity != new_quantity:
                        logger.info(f"Stok güncellendi: {barcode} - Eski: {old_quantity}, Yeni: {new_quantity}")
                    
                    updated_products.append(existing_product)
                else:
                    # Yeni ürün oluştur - Tam constructor çağrısı ile
                    try:
                        new_product = Product(
                            barcode=barcode,
                            original_product_barcode=original_barcode,
                            title=product_data_dict['title'],
                            product_main_id=product_data_dict['product_main_id'],
                            quantity=product_data_dict['quantity'],
                            images=product_data_dict['images'],
                            variants=product_data_dict['variants'],
                            size=product_data_dict['size'],
                            color=product_data_dict['color'],
                            archived=False,
                            locked=False,
                            on_sale=True,
                            reject_reason=product_data_dict['reject_reason'],
                            sale_price=product_data_dict['sale_price'],
                            list_price=product_data_dict['list_price'],
                            currency_type=product_data_dict['currency_type'],
                            cost_usd=0.0,
                            cost_try=0.0,
                            cost_date=None,
                            hidden=False
                        )
                        new_products.append(new_product)
                        logger.info(f"Yeni ürün eklendi: {barcode} - Stok: {product_data_dict['quantity']}")
                    except Exception as e:
                        logger.error(f"Yeni ürün oluşturulurken hata: {barcode} - {e}")
                        continue
            
            except Exception as e:
                logger.error(f"Ürün verisi işlenirken hata: {e} - Veri: {product_data}")
                continue

        # Yeni ürünleri toplu olarak ekle
        if new_products:
            try:
                db.session.add_all(new_products)
                logger.info(f"Toplam {len(new_products)} yeni ürün eklendi")
            except Exception as e:
                logger.error(f"Yeni ürünler veritabanına eklenirken hata: {e}")
                db.session.rollback()
                # Tek tek eklemeyi deneyelim
                for product in new_products:
                    try:
                        db.session.add(product)
                        db.session.commit()
                    except Exception as inner_e:
                        logger.error(f"Tek ürün eklenirken hata: {product.barcode} - {inner_e}")
                        db.session.rollback()

        # Güncellenmiş ürünleri kaydet
        if updated_products:
            try:
                for product in updated_products:
                    db.session.add(product)
                logger.info(f"Toplam {len(updated_products)} ürün güncellendi")
            except Exception as e:
                logger.error(f"Ürünler güncellenirken hata: {e}")
                db.session.rollback()

        try:
            db.session.commit()
            logger.info("Ürün veritabanı başarıyla güncellendi")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Veritabanı commit işlemi sırasında hata: {e}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Hata: process_all_products - {e}")
        # Tam hata izlemeyi ekrana yazdır
        import traceback
        logger.error(traceback.format_exc())


@product_service_bp.route('/api/product-categories', methods=['GET'])
async def get_product_categories():
    """
    Trendyol'daki tüm kategorileri çeker
    """
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}product-categories"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return jsonify({'success': False, 'error': f"API hatası: {response.status}"}), 500

                data = await response.json()
                return jsonify({'success': True, 'categories': data})

    except Exception as e:
        logger.error(f"Hata: get_product_categories - {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@product_service_bp.route('/api/brands', methods=['GET'])
async def get_brands():
    """
    Trendyol'daki tüm markaları çeker veya isme göre filtreleyerek arar
    """
    try:
        name = request.args.get('name', '')

        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')

        if name:
            url = f"{BASE_URL}brands/by-name?name={name}"
        else:
            url = f"{BASE_URL}brands" 

        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return jsonify({'success': False, 'error': f"API hatası: {response.status}"}), 500

                data = await response.json()
                return jsonify({'success': True, 'brands': data})

    except Exception as e:
        logger.error(f"Hata: get_brands - {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@product_service_bp.route('/api/category-attributes/<int:category_id>', methods=['GET'])
async def get_category_attributes(category_id):
    """
    Belirli bir kategorinin özelliklerini çeker
    """
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}product-categories/{category_id}/attributes"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return jsonify({'success': False, 'error': f"API hatası: {response.status}"}), 500

                data = await response.json()
                return jsonify({'success': True, 'attributes': data})

    except Exception as e:
        logger.error(f"Hata: get_category_attributes - {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@product_service_bp.route('/update-price-stock', methods=['POST'])
async def update_price_stock():
    """
    Seçilen ürünlerin fiyat ve stok bilgilerini Trendyol'da günceller
    """
    try:
        data = request.json
        if not data or 'items' not in data:
            return jsonify({'success': False, 'error': 'Geçersiz veri formatı'}), 400

        items = data['items']
        if not items:
            return jsonify({'success': False, 'error': 'Güncellenecek ürün bulunamadı'}), 400

        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/products/price-and-inventory"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        # API formatına uygun veri dönüşümü
        api_items = []
        for item in items:
            api_item = {
                "barcode": item.get('barcode'),
                "quantity": item.get('quantity'),
                "salePrice": item.get('salePrice'),
                "listPrice": item.get('listPrice', item.get('salePrice'))
            }
            api_items.append(api_item)

        payload = {"items": api_items}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response_data = await response.json()

                if response.status != 200:
                    logger.error(f"API Error: {response.status} - {response_data}")
                    return jsonify({'success': False, 'error': f"API hatası: {response_data}"}), 500

                # Veritabanında da aynı güncellemeleri yapalım
                for item in items:
                    barcode = item.get('barcode')
                    product = Product.query.filter_by(barcode=barcode).first()
                    if product:
                        product.quantity = item.get('quantity')
                        product.sale_price = item.get('salePrice')
                        product.list_price = item.get('listPrice', item.get('salePrice'))
                        product.last_update_date = datetime.now()
                        db.session.add(product)

                db.session.commit()

                return jsonify({
                    'success': True, 
                    'message': 'Ürün fiyat ve stok bilgileri güncellendi',
                    'api_response': response_data
                })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Hata: update_price_stock - {e}")
        return jsonify({'success': False, 'error': str(e)}), 500