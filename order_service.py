from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_sqlalchemy import SQLAlchemy
import base64
import json
from datetime import datetime, timedelta
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID
from update_service import update_package_to_picking
from models import db, Order
import traceback
import asyncio
import aiohttp
import os
import logging
from sqlalchemy.exc import SQLAlchemyError

# `order_list_service` modülünden `process_order_details` fonksiyonunu import ediyoruz
from order_list_service import process_order_details

order_service_bp = Blueprint('order_service', __name__)

# Loglama ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('order_service.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


@order_service_bp.route('/fetch-trendyol-orders', methods=['POST'])
def fetch_trendyol_orders_route():
    try:
        # Asenkron fonksiyonu çağır
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

        # İlk isteği yaparak toplam sipariş ve sayfa sayısını alalım
        params = {
            "status": "Created,Picking,Invoiced,Shipped,Delivered",
            "page": 0,
            "size": 200,  # Maksimum sayfa boyutu
            "orderByField": "PackageLastModifiedDate",
            "orderByDirection": "DESC"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                response_data = await response.json()
                if response.status != 200:
                    print(f"API Error: {response.status} - {response_data}")
                    return

                total_elements = response_data.get('totalElements', 0)
                total_pages = response_data.get('totalPages', 1)
                print(f"Toplam sipariş sayısı: {total_elements}, Toplam sayfa sayısı: {total_pages}")

                # Tüm sayfalar için istek hazırlayalım
                tasks = []
                semaphore = asyncio.Semaphore(5)  # Aynı anda maksimum 5 istek
                for page_number in range(total_pages):
                    params_page = params.copy()
                    params_page['page'] = page_number
                    task = fetch_orders_page(session, url, headers, params_page, semaphore)
                    tasks.append(task)

                # Asenkron olarak tüm istekleri yapalım
                pages_data = await asyncio.gather(*tasks)

                # Gelen siparişleri birleştirelim
                all_orders_data = []
                for orders in pages_data:
                    all_orders_data.extend(orders)

                print(f"Toplam çekilen sipariş sayısı: {len(all_orders_data)}")

                # Siparişleri işleyelim
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
                orders_data = data.get('content', [])
                return orders_data
        except Exception as e:
            print(f"Hata: fetch_orders_page - {e}")
            return []


def process_all_orders(all_orders_data):
    try:
        api_order_numbers = set()
        new_orders = []

        # Mevcut siparişleri al
        existing_orders = Order.query.all()
        existing_orders_dict = {order.order_number: order for order in existing_orders}

        for order_data in all_orders_data:
            order_number = str(order_data.get('orderNumber') or order_data.get('id'))
            api_order_numbers.add(order_number)
            order_status = order_data.get('status')

            if order_number in existing_orders_dict:
                existing_order = existing_orders_dict[order_number]
                if existing_order.status == 'Delivered':
                    # 'Delivered' siparişleri güncellemiyoruz
                    continue
                # Siparişi güncelle
                update_existing_order(existing_order, order_data, order_status)
            else:
                # Yeni siparişi ekle
                combined_order = combine_line_items(order_data, order_status)
                new_order = Order(**combined_order)
                new_orders.append(new_order)

        # Toplu ekleme
        if new_orders:
            db.session.bulk_save_objects(new_orders)
            logger.info(f"Toplam yeni eklenen sipariş sayısı: {len(new_orders)}")

        db.session.commit()

        # Veritabanında olmayan siparişleri sil, ancak 'Delivered' siparişleri silme
        existing_order_numbers = set(existing_orders_dict.keys())
        orders_to_delete_numbers = existing_order_numbers - api_order_numbers

        if orders_to_delete_numbers:
            # 'Delivered' siparişleri silineceklerden çıkar
            delivered_orders = Order.query.filter(
                Order.order_number.in_(orders_to_delete_numbers),
                Order.status == 'Delivered'
            ).all()
            delivered_order_numbers = {order.order_number for order in delivered_orders}
            # Silinecek sipariş numaralarını güncelle
            orders_to_delete_numbers = orders_to_delete_numbers - delivered_order_numbers

            if orders_to_delete_numbers:
                # Kalan siparişleri sil
                Order.query.filter(Order.order_number.in_(orders_to_delete_numbers)).delete(synchronize_session=False)
                logger.info(f"Silinen siparişler: {orders_to_delete_numbers}")
                db.session.commit()
            else:
                logger.info("Silinecek sipariş yok.")
        else:
            logger.info("Silinecek sipariş yok.")

    except SQLAlchemyError as e:
        logger.error(f"Veritabanı hatası: {e}")
        db.session.rollback()
    except Exception as e:
        logger.error(f"Hata: process_all_orders - {e}")
        traceback.print_exc()


def update_existing_order(existing_order, order_data, status):
    """
    Varolan sipariş kaydı üzerinde güncelleme yaparken
    hem details'e hem de quantity kolonuna toplam adet bilgisini kaydediyoruz.
    """
    try:
        new_lines = order_data['lines']

        # Daha önce kaydedilmiş verileri liste olarak çek
        merchant_skus = existing_order.merchant_sku.split(', ') if existing_order.merchant_sku else []
        product_barcodes = existing_order.product_barcode.split(', ') if existing_order.product_barcode else []
        original_product_barcodes = existing_order.original_product_barcode.split(', ') if existing_order.original_product_barcode else []
        line_ids = existing_order.line_id.split(', ') if existing_order.line_id else []

        # Toplam adet toplanacak
        total_qty = 0

        for line in new_lines:
            q = line.get('quantity', 1)
            try:
                q = int(q)
            except:
                q = 1
            total_qty += q

            merchant_sku = line.get('merchantSku', '')
            barcode = replace_turkish_characters(line.get('barcode', ''))
            original_barcode = line.get('barcode', '')
            line_id = str(line.get('id', ''))

            if merchant_sku:
                merchant_skus.append(merchant_sku)
            if barcode:
                product_barcodes.append(barcode)
            if original_barcode:
                original_product_barcodes.append(original_barcode)
            if line_id:
                line_ids.append(line_id)

        # Veritabanındaki sütunları güncelle
        existing_order.status = status
        existing_order.merchant_sku = ', '.join(merchant_skus)
        existing_order.product_barcode = ', '.join(product_barcodes)
        existing_order.original_product_barcode = ', '.join(original_product_barcodes)
        existing_order.line_id = ', '.join(line_ids)

        # Yeni eklenen kod: Sipariş detaylarını güncelle
        order_details = create_order_details(new_lines)
        existing_order.details = json.dumps(order_details, ensure_ascii=False)

        # Toplam adet bilgisini de tabloya kaydet
        existing_order.quantity = total_qty

        logger.info(f"Güncellenen sipariş: {existing_order.order_number}")
    except Exception as e:
        logger.error(f"Hata: update_existing_order - {e}")
        traceback.print_exc()


def create_order_details(order_lines):
    details_dict = {}  # dict: (barkod, color, size) -> detail
    total_quantity = 0  # Toplam miktar takibi

    for line in order_lines:
        try:
            barcode = line.get('barcode', '')
            product_color = line.get('productColor', '')
            product_size = line.get('productSize', '')
            merchant_sku = line.get('merchantSku', '')
            product_name = line.get('productName', '')
            product_code = str(line.get('productCode', ''))
            quantity = int(line.get('quantity', 1))
            amount = float(line.get('amount', 0))

            # Toplam miktarı güncelle
            total_quantity += quantity

            # Anahtar oluştur: (barkod, color, size)
            key = (barcode, product_color, product_size)

            if key not in details_dict:
                # Yeni kayıt
                details_dict[key] = {
                    'barcode': barcode,
                    'converted_barcode': replace_turkish_characters(barcode),
                    'color': product_color,
                    'size': product_size,
                    'sku': merchant_sku,
                    'productName': product_name,
                    'productCode': product_code,
                    'quantity': quantity,
                    'total_price': amount * quantity,
                    'image_url': ''
                }
            else:
                # Mevcut kayıt, miktarı ekle
                details_dict[key]['quantity'] += quantity
                details_dict[key]['total_price'] += amount * quantity

        except Exception as e:
            logger.error(f"Sipariş detayı oluşturulurken hata: {e}")
            continue

    # Her bir siparişin total_quantity değerini details içine ekle
    for detail in details_dict.values():
        detail['total_quantity'] = total_quantity

    # Sözlüğü liste olarak döndür
    return list(details_dict.values())




def replace_turkish_characters(text):
    """
    Gelen barkod veya metinlerdeki Türkçe karakterleri başka karakterlerle değiştiren fonksiyon.
    Sen kendi ihtiyacına göre düzenleyebilirsin.
    """
    if isinstance(text, str):
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
        text = text.translate(replacements)
    return text


def combine_line_items(order_data, status):
    # Miktar bilgisini koruyarak barkodları işle
    barcodes_with_quantity = []
    total_qty = 0  # Toplam adet için
    for line in order_data['lines']:
        barcode = line.get('barcode', '')
        quantity = line.get('quantity', 1)
        try:
            quantity = int(quantity)
        except:
            quantity = 1
        total_qty += quantity

        # Her miktar için barkodu tekrarla
        barcodes_with_quantity.extend([barcode] * quantity)

    original_barcodes = barcodes_with_quantity
    converted_barcodes = [replace_turkish_characters(bc) for bc in original_barcodes]

    # Sipariş detaylarını oluştur
    # Sipariş detaylarına line_id ekle
order_details = []
for line in order_data['lines']:
    detail = {
        'barcode': line.get('barcode', ''),
        'converted_barcode': replace_turkish_characters(line.get('barcode', '')),
        'color': line.get('productColor', ''),
        'size': line.get('productSize', ''),
        'sku': line.get('merchantSku', ''),
        'productName': line.get('productName', ''),
        'productCode': str(line.get('productCode', '')),
        'quantity': int(line.get('quantity', 1)),
        'total_price': float(line.get('amount', 0)) * int(line.get('quantity', 1)),
        'image_url': '',
        'total_quantity': int(line.get('quantity', 1)),
        'line_id': str(line.get('id', ''))  # Line ID eklendi
    }
    order_details.append(detail)

    combined_order = {
        'order_number': str(order_data.get('orderNumber', order_data['id'])),
        'order_date': datetime.utcfromtimestamp(order_data['orderDate'] / 1000) if order_data.get('orderDate') else None,
        'merchant_sku': ', '.join([line.get('merchantSku', '') for line in order_data['lines']]),
        'product_barcode': ', '.join(converted_barcodes),
        'original_product_barcode': ', '.join(original_barcodes),
        'status': status,
        'line_id': ', '.join([str(line.get('id', '')) for line in order_data['lines']]),
        'match_status': '',
        'customer_name': order_data.get('shipmentAddress', {}).get('firstName', ''),
        'customer_surname': order_data.get('shipmentAddress', {}).get('lastName', ''),
        'customer_address': order_data.get('shipmentAddress', {}).get('fullAddress', ''),
        'shipping_barcode': order_data.get('cargoTrackingNumber', ''),
        'product_name': ', '.join([line.get('productName', '') for line in order_data['lines']]),
        'product_code': ', '.join([str(line.get('productCode', '')) for line in order_data['lines']]),
        'amount': sum(line.get('amount', 0) for line in order_data['lines']),
        'discount': sum(line.get('discount', 0) for line in order_data['lines']),
        'currency_code': order_data.get('currencyCode', 'TRY'),
        'vat_base_amount': sum(line.get('vatBaseAmount', 0) for line in order_data['lines']),
        'package_number': str(order_data.get('id', '')),
        'stockCode': ', '.join([line.get('merchantSku', '') for line in order_data['lines']]),
        'estimated_delivery_start': datetime.utcfromtimestamp(order_data.get('estimatedDeliveryStartDate', 0) / 1000) if order_data.get('estimatedDeliveryStartDate') else None,
        'images': '',
        'product_model_code': ', '.join([line.get('merchantSku', '') for line in order_data['lines']]),
        'estimated_delivery_end': datetime.utcfromtimestamp(order_data.get('estimatedDeliveryEndDate', 0) / 1000) if order_data.get('estimatedDeliveryEndDate') else None,
        'origin_shipment_date': datetime.utcfromtimestamp(order_data.get('originShipmentDate', 0) / 1000) if order_data.get('originShipmentDate') else None,
        'product_size': ', '.join([line.get('productSize', '') for line in order_data['lines']]),
        'product_main_id': ', '.join([str(line.get('product_main_id', '')) for line in order_data['lines']]),
        'cargo_provider_name': order_data.get('cargoProviderName', ''),
        'agreed_delivery_date': datetime.utcfromtimestamp(order_data.get('agreedDeliveryDate', 0) / 1000) if order_data.get('agreedDeliveryDate') else None,
        'product_color': ', '.join([line.get('productColor', '') for line in order_data['lines']]),
        'cargo_tracking_link': order_data.get('cargoTrackingNumber', ''),
        'shipment_package_id': str(order_data.get('shipmentPackageId', '')),
        'details': json.dumps(order_details, ensure_ascii=False),
        'archive_date': None,
        'archive_reason': '',
        # Yeni eklenen kolon verisi:
        'quantity': total_qty
    }
    return combined_order


# ===== Sipariş listesi görüntüleme fonksiyonları =====

@order_service_bp.route('/order-list/new', methods=['GET'])
def get_new_orders():
    page = request.args.get('page', 1, type=int)
    per_page = 100

    orders_query = Order.query.filter_by(status='Created').order_by(Order.order_date.desc())
    paginated_orders = orders_query.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated_orders.items
    total_orders = paginated_orders.total
    total_pages = paginated_orders.pages

    process_order_details(orders)

    return render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=total_pages,
        total_orders_count=total_orders
    )


