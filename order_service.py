from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
import asyncio
import aiohttp
import base64
import json
import traceback
import logging
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
import threading

# Tablolar: Created, Picking, Shipped, Delivered, Cancelled, Archive
from models import db, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled, OrderArchived

# Trendyol API kimlik bilgileri
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID

# İsteğe bağlı: Sipariş detayı işleme, update service
from order_list_service import process_order_details
from update_service import update_package_to_picking

# Blueprint
order_service_bp = Blueprint('order_service', __name__)

# Log ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('order_service.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


############################
# Sipariş Statüsü -> Model eşlemesi
############################
STATUS_TABLE_MAP = {
    'Created': OrderCreated,
    'Picking': OrderPicking,
    'Invoiced': OrderPicking,  # Invoiced da picking’e gitsin
    'Shipped': OrderShipped,
    'Delivered': OrderDelivered,
    'Cancelled': OrderCancelled
}


############################
# 1) Trendyol'dan Sipariş Çekme (Asenkron)
############################
@order_service_bp.route('/fetch-trendyol-orders', methods=['POST'])
def fetch_trendyol_orders_route():
    """
    UI veya Postman vb. üzerinden tetiklenen endpoint.
    Asenkron olarak Trendyol siparişlerini çeker.
    """
    try:
        asyncio.run(fetch_trendyol_orders_async())
        flash('Siparişler başarıyla güncellendi!', 'success')
    except Exception as e:
        logger.error(f"Hata: fetch_trendyol_orders_route - {e}")
        traceback.print_exc()
        flash('Siparişler güncellenirken bir hata oluştu.', 'danger')
    return redirect(url_for('order_list_service.order_list_all'))


