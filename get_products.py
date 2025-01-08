import asyncio
import aiohttp
from trendyol_api import API_KEY, SUPPLIER_ID, API_SECRET, BASE_URL
from models import Product, ProductArchive
from sqlalchemy.dialects.postgresql import insert
import os
import base64
import json
from dotenv import load_dotenv
import logging
from models import db, Product
from sqlalchemy import func
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from trendyol_api import API_KEY, SUPPLIER_ID, API_SECRET, BASE_URL
from login_logout import roles_required
import qrcode
from io import BytesIO
from flask import send_file

get_products_bp = Blueprint('get_products', __name__)

# Çevresel değişkenleri yükle
load_dotenv()

# Loglama ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Log seviyesini DEBUG olarak ayarladık
handler = logging.FileHandler('get_products.log')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


@get_products_bp.route('/generate_qr')
def generate_qr():
    """
    Trendyol'dan gelen barkod ile QR kod oluştur ve döndür.
    """
    barcode = request.args.get('barcode', '').strip()
    if not barcode:
        return jsonify({'success': False, 'message': 'Barkod eksik!'})

    # QR kod oluşturma
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(barcode)
    qr.make(fit=True)

    # QR kodu kaydet
    qr_dir = os.path.join('static', 'qr_codes')
    os.makedirs(qr_dir, exist_ok=True)
    qr_path = os.path.join(qr_dir, f"{barcode}.png")
    qr.make_image(fill_color="black", back_color="white").save(qr_path)

    # QR kod görselinin göreli yolunu döndür
    return jsonify({'success': True, 'qr_code_path': f"/static/qr_codes/{barcode}.png"})
    

# Yardımcı Fonksiyonlar
def group_products_by_model_and_color(products):
    grouped_products = {}
    for product in products:
        key = (product.product_main_id or '', product.color or '')
        grouped_products.setdefault(key, []).append(product)
    return grouped_products

def sort_variants_by_size(product_group):
    """
    Bedenleri büyükten küçüğe doğru sıralar.
    """
    try:
        return sorted(product_group, key=lambda x: float(x.size), reverse=True)
    except (ValueError, TypeError):
        # Eğer bedenler numerik değilse, alfabetik olarak ters sırada sıralar
        return sorted(product_group, key=lambda x: x.size, reverse=True)

def render_product_list(products, pagination=None):
    grouped_products = group_products_by_model_and_color(products)
    # Varyantları bedenlere göre sıralayalım
    for key in grouped_products:
        grouped_products[key] = sort_variants_by_size(grouped_products[key])
    return render_template(
        'product_list.html',
        grouped_products=grouped_products,
        pagination=pagination,
        search_mode=False
    )

@get_products_bp.route('/update_products', methods=['POST'])
async def update_products_route():
    try:
        logger.debug("update_products_route fonksiyonu çağrıldı.")
        print("DEBUG: update_products_route başladı.")

        # Trendyol API'den ürünleri çekiyoruz
        products = await fetch_all_products_async()

        if not isinstance(products, list):
            logger.error(f"Beklenmeyen veri türü: {type(products)} - İçerik: {products}")
            print(f"ERROR: Beklenmeyen veri türü: {type(products)} - İçerik: {products}")
            raise ValueError("Beklenen liste değil.")

        logger.debug(f"Çekilen ürün sayısı: {len(products)}")
        print(f"DEBUG: Çekilen ürün sayısı: {len(products)}")

        if products:
            logger.debug("Ürünler veritabanına kaydediliyor...")
            print("DEBUG: Ürünler veritabanına kaydediliyor...")
            await save_products_to_db_async(products)
            flash('Ürünler başarıyla güncellendi.', 'success')
            logger.info("Ürünler başarıyla güncellendi.")
            print("INFO: Ürünler başarıyla güncellendi.")
        else:
            logger.warning("Ürünler bulunamadı veya güncelleme sırasında bir hata oluştu.")
            print("WARNING: Ürünler bulunamadı veya güncelleme sırasında bir hata oluştu.")
            flash('Ürünler bulunamadı veya güncelleme sırasında bir hata oluştu.', 'danger')

    except Exception as e:
        logger.error(f"update_products_route hata: {e}")
        print(f"ERROR: update_products_route hata: {e}")
        flash('Ürünler güncellenirken bir hata oluştu.', 'danger')

    logger.debug("update_products_route tamamlandı, product_list sayfasına yönlendiriliyor.")
    print("DEBUG: update_products_route tamamlandı, product_list sayfasına yönlendiriliyor.")
    return redirect(url_for('get_products.product_list'))


