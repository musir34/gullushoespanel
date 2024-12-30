from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL
import requests
import traceback
import json
import base64
from models import db, Order


update_service_bp = Blueprint('update_service', __name__)




# Trendyol API üzerinden sipariş statüsünü güncelleyen fonksiyon
def update_order_status_to_picking(supplier_id, shipment_package_id, lines):
    try:
        url = f"{BASE_URL}suppliers/{supplier_id}/shipment-packages/{shipment_package_id}"

        credentials = f"{API_KEY}:{API_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/json"
        }

        payload = {
            "lines": lines,
            "params": {},
            "status": "Picking"
        }

        print(f"API isteği: URL={url}, Payload={json.dumps(payload, ensure_ascii=False)}")
        print(f"Headers: {headers}")

        response = requests.put(url, headers=headers, data=json.dumps(payload), timeout=30)

        print(f"API yanıtı: Status Code={response.status_code}, Response Text={response.text}")

        if response.status_code == 200:
            # Yanıt gövdesinin boş olup olmadığını kontrol edin
            if response.text:
                data = response.json()
                print(f"Paket {shipment_package_id} statüsü 'Picking' olarak güncellendi.")
            else:
                print(f"Paket {shipment_package_id} statüsü 'Picking' olarak güncellendi (boş yanıt gövdesi).")
            return True
        else:
            print(f"Beklenmeyen durum kodu veya yanıt: {response.status_code}, Yanıt: {response.text}")
            return False

    except Exception as e:
        print(f"API üzerinden paket statüsü güncellenirken bir hata oluştu: {e}")
        return False

