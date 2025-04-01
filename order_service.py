# -*- coding: utf-8 -*-

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
from models import (
    db,
    OrderCreated,
    OrderPicking,
    OrderShipped,
    OrderDelivered,
    OrderCancelled,
    OrderArchived
)

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
# Statü -> Model eşlemesi
############################
STATUS_TABLE_MAP = {
    'Created':   OrderCreated,
    'Picking':   OrderPicking,
    'Invoiced':  OrderPicking,  # Invoiced -> picking tablosu
    'Shipped':   OrderShipped,
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

        params = {
            "status": "Created,Picking,Invoiced,Shipped,Delivered,Cancelled",
            "page": 0,
            "size": 500,  # Daha az sayfa ile çekmek için
            "orderByField": "PackageLastModifiedDate",
            "orderByDirection": "DESC"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                data = await response.json()
                if response.status != 200:
                    logger.error(f"API Error: {response.status} - {data}")
                    return

                total_elements = data.get('totalElements', 0)
                total_pages = data.get('totalPages', 1)
                logger.info(f"Toplam sipariş sayısı: {total_elements}, Toplam sayfa sayısı: {total_pages}")

                from asyncio import Semaphore, gather
                sem = Semaphore(10)
                tasks = []
                # İlk sayfadan gelen siparişler
                all_orders_data = data.get('content', [])

                # Ek sayfalar varsa paralel çek
                for page_number in range(1, total_pages):
                    params_page = dict(params, page=page_number)
                    tasks.append(fetch_orders_page(session, url, headers, params_page, sem))

                if tasks:
                    pages_data = await gather(*tasks)
                    for orders in pages_data:
                        all_orders_data.extend(orders)

                logger.info(f"Toplam çekilen sipariş sayısı: {len(all_orders_data)}")
                process_all_orders(all_orders_data)

    except Exception as e:
        logger.error(f"Hata: fetch_trendyol_orders_async - {e}")
        traceback.print_exc()


async def fetch_orders_page(session, url, headers, params, semaphore):
    """
    Belirli sayfadaki siparişleri asenkron çekme fonksiyonu.
    """
    async with semaphore:
        try:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    logger.error(f"API isteği başarısız oldu: {response.status} - {await response.text()}")
                    return []
                data = await response.json()
                return data.get('content', [])
        except Exception as e:
            logger.error(f"Hata: fetch_orders_page - {e}")
            return []


############################
# 2) Gelen Siparişleri İşleme (Created/Picking/Cancelled Senkron)
############################
def process_all_orders(all_orders_data):
    """
    Tüm siparişler statüsüne göre ayrılır:
    - (Created, Picking, Invoiced, Cancelled) -> Hemen işlenir (senkron).
    - (Shipped, Delivered) -> Arka planda işlenir (thread).
    """
    try:
        if not all_orders_data:
            logger.info("Hiç sipariş gelmedi.")
            return

        # 1) Arşiv kontrolü: arşivdeyse atla
        archived_list = OrderArchived.query.all()
        archived_set = {o.order_number for o in archived_list}

        # 2) Siparişleri statüye göre 2 kategoriye ayıralım
        sync_orders = []  # Created / Picking / Cancelled / Invoiced
        bg_orders   = []  # Shipped / Delivered

        processed_numbers = set()
        for od in all_orders_data:
            onum = str(od.get('orderNumber') or od.get('id'))
            if onum in processed_numbers:
                continue
            processed_numbers.add(onum)

            if onum in archived_set:
                logger.info(f"{onum} arşivde, atlanıyor.")
                continue

            st = (od.get('status') or '').strip()
            # 'Invoiced' => picking
            if st in ('Created', 'Picking', 'Invoiced', 'Cancelled'):
                sync_orders.append(od)
            elif st in ('Shipped', 'Delivered'):
                bg_orders.append(od)
            else:
                logger.warning(f"{onum} - işlenmeyen statü: {st}")

        # 3) Senkron siparişleri tek transaction ile işleyelim
        _process_sync_orders_bulk(sync_orders)

        # 4) Shipped/Delivered -> Arka plan
        if bg_orders:
            app = current_app._get_current_object()
            t = threading.Thread(target=process_bg_orders_bulk, args=(bg_orders, app))
            t.start()

    except Exception as e:
        logger.error(f"Hata: process_all_orders - {e}")
        traceback.print_exc()
        db.session.rollback()


def _process_sync_orders_bulk(sync_orders):
    """
    Created/Picking/Cancelled siparişlerini toplu şekilde ekleme/güncelleme
    (tek seferde commit).
    """
    if not sync_orders:
        return

    try:
        # 1) Siparişlerin order_number seti
        numbers = {str(od.get('orderNumber') or od.get('id')) for od in sync_orders}

        # 2) Mevcut kayıtları sorgula
        existing_created   = OrderCreated.query.filter(OrderCreated.order_number.in_(numbers)).all()
        existing_picking   = OrderPicking.query.filter(OrderPicking.order_number.in_(numbers)).all()
        existing_cancelled = OrderCancelled.query.filter(OrderCancelled.order_number.in_(numbers)).all()

        created_map   = {r.order_number: r for r in existing_created}
        picking_map   = {r.order_number: r for r in existing_picking}
        cancelled_map = {r.order_number: r for r in existing_cancelled}

        # 3) Bulk insert için listeler
        to_insert_created   = []
        to_insert_picking   = []
        to_insert_cancelled = []

        # 4) Döngü ile statüye göre ekle/güncelle
        for od in sync_orders:
            onum = str(od.get('orderNumber') or od.get('id'))
            st   = (od.get('status') or '').strip()

            # "Invoiced" = picking kabul
            if st == 'Invoiced':
                st = 'Picking'

            target_model = STATUS_TABLE_MAP.get(st)  # Created, Picking veya Cancelled
            new_data = combine_line_items(od, st)

            if target_model == OrderCreated:
                old_obj = created_map.get(onum)
                if old_obj:
                    _minimal_update_bulk(old_obj, new_data)
                else:
                    to_insert_created.append(new_data)

            elif target_model == OrderPicking:
                old_obj = picking_map.get(onum)
                if old_obj:
                    _minimal_update_bulk(old_obj, new_data)
                else:
                    to_insert_picking.append(new_data)

            elif target_model == OrderCancelled:
                old_obj = cancelled_map.get(onum)
                if old_obj:
                    _minimal_update_bulk(old_obj, new_data)
                else:
                    to_insert_cancelled.append(new_data)

        # 5) Tek seferde ekle
        if to_insert_created:
            db.session.bulk_insert_mappings(OrderCreated, to_insert_created)
            logger.info(f"{len(to_insert_created)} Created sipariş eklendi (bulk).")
        if to_insert_picking:
            db.session.bulk_insert_mappings(OrderPicking, to_insert_picking)
            logger.info(f"{len(to_insert_picking)} Picking sipariş eklendi (bulk).")
        if to_insert_cancelled:
            db.session.bulk_insert_mappings(OrderCancelled, to_insert_cancelled)
            logger.info(f"{len(to_insert_cancelled)} Cancelled sipariş eklendi (bulk).")

        # 6) Commit
        db.session.commit()
        logger.info("Created/Picking/Cancelled siparişler tek seferde güncellendi ve commit edildi.")
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Senkron sipariş kaydetme hatası: {e}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Senkron sipariş beklenmeyen hata: {e}")


def _minimal_update_bulk(old_obj, new_data):
    """
    Basit 'update' mantığı: statü, barkod, quantity, details vs.
    """
    old_obj.status = new_data.get('status')
    old_obj.product_barcode = new_data.get('product_barcode')
    old_obj.order_date = new_data.get('order_date')
    old_obj.quantity = new_data.get('quantity')
    old_obj.commission = new_data.get('commission')
    old_obj.details = new_data.get('details')


############################
# 3) Arka Plan Shipped/Delivered (Toplu Yaklaşım)
############################
def process_bg_orders_bulk(bg_orders, app):
    """
    Shipped ve Delivered siparişlerini tek seferde tablolara ekle/sil (bulk).
    """
    with app.app_context():
        try:
            if not bg_orders:
                return

            # 1) Sipariş seti
            numbers = {str(od.get('orderNumber') or od.get('id')) for od in bg_orders}

            # 2) Mevcut picking / shipped sorgula
            existing_picking = OrderPicking.query.filter(OrderPicking.order_number.in_(numbers)).all()
            existing_shipped = OrderShipped.query.filter(OrderShipped.order_number.in_(numbers)).all()

            picking_map = {r.order_number: r for r in existing_picking}
            shipped_map = {r.order_number: r for r in existing_shipped}

            # Toplu ekleme/silme listeleri
            to_insert_shipped = []
            to_insert_delivered = []
            to_delete_picking = []
            to_delete_shipped = []

            # 3) Döngüyle Shipped/Delivered ayrımı
            for od in bg_orders:
                onum = str(od.get('orderNumber') or od.get('id'))
                st = (od.get('status') or '').strip()

                if st == 'Shipped':
                    # picking → shipped
                    old_pick = picking_map.get(onum)
                    data_dict = combine_line_items(od, 'Shipped')
                    if old_pick:
                        to_delete_picking.append(old_pick.id)
                    to_insert_shipped.append(data_dict)

                elif st == 'Delivered':
                    # shipped → delivered
                    old_ship = shipped_map.get(onum)
                    data_dict = combine_line_items(od, 'Delivered')
                    if old_ship:
                        to_delete_shipped.append(old_ship.id)
                    to_insert_delivered.append(data_dict)

            # 4) Bulk insert & delete
            if to_insert_shipped:
                db.session.bulk_insert_mappings(OrderShipped, to_insert_shipped)
                logger.info(f"{len(to_insert_shipped)} sipariş Shipped tablosuna eklendi (arka plan).")

            if to_insert_delivered:
                db.session.bulk_insert_mappings(OrderDelivered, to_insert_delivered)
                logger.info(f"{len(to_insert_delivered)} sipariş Delivered tablosuna eklendi (arka plan).")

            if to_delete_picking:
                OrderPicking.query.filter(OrderPicking.id.in_(to_delete_picking)).delete(synchronize_session=False)
                logger.info(f"{len(to_delete_picking)} sipariş picking tablosundan silindi (arka plan).")

            if to_delete_shipped:
                OrderShipped.query.filter(OrderShipped.id.in_(to_delete_shipped)).delete(synchronize_session=False)
                logger.info(f"{len(to_delete_shipped)} sipariş shipped tablosundan silindi (arka plan).")

            db.session.commit()
            logger.info("Arka plan Shipped/Delivered siparişleri tek seferde tamamlandı.")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Hata (process_bg_orders_bulk): {e}")


############################
# Yardımcı Fonksiyonlar (Barkod vs.)
############################
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
    Karakter dönüşüm fonksiyonu.
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
    lines içindeki barkod, color, size vb. birleştirir.
    Toplam quantity vb. alanları doldurur. (Örnek)
    """
    details_dict = {}
    total_quantity = 0
    for line in lines:
        bc = line.get('barcode', '')
        color = line.get('productColor', '')
        size_ = line.get('productSize', '')
        q = safe_int(line.get('quantity'), 1)
        total_quantity += q
        cf = safe_float(line.get('commissionFee'), 0.0)
        line_id = str(line.get('id', ''))

        key = (bc, color, size_)
        if key not in details_dict:
            details_dict[key] = {
                'barcode': bc,
                'converted_barcode': replace_turkish_characters_cached(bc),
                'color': color,
                'size': size_,
                'sku': line.get('merchantSku', ''),
                'productName': line.get('productName', ''),
                'productCode': str(line.get('productCode', '')),
                'product_main_id': str(line.get('productId', '')),
                'quantity': q,
                'commissionFee': cf,
                'line_id': line_id,
                'total_price': safe_float(line.get('amount'), 0) * q
            }
        else:
            details_dict[key]['quantity'] += q
            details_dict[key]['commissionFee'] += cf
            details_dict[key]['total_price'] += safe_float(line.get('amount'), 0) * q

    # Her entry'ye toplam quantity koy
    for val in details_dict.values():
        val['total_quantity'] = total_quantity

    return list(details_dict.values())

def combine_line_items(order_data, status):
    """
    Tabloya yazılacak verileri hazırlayan fonksiyon (SENİN GÜNCEL KODUN).
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


############################
# 4) Rotalar: Created, Picking, Shipped, Delivered, Cancelled
############################

@order_service_bp.route('/order-list/new', methods=['GET'])
def get_new_orders():
    page = request.args.get('page', 1, int)
    per_page = 50
    q = OrderCreated.query.order_by(OrderCreated.order_date.desc())
    paginated = q.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated.items
    process_order_details(orders)
    return render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=paginated.pages,
        total_orders_count=paginated.total
    )

@order_service_bp.route('/order-list/picking', methods=['GET'])
def get_picking_orders():
    page = request.args.get('page', 1, int)
    per_page = 50
    q = OrderPicking.query.order_by(OrderPicking.order_date.desc())
    paginated = q.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated.items
    process_order_details(orders)
    return render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=paginated.pages,
        total_orders_count=paginated.total
    )

@order_service_bp.route('/order-list/shipped', methods=['GET'])
def get_shipped_orders():
    page = request.args.get('page', 1, int)
    per_page = 50
    q = OrderShipped.query.order_by(OrderShipped.order_date.desc())
    paginated = q.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated.items
    process_order_details(orders)
    return render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=paginated.pages,
        total_orders_count=paginated.total
    )

@order_service_bp.route('/order-list/delivered', methods=['GET'])
def get_delivered_orders():
    page = request.args.get('page', 1, int)
    per_page = 50
    q = OrderDelivered.query.order_by(OrderDelivered.order_date.desc())
    paginated = q.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated.items
    process_order_details(orders)
    return render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=paginated.pages,
        total_orders_count=paginated.total
    )

@order_service_bp.route('/order-list/cancelled', methods=['GET'])
def get_cancelled_orders():
    page = request.args.get('page', 1, int)
    per_page = 50
    q = OrderCancelled.query.order_by(OrderCancelled.order_date.desc())
    paginated = q.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated.items
    process_order_details(orders)
    return render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=paginated.pages,
        total_orders_count=paginated.total
    )