async def fetch_all_products_async():
    page_size = 1000  # Trendyol API'nin desteklediği maksimum boyut
    url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/products"
    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

    headers = {"Authorization": f"Basic {encoded_credentials}"}

    async with aiohttp.ClientSession() as session:
        # İlk isteği yaparak toplam sayfa sayısını alalım
        params = {"page": 0, "size": page_size}
        async with session.get(url, headers=headers, params=params, timeout=30) as response:
            if response.status != 200:
                error_text = await response.text()
                logging.error(f"API Hatası: {response.status} - {error_text}")
                return []
            try:
                data = await response.json()
                logging.debug(f"API Yanıtı: Tür: {type(data)}, İçerik: {data}")
            except Exception as e:
                error_text = await response.text()
                logging.error(f"JSON çözümleme hatası: {e} - Yanıt: {error_text}")
                return []

            # Toplam sayfa sayısını belirleme
            total_pages = data.get('totalPages', 1)
            logging.info(f"Toplam sayfa sayısı: {total_pages}")

        # Paralel olarak sayfaları çekmek için görevler oluştur
        tasks = [
            fetch_products_page(session, url, headers, {"page": page_number, "size": page_size})
            for page_number in range(total_pages)
        ]

        # Paralel işlemleri başlat
        pages_data = await asyncio.gather(*tasks)

        # Gelen tüm verileri birleştir
        all_products = [product for page in pages_data if isinstance(page, list) for product in page]

        logging.info(f"Toplam çekilen ürün sayısı: {len(all_products)}")
        return all_products


async def fetch_products_page(session, url, headers, params):
    try:
        async with session.get(url, headers=headers, params=params, timeout=30) as response:
            if response.status != 200:
                error_text = await response.text()
                logging.error(f"Sayfa çekme hatası: {response.status} - {error_text}")
                return []
            try:
                data = await response.json()
                if not isinstance(data.get('content'), list):
                    logging.error(f"Sayfa verisi `content` beklenen bir liste değil: {type(data.get('content'))}")
                    return []
                logging.debug(f"Sayfa {params['page']} başarıyla çekildi, içerik boyutu: {len(data['content'])}")
                return data.get('content', [])
            except Exception as e:
                error_text = await response.text()
                logging.error(f"JSON çözümleme hatası: {e} - Yanıt: {error_text}")
                return []
    except Exception as e:
        logging.error(f"fetch_products_page hata: {e}")
        return []



# Asenkron resim indirme fonksiyonu
async def download_images_async(image_urls):
    async with aiohttp.ClientSession() as session:
        tasks = []
        semaphore = asyncio.Semaphore(100)  # Aynı anda maksimum 10 istek
        for image_url, image_path in image_urls:
            tasks.append(download_image(session, image_url, image_path, semaphore))
        await asyncio.gather(*tasks)

async def download_image(session, image_url, image_path, semaphore):
    async with semaphore:
        if os.path.exists(image_path):
            logger.info(f"Resim zaten mevcut, atlanıyor: {image_path}")
            return
        try:
            async with session.get(image_url, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"Resim indirme hatası: {response.status} - {image_url}")
                    return
                content = await response.read()
                with open(image_path, 'wb') as img_file:
                    img_file.write(content)
                logger.info(f"Resim kaydedildi: {image_path}")
        except Exception as e:
            logger.error(f"Resim indirme sırasında hata oluştu ({image_url}): {e}")



