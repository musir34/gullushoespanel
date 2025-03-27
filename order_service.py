from flask import Blueprint, render_template, request, redirect, url_for, flash
import asyncio
import aiohttp
import base64
import json
import traceback
import logging
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError

from models import db, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled, OrderArchived
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID
from order_list_service import process_order_details  # Varsayıyorum
from update_service import update_package_to_picking  # Varsayıyorum

order_service_bp = Blueprint('order_service', __name__)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('order_service.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


# Statü -> Model eşlemesi
STATUS_TABLE_MAP = {
    'Created': OrderCreated,
    'Picking': OrderPicking,
    'Invoiced': OrderPicking,      # İstersen Invoiced => picking
    'Shipped': OrderShipped,
    'Delivered': OrderDelivered,
    'Cancelled': OrderCancelled
}

@order_service_bp.route('/fetch-trendyol-orders', methods=['POST'])
def fetch_trendyol_orders_route():
    try:
        asyncio.run(fetch_trendyol_orders_async())
        flash('Siparişler başarıyla güncellendi!', 'success')
    except Exception as e:
        logger.error(f"Hata: fetch_trendyol_orders_route - {e}")
        traceback.print_exc()
        flash('Siparişler güncellenirken bir hata oluştu.', 'danger')

    return redirect(url_for('order_list_service.order_list_all'))

async def fetch_trendyol_orders_async():
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
            "size": 200,
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

                tasks = []
                from asyncio import Semaphore
                semaphore = Semaphore(5)
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

def process_all_orders(all_orders_data):
    try:
        if not all_orders_data:
            logger.info("Hiç sipariş gelmedi.")
            return

        # arşiv kontrolu
        archived = OrderArchived.query.all()
        archived_set = {o.order_number for o in archived}

        processed = set()
        for od in all_orders_data:
            order_number = str(od.get('orderNumber') or od.get('id'))
            if order_number in processed:
                continue
            processed.add(order_number)

            if order_number in archived_set:
                logger.info(f"{order_number} arşivde, atla.")
                continue

            st = (od.get('status') or '').strip()
            if st not in STATUS_TABLE_MAP:
                logger.warning(f"{order_number} - bilinmeyen statü: {st}")
                continue

            target_model = STATUS_TABLE_MAP[st]

            # var mı?
            old_order, old_model = find_existing_order_in_all_tables(order_number)
            if old_order:
                if old_model != target_model:
                    move_order_between_tables(order_number, old_model, target_model)
                    # Tekrar bul
                    new_rec = target_model.query.filter_by(order_number=order_number).first()
                    if new_rec:
                        update_existing_order_minimal(new_rec, od)
                else:
                    # Aynı tablodayız -> güncelle
                    update_existing_order_minimal(old_order, od)
            else:
                # Yeni kayit
                from datetime import datetime
                new_data = combine_line_items(od, st)
                obj = target_model(**new_data)
                db.session.add(obj)
                db.session.commit()
                logger.info(f"Yeni sipariş eklendi {order_number} -> {target_model.__tablename__}")

    except SQLAlchemyError as e:
        logger.error(f"Veritabanı hatası: {e}")
        db.session.rollback()
    except Exception as e:
        logger.error(f"Hata: process_all_orders - {e}")
        traceback.print_exc()


def find_existing_order_in_all_tables(order_number):
    for cls in (OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled):
        row = cls.query.filter_by(order_number=order_number).first()
        if row:
            return (row, cls)
    return (None, None)

def move_order_between_tables(order_number, old_model, new_model):
    old_rec = old_model.query.filter_by(order_number=order_number).first()
    if not old_rec:
        return
    data = {}
    for c in old_rec.__table__.columns:
        data[c.name] = getattr(old_rec, c.name)

    new_rec = new_model(**data)
    db.session.add(new_rec)
    db.session.delete(old_rec)
    db.session.commit()
    logger.info(f"{order_number} {old_model.__tablename__} -> {new_model.__tablename__}")

####################################
# İstediğin mantık: 
#  - Delivered / Cancelled -> Bir daha barkod güncellenmez 
#  - Shipped -> Sadece statü kontrol; barkod dokunma
####################################
def update_existing_order_minimal(order_obj, order_data):
    new_status = (order_data.get('status') or '').strip()

    # 1) Eğer sipariş zaten Delivered veya Cancelled ise, hiç dokunma
    if order_obj.status in ('Delivered', 'Cancelled'):
        logger.info(f"{order_obj.order_number} zaten {order_obj.status}, güncellenmedi.")
        return

    # 2) Eğer yeni statü Delivered/Cancelled ise, sadece statüyü atayalım
    if new_status in ('Delivered','Cancelled'):
        order_obj.status = new_status
        db.session.commit()
        logger.info(f"{order_obj.order_number} -> statü {new_status} yapıldı, barkod dokunulmadı.")
        return

    # 3) Eğer yeni statü Shipped ise -> Sadece statü koy, barkod güncellemeyelim
    if new_status == 'Shipped':
        order_obj.status = 'Shipped'
        db.session.commit()
        logger.info(f"{order_obj.order_number} -> statü Shipped, barkod/lines güncellenmedi.")
        return

    # 4) Geriye Created/Picking/Invoiced statüleri kaldı -> sil-yeniden ekle
    order_obj.merchant_sku = ''
    order_obj.product_barcode = ''
    order_obj.original_product_barcode = ''
    order_obj.line_id = ''
    order_obj.quantity = 0
    order_obj.commission = 0.0

    order_obj.status = new_status

    lines = order_data.get('lines', [])
    new_msku = []
    new_bc = []
    new_obc = []
    new_lids = []

    for li in lines:
        q = li.get('quantity',1)
        try:
            q = int(q)
        except:
            q = 1
        order_obj.quantity += q

        cf = li.get('commissionFee',0.0)
        try:
            cf = float(cf)
        except:
            cf = 0.0
        order_obj.commission += cf

        msku = li.get('merchantSku','')
        obc = li.get('barcode','')
        cbc = replace_turkish_characters(obc)
        lid = str(li.get('id',''))

        if msku: new_msku.append(msku)
        if cbc: new_bc.append(cbc)
        if obc: new_obc.append(obc)
        if lid: new_lids.append(lid)

    order_obj.merchant_sku = ', '.join(new_msku)
    order_obj.product_barcode = ', '.join(new_bc)
    order_obj.original_product_barcode = ', '.join(new_obc)
    order_obj.line_id = ', '.join(new_lids)

    # details
    from json import dumps
    dd = create_order_details(lines)
    order_obj.details = dumps(dd, ensure_ascii=False)

    db.session.commit()
    logger.info(f"{order_obj.order_number} -> statü {new_status}, barkod güncellendi (Created/Picking).")


# Aşağıdaki fonksiyonlar: combine_line_items, create_order_details, replace_turkish_characters
# senin önceki kodla aynı, sadece rename edebilir veya ekleyebilirsin.

def replace_turkish_characters(text):
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
    details_dict = {}
    total_quantity = 0
    for line in lines:
        try:
            bc = line.get('barcode','')
            c = line.get('productColor','')
            s = line.get('productSize','')
            q = int(line.get('quantity',1))
            total_quantity += q

            cf = float(line.get('commissionFee',0.0))
            line_id = str(line.get('id',''))

            key = (bc,c,s)
            if key not in details_dict:
                details_dict[key] = {
                    'barcode': bc,
                    'converted_barcode': replace_turkish_characters(bc),
                    'color': c,
                    'size': s,
                    'sku': line.get('merchantSku',''),
                    'productName': line.get('productName',''),
                    'productCode': str(line.get('productCode','')),
                    'product_main_id': str(line.get('productId','')),
                    'quantity': q,
                    'total_price': float(line.get('amount',0))*q,
                    'line_id': line_id,
                    'commissionFee': cf,
                    'image_url': ''
                }
            else:
                details_dict[key]['quantity'] += q
                details_dict[key]['commissionFee'] += cf
                details_dict[key]['total_price'] += float(line.get('amount',0))*q
        except:
            continue

    for det in details_dict.values():
        det['total_quantity'] = total_quantity

    return list(details_dict.values())


def combine_line_items(order_data, status):
    lines = order_data.get('lines',[])
    total_qty=0
    commission_sum=0.0
    bc_list = []
    for l in lines:
        q = int(l.get('quantity',1))
        total_qty += q
        cfee = float(l.get('commissionFee',0.0))
        commission_sum += cfee
        bc = l.get('barcode','')
        for _ in range(q):
            bc_list.append(bc)
    cbc = [replace_turkish_characters(x) for x in bc_list]
    from json import dumps
    dd = create_order_details(lines)

    return {
        'order_number': str(order_data.get('orderNumber', order_data.get('id'))),
        'order_date': datetime.utcfromtimestamp(order_data['orderDate']/1000) if order_data.get('orderDate') else None,
        'merchant_sku': ', '.join([x.get('merchantSku','') for x in lines]),
        'product_barcode': ', '.join(cbc),
        'original_product_barcode': ', '.join(bc_list),
        'status': status,
        'line_id': ', '.join([str(x.get('id','')) for x in lines]),
        'match_status': '',
        'customer_name': order_data.get('shipmentAddress',{}).get('firstName',''),
        'customer_surname': order_data.get('shipmentAddress',{}).get('lastName',''),
        'customer_address': order_data.get('shipmentAddress',{}).get('fullAddress',''),
        'shipping_barcode': order_data.get('cargoTrackingNumber',''),
        'product_name': ', '.join([x.get('productName','') for x in lines]),
        'product_code': ', '.join([str(x.get('productCode','')) for x in lines]),
        'amount': sum(x.get('amount',0) for x in lines),
        'discount': sum(x.get('discount',0) for x in lines),
        'currency_code': order_data.get('currencyCode','TRY'),
        'vat_base_amount': sum(x.get('vatBaseAmount',0) for x in lines),
        'package_number': str(order_data.get('id','')),
        'stockCode': ', '.join([x.get('merchantSku','') for x in lines]),
        'estimated_delivery_start': datetime.utcfromtimestamp(order_data.get('estimatedDeliveryStartDate',0)/1000) if order_data.get('estimatedDeliveryStartDate') else None,
        'images': '',
        'product_model_code': ', '.join([x.get('merchantSku','') for x in lines]),
        'estimated_delivery_end': datetime.utcfromtimestamp(order_data.get('estimatedDeliveryEndDate',0)/1000) if order_data.get('estimatedDeliveryEndDate') else None,
        'origin_shipment_date': datetime.utcfromtimestamp(order_data.get('originShipmentDate',0)/1000) if order_data.get('originShipmentDate') else None,
        'product_size': ', '.join([x.get('productSize','') for x in lines]),
        'product_main_id': ', '.join([str(x.get('productId','')) for x in lines]),
        'cargo_provider_name': order_data.get('cargoProviderName',''),
        'agreed_delivery_date': datetime.utcfromtimestamp(order_data.get('agreedDeliveryDate',0)/1000) if order_data.get('agreedDeliveryDate') else None,
        'product_color': ', '.join([x.get('productColor','') for x in lines]),
        'cargo_tracking_link': order_data.get('cargoTrackingNumber',''),
        'shipment_package_id': str(order_data.get('shipmentPackageId','')),
        'details': dumps(dd, ensure_ascii=False),
        'quantity': total_qty,
        'commission': commission_sum
    }


########################################
# Rotalar (Created,Picking,Shipped,Delivered,Cancelled)
########################################

@order_service_bp.route('/order-list/new', methods=['GET'])
def get_new_orders():
    page = request.args.get('page',1,int)
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
    page = request.args.get('page',1,int)
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
    page = request.args.get('page',1,int)
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
    page = request.args.get('page',1,int)
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
    page = request.args.get('page',1,int)
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