async def fetch_trendyol_orders_async():
    """
    Trendyol API'ye asenkron istek atar, tüm sayfaları paralel çekip
    process_all_orders fonksiyonuna iletir.
    """
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"https://api.trendyol.com/sapigw/suppliers/{SUPPLIER_ID}/orders"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        # size=500 diyerek daha az sayfa ile çekme (performans için)
        params = {
            "status": "Created,Picking,Invoiced,Shipped,Delivered,Cancelled",
            "page": 0,
            "size": 500,
            "orderByField": "PackageLastModifiedDate",
            "orderByDirection": "DESC"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                data = await response.json()
                if response.status != 200:
                    print(f"API Error: {response.status} - {data}")
                    return

                total_elements = data.get('totalElements', 0)
                total_pages = data.get('totalPages', 1)
                print(f"Toplam sipariş sayısı: {total_elements}, Toplam sayfa sayısı: {total_pages}")

                # Aynı anda en fazla 10 istek
                from asyncio import Semaphore
                semaphore = Semaphore(10)
                tasks = []
                for page_number in range(total_pages):
                    params_page = params.copy()
                    params_page['page'] = page_number
                    task = fetch_orders_page(session, url, headers, params_page, semaphore)
                    tasks.append(task)

                pages_data = await asyncio.gather(*tasks)
                all_orders_data = []
                for orders in pages_data:
                    all_orders_data.extend(orders)

                print(f"Toplam çekilen sipariş sayısı: {len(all_orders_data)}")
                process_all_orders(all_orders_data)

    except Exception as e:
        print(f"Hata: fetch_trendyol_orders_async - {e}")
        traceback.print_exc()


async def fetch_orders_page(session, url, headers, params, semaphore):
    """
    Belirli sayfadaki siparişleri asenkron çekme fonksiyonu.
    """
    async with semaphore:
        try:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    print(f"API isteği başarısız oldu: {response.status} - {await response.text()}")
                    return []
                data = await response.json()
                return data.get('content', [])
        except Exception as e:
            print(f"Hata: fetch_orders_page - {e}")
            return []


############################
# 2) Gelen Siparişleri İşleme
############################
def process_all_orders(all_orders_data):
    """
    - Tüm siparişler için tablo hareketlerini minimal sorgu ve tek transaction ile yapar.
      * Tek seferde 5 tabloyu order_number IN(...) ile sorgular.
      * Her siparişi tabloya göre update/insert/taşıma yapar.
      * En sonda tek commit.
    - Arka planda Shipped/Delivered siparişlerini ayrı bir thread’de işleyebilir.
    """
    try:
        if not all_orders_data:
            logger.info("Hiç sipariş gelmedi.")
            return

        # 1) Arşiv kontrolü
        archived_list = OrderArchived.query.all()
        archived_set = {o.order_number for o in archived_list}

        # 2) Tüm order_number'ları set olarak alalım:
        order_numbers = set(str(od.get('orderNumber') or od.get('id')) for od in all_orders_data)

        # 3) 5 tabloyu tek sorguda çek:
        existing_created   = OrderCreated.query.filter(OrderCreated.order_number.in_(order_numbers)).all()
        existing_picking   = OrderPicking.query.filter(OrderPicking.order_number.in_(order_numbers)).all()
        existing_shipped   = OrderShipped.query.filter(OrderShipped.order_number.in_(order_numbers)).all()
        existing_delivered = OrderDelivered.query.filter(OrderDelivered.order_number.in_(order_numbers)).all()
        existing_cancelled = OrderCancelled.query.filter(OrderCancelled.order_number.in_(order_numbers)).all()

        # Dictionary map: order_number -> (model_instance, tablo_sinifi)
        created_map   = {row.order_number: (row, OrderCreated)   for row in existing_created}
        picking_map   = {row.order_number: (row, OrderPicking)   for row in existing_picking}
        shipped_map   = {row.order_number: (row, OrderShipped)   for row in existing_shipped}
        delivered_map = {row.order_number: (row, OrderDelivered) for row in existing_delivered}
        cancelled_map = {row.order_number: (row, OrderCancelled) for row in existing_cancelled}

        def find_existing_order_in_maps(onum):
            if onum in created_map:
                return created_map[onum]
            if onum in picking_map:
                return picking_map[onum]
            if onum in shipped_map:
                return shipped_map[onum]
            if onum in delivered_map:
                return delivered_map[onum]
            if onum in cancelled_map:
                return cancelled_map[onum]
            return None, None

        # 4) Siparişleri duruma göre gruplayalım
        sync_orders_grouped = {}  # new eklenecek siparişler: {model_cls: [dict_data, ...]}
        bg_orders = []            # Shipped / Delivered arka planda işlenecekler
        processed = set()

        for od in all_orders_data:
            order_number = str(od.get('orderNumber') or od.get('id'))
            if order_number in processed:
                continue
            processed.add(order_number)

            if order_number in archived_set:
                logger.info(f"{order_number} arşivde, atlanıyor.")
                continue

            st = (od.get('status') or '').strip()
            target_model = STATUS_TABLE_MAP.get(st)

            if st in ('Created', 'Picking', 'Invoiced'):
                old_obj, old_model = find_existing_order_in_maps(order_number)
                if old_obj:
                    # Zaten tabloda var, belki tablo taşıma gerekebilir:
                    if old_model != target_model:
                        # Tablolar arası taşıma
                        move_order_between_tables_in_memory(order_number, old_obj, old_model, target_model)
                        # Yeni tabloya taşındıktan sonra update
                        new_rec = target_model.query.filter_by(order_number=order_number).first()
                        if new_rec:
                            update_existing_order_minimal(new_rec, od, commit_immediately=False)
                    else:
                        # Sadece minimal update
                        update_existing_order_minimal(old_obj, od, commit_immediately=False)
                else:
                    # Yepyeni sipariş
                    new_data = combine_line_items(od, st)
                    sync_orders_grouped.setdefault(target_model, []).append(new_data)

            elif st in ('Shipped', 'Delivered'):
                bg_orders.append(od)

            else:
                logger.warning(f"{order_number} - işlenmeyen statü: {st}")

        # 5) Senkron bulk insert işlemi
        for model_cls, orders_data in sync_orders_grouped.items():
            if orders_data:
                db.session.bulk_insert_mappings(model_cls, orders_data)
                logger.info(f"{len(orders_data)} yeni sipariş {model_cls.__tablename__} tablosuna eklendi (bulk_insert).")

        # 6) Tek commit
        db.session.commit()
        logger.info("Senkron siparişler işleme alındı ve commit edildi.")

        # 7) Arka plan işlemleri: Shipped / Delivered
        if bg_orders:
            app = current_app._get_current_object()
            thread = threading.Thread(target=process_bg_orders, args=(bg_orders, app))
            thread.start()

    except SQLAlchemyError as e:
        logger.error(f"Veritabanı hatası: {e}")
        db.session.rollback()
    except Exception as e:
        logger.error(f"Hata: process_all_orders - {e}")
        traceback.print_exc()
        db.session.rollback()


def process_bg_orders(bg_orders, app):
    """
    Shipped ve Delivered siparişlerini arka planda işleyen fonksiyon.
    Bu fonksiyon, ayrı bir thread içinde çalışır ve tek seferde commit yapılır.
    """
    with app.app_context():
        try:
            if not bg_orders:
                return

            # Tek seferde tablo sorgusu için:
            order_numbers = set(str(od.get('orderNumber') or od.get('id')) for od in bg_orders)

            existing_created   = OrderCreated.query.filter(OrderCreated.order_number.in_(order_numbers)).all()
            existing_picking   = OrderPicking.query.filter(OrderPicking.order_number.in_(order_numbers)).all()
            existing_shipped   = OrderShipped.query.filter(OrderShipped.order_number.in_(order_numbers)).all()
            existing_delivered = OrderDelivered.query.filter(OrderDelivered.order_number.in_(order_numbers)).all()
            existing_cancelled = OrderCancelled.query.filter(OrderCancelled.order_number.in_(order_numbers)).all()

            created_map   = {r.order_number: (r, OrderCreated)   for r in existing_created}
            picking_map   = {r.order_number: (r, OrderPicking)   for r in existing_picking}
            shipped_map   = {r.order_number: (r, OrderShipped)   for r in existing_shipped}
            delivered_map = {r.order_number: (r, OrderDelivered) for r in existing_delivered}
            cancelled_map = {r.order_number: (r, OrderCancelled) for r in existing_cancelled}

            def find_existing_bg(onum):
                if onum in created_map:
                    return created_map[onum]
                if onum in picking_map:
                    return picking_map[onum]
                if onum in shipped_map:
                    return shipped_map[onum]
                if onum in delivered_map:
                    return delivered_map[onum]
                if onum in cancelled_map:
                    return cancelled_map[onum]
                return None, None

            for od in bg_orders:
                order_number = str(od.get('orderNumber') or od.get('id'))
                st = (od.get('status') or '').strip()

                old_obj, old_model = find_existing_bg(order_number)
                if not old_obj:
                    # Eğer arka planda tablo yoksa, Shipped ise ekleyebiliriz.
                    if st == 'Shipped':
                        new_data = combine_line_items(od, 'Shipped')
                        db.session.bulk_insert_mappings(OrderShipped, [new_data])
                        logger.info(f"Yeni shipped sipariş (arka plan) eklendi: {order_number}")
                    continue

                # Eğer Delivered ise Shipped tablosundan Delivered tablosuna taşı
                if st == 'Delivered' and old_model == OrderShipped:
                    move_order_between_tables_in_memory(order_number, old_obj, old_model, OrderDelivered)
                    logger.info(f"{order_number} shipped'den delivered'a taşındı (arka plan).")

            db.session.commit()
            logger.info("Arka plan siparişleri tamamlandı ve commit edildi.")

        except Exception as e:
            logger.error(f"Hata (process_bg_orders): {e}")
            db.session.rollback()


############################
# Tablolar Arası Taşıma (Commit'siz)
############################
def move_order_between_tables_in_memory(order_number, old_rec, old_model, new_model):
    """
    Siparişin kaydını eski tablodan silip, verilerini yeni tabloya taşır.
    Tek transaction kapsamında commit etmez, process_all_orders sonunda commit edilecek.
    """
    if not old_rec:
        logger.error(f"Sipariş bulunamadı: {order_number} ({old_model.__tablename__})")
        return

    data = old_rec.__dict__.copy()
    data.pop('_sa_instance_state', None)

    new_cols = set(new_model.__table__.columns.keys())
    data = {k: v for k, v in data.items() if k in new_cols}

    new_rec = new_model(**data)
    db.session.add(new_rec)
    db.session.delete(old_rec)
    logger.info(f"Sipariş taşındı: {order_number} -> {new_model.__tablename__}")


############################
# 3) Minimal Update Mantığı (Commit Etme)
############################
def update_existing_order_minimal(order_obj, order_data, commit_immediately=False):
    """
    - Delivered/Cancelled ise barkodu güncelleme
    - Shipped ise sadece statüyü güncelle
    - Created/Picking/Invoiced ise barkodu silip yeniden ekle
    - commit_immediately=False: Biriktiriyoruz, en sonda toplu commit.
    """
    new_status = (order_data.get('status') or '').strip()

    # Halihazırda Delivered/Cancelled ise dokunma
    if order_obj.status in ('Delivered', 'Cancelled'):
        logger.info(f"{order_obj.order_number} zaten {order_obj.status}, güncellenmedi.")
        return

    # Eğer Delivered/Cancelled ise tabloya göre taşıma ya da güncelleme yapalım
    if new_status in ('Delivered', 'Cancelled'):
        # Eğer başka bir tablodaysa, Delivered/Cancelled için doğru tabloya taşıyalım
        if (new_status == 'Delivered' and not isinstance(order_obj, OrderDelivered)) or \
           (new_status == 'Cancelled' and not isinstance(order_obj, OrderCancelled)):
            target_cls = OrderDelivered if new_status == 'Delivered' else OrderCancelled
            move_order_between_tables_in_memory(order_obj.order_number, order_obj, type(order_obj), target_cls)
            logger.info(f"{order_obj.order_number} -> {new_status} tablosuna taşındı.")
            # Taşıma işleminden sonra barkod güncellemeden çıkabilirisiniz
            if commit_immediately:
                db.session.commit()
            return
        # Zaten doğru tablodaysa sadece statü güncellemesi
        else:
            order_obj.status = new_status
            if commit_immediately:
                db.session.commit()
            logger.info(f"{order_obj.order_number} -> statü {new_status}, barkod güncellenmedi.")
            return

    # Shipped ise doğru tabloya taşıma ve güncelleme
    if new_status == 'Shipped':
        # Farklı bir tablodaysa Shipped tablosuna taşı
        if not isinstance(order_obj, OrderShipped):
            move_order_between_tables_in_memory(order_obj.order_number, order_obj, type(order_obj), OrderShipped)
            logger.info(f"{order_obj.order_number} -> Shipped tablosuna taşındı.")
            if commit_immediately:
                db.session.commit()
            return
        # Zaten Shipped tablosunda ise sadece statü güncellemesi
        else:
            order_obj.status = 'Shipped'
            if commit_immediately:
                db.session.commit()
            logger.info(f"{order_obj.order_number} -> Shipped yapıldı, barkod güncellenmedi.")
            return

    # Geri kalan (Created, Picking, Invoiced) barkod vs. sıfırla ve yeniden doldur
    order_obj.merchant_sku = ''
    order_obj.product_barcode = ''
    order_obj.original_product_barcode = ''
    order_obj.line_id = ''
    order_obj.quantity = 0
    order_obj.commission = 0.0
    order_obj.status = new_status

    lines = order_data.get('lines', [])
    new_skus, new_bcs, new_obcs, new_lids = [], [], [], []

    for li in lines:
        qty = safe_int(li.get('quantity'), 1)
        cf = safe_float(li.get('commissionFee'), 0.0)
        order_obj.quantity += qty
        order_obj.commission += cf

        msku = li.get('merchantSku', '')
        original_bc = li.get('barcode', '')
        converted_bc = replace_turkish_characters_cached(original_bc)
        lid = str(li.get('id', ''))

        if msku: new_skus.append(msku)
        if converted_bc: new_bcs.append(converted_bc)
        if original_bc: new_obcs.append(original_bc)
        if lid: new_lids.append(lid)

    order_obj.merchant_sku = ', '.join(new_skus)
    order_obj.product_barcode = ', '.join(new_bcs)
    order_obj.original_product_barcode = ', '.join(new_obcs)
    order_obj.line_id = ', '.join(new_lids)

    from json import dumps
    details_dict = create_order_details(lines)
    order_obj.details = dumps(details_dict, ensure_ascii=False)

    if commit_immediately:
        db.session.commit()

    logger.info(f"{order_obj.order_number} -> {new_status}, barkod güncellendi.")


############################
# 4) Yardımcı Fonksiyonlar
############################

# Basit int/float convert fonksiyonları
def safe_int(val, default=0):
    try:
        return int(val)
    except:
        return default

def safe_float(val, default=0.0):
    try:
        return float(val)
    except:
        return default


# Basit bir cache kullanarak aynı metin tekrar dönüştürüldüğünde hız kazanın
_turkish_replace_cache = {}

def replace_turkish_characters_cached(text):
    if not isinstance(text, str):
        return text
    if text in _turkish_replace_cache:
        return _turkish_replace_cache[text]

    converted = replace_turkish_characters(text)
    _turkish_replace_cache[text] = converted
    return converted


def replace_turkish_characters(text):
    """
    Orijinal karakter dönüştürme fonksiyonunuz.
    """
    if not isinstance(text, str):
        return text
    replacements = str.maketrans({
        'A': '1', 'a': '1', 'B': '2', 'b': '2', 'C': '3', 'c': '3',
        'Ç': '4', 'ç': '4', 'D': '5', 'd': '5', 'E': '6', 'e': '6',
        'F': '7', 'f': '7', 'G': '8', 'g': '8', 'Ğ': '9', 'ğ': '9',
        'H': '1', 'h': '0', 'I': '1', 'ı': '1', 'İ': '1', 'i': '2',
        'J': '3', 'j': '1', 'K': '4', 'k': '4', 'L': '1', 'l': '5',
        'M': '6', 'm': '6', 'N': '1', 'n': '7', 'O': '8', 'o': '8',
        'Ö': '1', 'ö': '9', 'P': '0', 'p': '0', 'R': '1', 'r': '2',
        'S': '2', 's': '2', 'Ş': '3', 'ş': '3', 'T': '2', 't': '4',
        'U': '2', 'u': '2', 'Ü': '6', 'ü': '6', 'V': '7', 'v': '7',
        'Y': '8', 'y': '8', 'Z': '9', 'z': '9'
    })
    return text.translate(replacements)


def create_order_details(lines):
    """
    lines içindeki her bir barkod, color, size vb. birleştirir.
    Tekrarlı satırları quantity toplayarak tek entry haline getirir.
    """
    details_dict = {}
    total_quantity = 0
    for line in lines:
        bc = line.get('barcode', '')
        c = line.get('productColor', '')
        s = line.get('productSize', '')
        q = safe_int(line.get('quantity'), 1)
        total_quantity += q
        cf = safe_float(line.get('commissionFee'), 0.0)
        line_id = str(line.get('id', ''))

        key = (bc, c, s)
        if key not in details_dict:
            details_dict[key] = {
                'barcode': bc,
                'converted_barcode': replace_turkish_characters_cached(bc),
                'color': c,
                'size': s,
                'sku': line.get('merchantSku', ''),
                'productName': line.get('productName', ''),
                'productCode': str(line.get('productCode', '')),
                'product_main_id': str(line.get('productId', '')),
                'quantity': q,
                'total_price': safe_float(line.get('amount'), 0) * q,
                'line_id': line_id,
                'commissionFee': cf,
                'image_url': ''
            }
        else:
            details_dict[key]['quantity'] += q
            details_dict[key]['commissionFee'] += cf
            details_dict[key]['total_price'] += safe_float(line.get('amount'), 0) * q

    for det in details_dict.values():
        det['total_quantity'] = total_quantity

    return list(details_dict.values())


def combine_line_items(order_data, status):
    """
    Yeni sipariş eklemek için dict döndürür.
    Barkodları vs. virgülle birleştirir.
    """
    lines = order_data.get('lines', [])
    total_qty = 0
    commission_sum = 0.0
    bc_list = []

    for line in lines:
        q = safe_int(line.get('quantity'), 1)
        total_qty += q
        cf = safe_float(line.get('commissionFee'), 0.0)
        commission_sum += cf
        bc = line.get('barcode', '')
        for _ in range(q):
            bc_list.append(bc)

    cbc = [replace_turkish_characters_cached(x) for x in bc_list]

    from json import dumps
    details_list = create_order_details(lines)

    def ts_to_dt(ms):
        if not ms:
            return None
        return datetime.utcfromtimestamp(ms / 1000)

    return {
        'order_number': str(order_data.get('orderNumber', order_data.get('id'))),
        'order_date': ts_to_dt(order_data.get('orderDate')),
        'merchant_sku': ', '.join([x.get('merchantSku', '') for x in lines]),
        'product_barcode': ', '.join(cbc),
        'original_product_barcode': ', '.join(bc_list),
        'status': status,
        'line_id': ', '.join([str(x.get('id', '')) for x in lines]),
        'match_status': '',
        'customer_name': order_data.get('shipmentAddress', {}).get('firstName', ''),
        'customer_surname': order_data.get('shipmentAddress', {}).get('lastName', ''),
        'customer_address': order_data.get('shipmentAddress', {}).get('fullAddress', ''),
        'shipping_barcode': order_data.get('cargoTrackingNumber', ''),
        'product_name': ', '.join([x.get('productName', '') for x in lines]),
        'product_code': ', '.join([str(x.get('productCode', '')) for x in lines]),
        'amount': sum(safe_float(x.get('amount'), 0) for x in lines),
        'discount': sum(safe_float(x.get('discount'), 0) for x in lines),
        'currency_code': order_data.get('currencyCode', 'TRY'),
        'vat_base_amount': sum(safe_float(x.get('vatBaseAmount'), 0) for x in lines),
        'package_number': str(order_data.get('id', '')),
        'stockCode': ', '.join([x.get('merchantSku', '') for x in lines]),
        'estimated_delivery_start': ts_to_dt(order_data.get('estimatedDeliveryStartDate')),
        'images': '',
        'product_model_code': ', '.join([x.get('merchantSku', '') for x in lines]),
        'estimated_delivery_end': ts_to_dt(order_data.get('estimatedDeliveryEndDate')),
        'origin_shipment_date': ts_to_dt(order_data.get('originShipmentDate')),
        'product_size': ', '.join([x.get('productSize', '') for x in lines]),
        'product_main_id': ', '.join([str(x.get('productId', '')) for x in lines]),
        'cargo_provider_name': order_data.get('cargoProviderName', ''),
        'agreed_delivery_date': ts_to_dt(order_data.get('agreedDeliveryDate')),
        'product_color': ', '.join([x.get('productColor', '') for x in lines]),
        'cargo_tracking_link': order_data.get('cargoTrackingNumber', ''),
        'shipment_package_id': str(order_data.get('shipmentPackageId', '')),
        'details': dumps(details_list, ensure_ascii=False),
        'quantity': total_qty,
        'commission': commission_sum
    }


########################################
# Ek Rotalar: Created, Picking, Shipped, Delivered, Cancelled
########################################

@order_service_bp.route('/order-list/new', methods=['GET'])
def get_new_orders():
    page = request.args.get('page', 1, int)
    per_page = 50
    q = OrderCreated.query.order_by(OrderCreated.order_date.desc())
    paginated = q.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated.items
    process_order_details(orders)
    return render_template('order_list.html',
                           orders=orders,
                           page=page,
                           total_pages=paginated.pages,
                           total_orders_count=paginated.total)

@order_service_bp.route('/order-list/picking', methods=['GET'])
def get_picking_orders():
    page = request.args.get('page', 1, int)
    per_page = 50
    q = OrderPicking.query.order_by(OrderPicking.order_date.desc())
    paginated = q.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated.items
    process_order_details(orders)
    return render_template('order_list.html',
                           orders=orders,
                           page=page,
                           total_pages=paginated.pages,
                           total_orders_count=paginated.total)

@order_service_bp.route('/order-list/shipped', methods=['GET'])
def get_shipped_orders():
    page = request.args.get('page', 1, int)
    per_page = 50
    q = OrderShipped.query.order_by(OrderShipped.order_date.desc())
    paginated = q.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated.items
    process_order_details(orders)
    return render_template('order_list.html',
                           orders=orders,
                           page=page,
                           total_pages=paginated.pages,
                           total_orders_count=paginated.total)

@order_service_bp.route('/order-list/delivered', methods=['GET'])
def get_delivered_orders():
    page = request.args.get('page', 1, int)
    per_page = 50
    q = OrderDelivered.query.order_by(OrderDelivered.order_date.desc())
    paginated = q.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated.items
    process_order_details(orders)
    return render_template('order_list.html',
                           orders=orders,
                           page=page,
                           total_pages=paginated.pages,
                           total_orders_count=paginated.total)

@order_service_bp.route('/order-list/cancelled', methods=['GET'])
def get_cancelled_orders():
    page = request.args.get('page', 1, int)
    per_page = 50
    q = OrderCancelled.query.order_by(OrderCancelled.order_date.desc())
    paginated = q.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated.items
    process_order_details(orders)
    return render_template('order_list.html',
                           orders=orders,
                           page=page,
                           total_pages=paginated.pages,
                           total_orders_count=paginated.total)