# Ürünleri veritabanına kaydeden ve resimleri indiren fonksiyon
import threading

def background_download_images(image_downloads):
    # Asenkron indirme fonksiyonunu buradan çağır
    asyncio.run(download_images_async(image_downloads))

async def save_products_to_db_async(products):
    products = [product for product in products if isinstance(product, dict)]
    
    # Arşivdeki ürün barkodlarını al
    archived_barcodes = set(p.original_product_barcode for p in ProductArchive.query.all())
    
    # Arşivde olan ürünleri filtrele
    products = [p for p in products if p.get('barcode') not in archived_barcodes]

    if not products:
        logger.warning("Kaydedilecek ürün yok.")
        flash("Kaydedilecek ürün bulunamadı.", "warning")
        return

    images_folder = os.path.join('static', 'images')
    os.makedirs(images_folder, exist_ok=True)

    from urllib.parse import urlparse
    image_downloads = []
    product_objects = []

    for index, product_data in enumerate(products):
        try:
            quantity = int(product_data.get('quantity', 0))
            original_barcode = product_data.get('barcode', 'N/A')
            if not original_barcode:
                logger.warning(f"Barkod eksik, ürün atlanıyor: {product_data}")
                continue

            image_urls = [image.get('url', '') for image in product_data.get('images', []) if isinstance(image, dict)]
            image_url = image_urls[0] if image_urls else ''
            if image_url:
                parsed_url = urlparse(image_url)
                image_extension = os.path.splitext(parsed_url.path)[1]
                if not image_extension:
                    image_extension = '.jpg'
                image_extension = image_extension.lower()

                image_filename = f"{original_barcode}{image_extension}"
                image_path = os.path.join(images_folder, image_filename)
                image_downloads.append((image_url, image_path))
                product_data['images'] = f"/static/images/{image_filename}"

            size = next((attr.get('attributeValue', 'N/A') for attr in product_data.get('attributes', []) if attr.get('attributeName') == 'Beden'), 'N/A')
            color = next((attr.get('attributeValue', 'N/A') for attr in product_data.get('attributes', []) if attr.get('attributeName') == 'Renk'), 'N/A')
            reject_reason = product_data.get('rejectReasonDetails', [])
            reject_reason_str = '; '.join([reason.get('reason', 'N/A') for reason in reject_reason])

            product = {
                "barcode": original_barcode,
                "original_product_barcode": original_barcode,
                "title": product_data.get('title', 'N/A'),
                "product_main_id": product_data.get('productMainId', 'N/A'),
                "quantity": quantity,
                "images": product_data.get('images', ''),
                "variants": json.dumps(product_data.get('variants', [])),
                "size": size,
                "color": color,
                "archived": product_data.get('archived', False),
                "locked": product_data.get('locked', False),
                "on_sale": product_data.get('onSale', False),
                "reject_reason": reject_reason_str,
                "sale_price": float(product_data.get('salePrice', 0)),
                "list_price": float(product_data.get('listPrice', 0)),
                "currency_type": product_data.get('currencyType', 'TRY'),
            }
            product_objects.append(product)

        except Exception as e:
            logger.error(f"Ürün işlenirken hata (index {index}): {e}")
            continue

    # Upsert işlemi
    upsert_products(product_objects)
    flash("Ürünler başarıyla veritabanına kaydedildi.", "success")

    # Varolan dosyaları atla, sadece eksikleri indir
    image_downloads = check_and_prepare_image_downloads(image_downloads, images_folder)
    if image_downloads:
        logger.info("Resim indirme işlemleri arka planda başlatılıyor...")
        # Thread başlat
        threading.Thread(target=background_download_images, args=(image_downloads,)).start()

        