# Paketleme onayı fonksiyonu
@update_service_bp.route('/confirm_packing', methods=['POST'])
def confirm_packing():
    try:
        # Sipariş numarasını al
        order_number = request.form['order_number']
        print(f"Received order_number: {order_number}")

        # Barkodları topla
        barkodlar = []
        for key in request.form:
            if key.startswith('barkod_right_') or key.startswith('barkod_left_'):
                barkod_value = request.form[key].strip()
                barkodlar.append(barkod_value)
        print(f"Received barcodes: {barkodlar}")
        print(f"Received barcodes (repr): {[repr(b) for b in barkodlar]}")

        # Siparişi veritabanından al
        order = Order.query.filter_by(order_number=order_number).first()
        if not order:
            flash('Sipariş bulunamadı.', 'danger')
            print("Order not found.")
            return redirect(url_for('home.home'))

        # Sipariş detaylarını al ve JSON olarak yükle
        details_json = order.details or '[]'
        try:
            details = json.loads(details_json)
            print(f"Parsed details: {details}")
        except json.JSONDecodeError:
            details = []
            print(f"order.details JSON parse edilemedi: {order.details}")

        # ShipmentPackageId'leri ürün detaylarından toplayın
        shipment_package_ids = set()
        for detail in details:
            sp_id = detail.get('shipmentPackageId') or order.shipment_package_id or order.package_number
            if sp_id:
                shipment_package_ids.add(sp_id)

        print(f"Shipment Package IDs: {shipment_package_ids}")

        if not shipment_package_ids:
            shipment_package_ids = {order.shipment_package_id or order.package_number}
            print(f"Using order level Shipment Package ID: {shipment_package_ids}")

        if not shipment_package_ids:
            flash("shipmentPackageId bulunamadı.", 'danger')
            print("shipmentPackageId bulunamadı.")
            return redirect(url_for('home.home'))

        expected_barcodes = []
        for detail in details:
            print(f"Processing detail: {detail}")
            # Her quantity için barkodları ekleyin (sol ve sağ olmak üzere iki kez)
            barcode = detail['barcode']
            quantity = int(detail.get('quantity', 1))
            count = quantity * 2  # Sol ve sağ barkodlar için miktarı ikiyle çarpıyoruz
            print(f"Adding {count} copies of barcode: {barcode}")
            expected_barcodes.extend([barcode] * count)
        print(f"Expected barcodes after processing details: {expected_barcodes}")
        print(f"Expected barcodes (repr): {[repr(b) for b in expected_barcodes]}")

        # Debug: Barkod listesini ve beklenen barkod listesini karşılaştır
        print(f"Comparing received barcodes ({len(barkodlar)}): {barkodlar}")
        print(f"With expected barcodes ({len(expected_barcodes)}): {expected_barcodes}")

        if sorted(barkodlar) == sorted(expected_barcodes):
            print("Barcodes match.")
            order.status = 'Picking'  # Sipariş statüsünü güncelliyoruz
            db.session.commit()
            print(f"Updated order status to 'Picking' for order_number: {order_number}")

            # Gerekli verileri al
            supplier_id = SUPPLIER_ID
            print(f"Supplier ID: {supplier_id}, Shipment Package IDs: {shipment_package_ids}")

            lines = []
            for detail in details:
                line_id = detail.get('line_id')
                quantity = int(detail.get('quantity', 1))
                sp_id = detail.get('shipmentPackageId') or order.shipment_package_id or order.package_number
                print(f"Detail line_id: {line_id}, quantity: {quantity}, shipmentPackageId: {sp_id}")

                if line_id is None:
                    flash("'line_id' değeri bulunamadı. Sipariş verilerini kontrol edin.", 'danger')
                    print("'line_id' değeri bulunamadı.")
                    return redirect(url_for('home.home'))

                try:
                    line = {
                        "lineId": int(line_id),
                        "quantity": quantity,
                        "shipmentPackageId": sp_id
                    }
                    lines.append(line)
                    print(f"Added line to lines: {line}")
                except ValueError as ve:
                    flash(f"Line ID veya quantity hatalı: {ve}", 'danger')
                    print(f"Error converting line_id or quantity: {ve}")
                    return redirect(url_for('home.home'))

            print(f"Lines to send to API: {lines}")

            # lines listesini shipmentPackageId'ye göre gruplandırın
            from collections import defaultdict

            lines_by_sp_id = defaultdict(list)
            for line in lines:
                sp_id = line.pop('shipmentPackageId')
                lines_by_sp_id[sp_id].append(line)

            # Her bir shipmentPackageId için API çağrısı yapın
            for sp_id, lines_for_sp in lines_by_sp_id.items():
                print(f"Making API call for Shipment Package ID: {sp_id} with lines: {lines_for_sp}")
                result = update_order_status_to_picking(supplier_id, sp_id, lines_for_sp)
                print(f"update_order_status_to_picking result for {sp_id}: {result}")
                if result:
                    flash(f"Paket {sp_id} başarıyla güncellendi ve API üzerinden statü güncellendi.", 'success')
                else:
                    flash(f"Paket statüsü API üzerinde güncellenirken bir hata oluştu. Paket ID: {sp_id}", 'danger')

            # Bir sonraki siparişi bul
            next_order = Order.query.filter_by(status='Created').first()
            if next_order:
                flash(f'Bir sonraki sipariş: {next_order.order_number}.', 'info')
                print(f"Next order found: {next_order.order_number}")
                return redirect(url_for('home.home', order_number=next_order.order_number))
            else:
                flash('Yeni bir sipariş bulunamadı.', 'info')
                print("No new order found.")
        else:
            flash('Barkodlar uyuşmuyor, lütfen tekrar deneyin!', 'danger')
            print("Barcodes do not match.")
            return redirect(url_for('home.home'))

    except Exception as e:
        print(f"Hata: {e}")
        traceback.print_exc()
        flash('Bir hata oluştu.', 'danger')

    return redirect(url_for('home.home'))

# Diğer fonksiyonlar
def fetch_orders_from_api():
    # Base64 ile Authorization oluşturma
    auth_str = f"{API_KEY}:{API_SECRET}"
    b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')

    url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/orders"
    headers = {
        "Authorization": f"Basic {b64_auth_str}",
        "Content-Type": "application/json"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()  # API'den dönen JSON veriyi döner
    else:
        print(f"API'den siparişler çekilirken hata oluştu: {response.status_code} - {response.text}")
        return []

def update_package_to_picking(supplier_id, package_id, line_id, quantity):
    url = f"{BASE_URL}suppliers/{supplier_id}/shipment-packages/{package_id}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {base64.b64encode(f'{API_KEY}:{API_SECRET}'.encode()).decode()}"
    }

    payload = {
        "lines": [{
            "lineId": line_id,
            "quantity": quantity
        }],
        "params": {},
        "status": "Picking"
    }

    print(f"Sending API request to URL: {url}")
    print(f"Headers: {headers}")
    print(f"Payload: {payload}")

    response = requests.put(url, headers=headers, json=payload)

    if response.status_code == 200:
        print(f"Paket başarıyla Picking statüsüne güncellendi. Yanıt: {response.json()}")
    else:
        print(f"Paket güncellenemedi! Hata kodu: {response.status_code}")
        print(f"API Yanıtı: {response.text}")