@order_service_bp.route('/order-list/processed', methods=['GET'])
def get_processed_orders():
    page = request.args.get('page', 1, type=int)
    per_page = 100

    orders_query = Order.query.filter_by(status='Picking').order_by(Order.order_date.desc())
    paginated_orders = orders_query.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated_orders.items
    total_orders = paginated_orders.total
    total_pages = paginated_orders.pages

    process_order_details(orders)

    return render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=total_pages,
        total_orders_count=total_orders
    )


@order_service_bp.route('/order-list/delivered', methods=['GET'])
def get_delivered_orders():
    page = request.args.get('page', 1, type=int)
    per_page = 100

    orders_query = Order.query.filter(Order.status.in_(['Delivered', 'Teslim Edildi'])).order_by(Order.order_date.desc())
    paginated_orders = orders_query.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated_orders.items
    total_orders = paginated_orders.total
    total_pages = paginated_orders.pages

    process_order_details(orders)

    return render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=total_pages,
        total_orders_count=total_orders
    )


@order_service_bp.route('/order-list/shipped', methods=['GET'])
def get_shipped_orders():
    page = request.args.get('page', 1, type=int)
    per_page = 100

    orders_query = Order.query.filter(Order.status.in_(['Shipped', 'Kargoya Verildi'])).order_by(Order.order_date.desc())
    paginated_orders = orders_query.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated_orders.items
    total_orders = paginated_orders.total
    total_pages = paginated_orders.pages

    process_order_details(orders)

    return render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=total_pages,
        total_orders_count=total_orders
    )