def check_and_prepare_image_downloads(image_urls, images_folder):
    existing_files = set(os.listdir(images_folder))
    download_list = []

    for image_url, image_path in image_urls:
        image_filename = os.path.basename(image_path)
        if image_filename not in existing_files:  # Mevcut dosyaları atla
            download_list.append((image_url, image_path))

    return download_list



def upsert_products(products):
    insert_stmt = insert(Product).values(products)
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=['barcode'],  # Çakışma kontrolü için benzersiz alan
        set_={
            'quantity': insert_stmt.excluded.quantity,
            'sale_price': insert_stmt.excluded.sale_price,
            'list_price': insert_stmt.excluded.list_price,
            'images': insert_stmt.excluded.images,
            'size': insert_stmt.excluded.size,
            'color': insert_stmt.excluded.color,
        }
    )
    db.session.execute(upsert_stmt)
    db.session.commit()



# Ürün stoklarını asenkron güncelleme fonksiyonu
async def update_stock_levels_with_items_async(items):
    if not items:
        logger.error("Güncellenecek ürün bulunamadı.")
        return False

    url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/products/price-and-inventory"
    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/json"
    }

    # Veritabanından ürünleri çekme
    product_dict = {product.original_product_barcode: product for product in Product.query.all()}
    logger.info(f"Veritabanındaki ürün sayısı: {len(product_dict)}")

    payload_items = []
    for item in items:
        barcode = item['barcode']
        quantity = item['quantity']

        logger.info(f"İşlenen barkod: {barcode}, miktar: {quantity}")

        product_info = product_dict.get(barcode)
        if product_info:
            try:
                sale_price = float(product_info.sale_price or 0)
                list_price = float(product_info.list_price or 0)
                currency_type = product_info.currency_type or 'TRY'

                logger.info(f"Ürün bilgileri - Barkod: {barcode}, Satış Fiyatı: {sale_price}, Liste Fiyatı: {list_price}, Döviz Cinsi: {currency_type}")

                payload_item = {
                    "barcode": barcode,
                    "quantity": quantity,
                    "salePrice": sale_price,
                    "listPrice": list_price,
                    "currencyType": currency_type
                }
                payload_items.append(payload_item)

            except ValueError as e:
                logger.error(f"Fiyat bilgileri hatalı: {e}")
                continue
        else:
            logger.warning(f"Barkod için ürün bulunamadı: {barcode}")
            continue

    logger.info(f"API'ye gönderilecek ürün sayısı: {len(payload_items)}")

    payload = {"items": payload_items}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=payload, timeout=30) as response:
                if response.status != 200:
                    logger.error(f"HTTP Hatası: {response.status}, Yanıt: {await response.text()}")
                    return False
                data = await response.json()
                logger.info(f"API yanıtı: {data}")

                batch_request_id = data.get('batchRequestId')
                if batch_request_id:
                    logger.info("Ürünler API üzerinden başarıyla güncellendi.")
                    return True
                else:
                    logger.error("Batch Request ID alınamadı.")
                    return False

        except aiohttp.ClientError as e:
            logger.error(f"İstek Hatası: {e}")
            return False

# Rotalar

@get_products_bp.route('/fetch-products')
async def fetch_products_route():
    """
    Ürünleri Trendyol API'den çeker ve veritabanına kaydeder.
    """
    try:
        products = await fetch_all_products_async()
        if products:
            await save_products_to_db_async(products)
            flash('Ürünler başarıyla güncellendi.', 'success')
        else:
            flash('Ürünler bulunamadı veya güncelleme sırasında bir hata oluştu.', 'danger')
    except Exception as e:
        logger.error(f"fetch_products_route hata: {e}")
        flash('Ürünler güncellenirken bir hata oluştu.', 'danger')

    return redirect(url_for('get_products.product_list'))

@get_products_bp.route('/archive_product', methods=['POST'])
def archive_product():
    try:
        product_main_id = request.form.get('product_main_id')
        if not product_main_id:
            return jsonify({'success': False, 'message': 'Model kodu gerekli'})

        # Model koduna ait tüm ürünleri bul
        products = Product.query.filter_by(product_main_id=product_main_id).all()
        
        if not products:
            return jsonify({'success': False, 'message': 'Ürün bulunamadı'})

        # Ürünleri arşive taşı
        for product in products:
            archive_product = ProductArchive(
                barcode=product.barcode,
                original_product_barcode=product.original_product_barcode,
                title=product.title,
                product_main_id=product.product_main_id,
                quantity=product.quantity,
                images=product.images,
                variants=product.variants,
                size=product.size,
                color=product.color,
                archived=True,
                locked=product.locked,
                on_sale=product.on_sale,
                reject_reason=product.reject_reason,
                sale_price=product.sale_price,
                list_price=product.list_price,
                currency_type=product.currency_type
            )
            db.session.add(archive_product)
            db.session.delete(product)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Ürünler başarıyla arşivlendi'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@get_products_bp.route('/restore_from_archive', methods=['POST'])
def restore_from_archive():
    try:
        product_main_id = request.form.get('product_main_id')
        if not product_main_id:
            return jsonify({'success': False, 'message': 'Model kodu gerekli'})

        # Arşivden ürünleri bul
        archived_products = ProductArchive.query.filter_by(product_main_id=product_main_id).all()
        
        if not archived_products:
            return jsonify({'success': False, 'message': 'Arşivde ürün bulunamadı'})

        # Ürünleri arşivden çıkar
        for archived in archived_products:
            product = Product(
                barcode=archived.barcode,
                original_product_barcode=archived.original_product_barcode,
                title=archived.title,
                product_main_id=archived.product_main_id,
                quantity=archived.quantity,
                images=archived.images,
                variants=archived.variants,
                size=archived.size,
                color=archived.color,
                archived=False,
                locked=archived.locked,
                on_sale=archived.on_sale,
                reject_reason=archived.reject_reason,
                sale_price=archived.sale_price,
                list_price=archived.list_price,
                currency_type=archived.currency_type
            )
            db.session.add(product)
            db.session.delete(archived)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Ürünler başarıyla arşivden çıkarıldı'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@get_products_bp.route('/product_list')
def product_list():
    """
    Ürün listesini sayfalar halinde gösterir.
    """
    try:
        products = Product.query.all()
    except Exception as e:
        logger.error(f"Ürünler veritabanından çekilirken bir hata oluştu: {e}")
        flash("Ürünler bulunamadı veya veritabanı okunamadı.", "danger")
        return render_template('error.html', message="Ürün bulunamadı.")

    grouped_products = group_products_by_model_and_color(products)

    page = request.args.get('page', 1, type=int)
    per_page = 12
    total_groups = len(grouped_products)

    # Model ve renge göre sıralama
    sorted_keys = sorted(grouped_products.keys(), key=lambda x: (x[0], x[1]))
    
    # Sayfalama için başlangıç ve bitiş indekslerini hesapla
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    # Sayfalanmış anahtarları al
    paginated_keys = sorted_keys[start_idx:end_idx]
    
    # Sayfalanmış ürün gruplarını oluştur
    paginated_product_groups = {key: sort_variants_by_size(grouped_products[key]) for key in paginated_keys}

    # Toplam sayfa sayısını hesapla
    total_pages = (total_groups + per_page - 1) // per_page

    return render_template(
        'product_list.html',
        grouped_products=paginated_product_groups,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        search_mode=False,
        current_page=page,
        has_next=page < total_pages,
        has_prev=page > 1
    )

@get_products_bp.route('/get_product_variants', methods=['GET'])
def get_product_variants():
    """
    Belirli bir model ve renge ait ürün varyantlarını bedenlere göre sıralayarak JSON formatında döndürür.
    """
    model_id = request.args.get('model', '').strip()
    color = request.args.get('color', '').strip()

    logger.info(f"Gelen istek - Model: {model_id}, Renk: {color}")

    if not model_id or not color:
        logger.warning("Model veya renk bilgisi eksik.")
        return jsonify({'success': False, 'message': 'Model veya renk bilgisi eksik.'})

    products = Product.query.filter(
        func.lower(Product.product_main_id) == model_id.lower(),
        func.lower(Product.color) == color.lower()
    ).all()

    products_list = []

    if products:
        for p in products:
            if not p.original_product_barcode or p.quantity is None:
                logger.warning(f"Eksik veri - Barkod: {p.original_product_barcode}, Stok: {p.quantity}")
                continue

            products_list.append({
                'size': p.size,
                'original_product_barcode': p.original_product_barcode,
                'quantity': p.quantity
            })

        # Bedenlere göre sıralama
        try:
            products_list = sorted(products_list, key=lambda x: float(x['size']), reverse=True)
        except (ValueError, TypeError):
            products_list = sorted(products_list, key=lambda x: x['size'], reverse=True)

        logger.info(f"{len(products_list)} ürün bulundu.")
        return jsonify({'success': True, 'products': products_list})
    else:
        logger.warning("Ürün bulunamadı.")
        return jsonify({'success': False, 'message': 'Ürün bulunamadı.'})

@get_products_bp.route('/update_stocks_ajax', methods=['POST'])
async def update_stocks_ajax():
    """
    AJAX isteği ile gelen stok güncellemelerini işler.
    """
    form_data = request.form
    logger.info(f"Gelen stok güncelleme isteği: {form_data}")

    if not form_data:
        logger.error("Güncellenecek ürün bulunamadı.")
        return jsonify({'success': False, 'message': 'Güncellenecek ürün bulunamadı.'})

    items_to_update = []
    for barcode, quantity in form_data.items():
        try:
            items_to_update.append({
                'barcode': barcode,
                'quantity': int(quantity)
            })
            logger.info(f"Güncellenecek ürün - Barkod: {barcode}, Yeni Stok: {quantity}")
        except ValueError:
            logger.error(f"Geçersiz stok miktarı - Barkod: {barcode}, Girilen Miktar: {quantity}")
            return jsonify({'success': False, 'message': f"Barkod {barcode} için geçersiz miktar girdiniz."})

    # Stok güncelleme işlemini asenkron gerçekleştir
    result = await update_stock_levels_with_items_async(items_to_update)

    if result:
        logger.info("Stoklar başarıyla güncellendi.")
        return jsonify({'success': True})
    else:
        logger.error("Stok güncelleme başarısız oldu.")
        return jsonify({'success': False, 'message': 'Stok güncelleme başarısız oldu.'})

@get_products_bp.route('/search', methods=['GET'])
def search_products():
    """
    Ürün arama fonksiyonu. Model kodu veya barkod ile arama yapar.
    """
    query = request.args.get('query', '').strip()
    if not query:
        return redirect(url_for('get_products.product_list'))

    # Hem model kodu hem de barkod ile arama yap
    products = Product.query.filter(
        db.or_(
            Product.product_main_id == query,
            Product.barcode == query,
            Product.original_product_barcode == query
        )
    ).all()
    if not products:
        flash("Arama kriterlerine uygun ürün bulunamadı.", "warning")
        return redirect(url_for('get_products.product_list'))

    grouped_products = group_products_by_model_and_color(products)

    # Varyantları bedenlere göre sıralayalım
    for key in grouped_products:
        grouped_products[key] = sort_variants_by_size(grouped_products[key])

    return render_template(
        'product_list.html',
        grouped_products=grouped_products,
        search_mode=True
    )




# Ürün Etiketi Rotası
@get_products_bp.route('/product_label')
def product_label():
    return render_template('product_label.html')
