from flask import Blueprint
from barcode import get_barcode_class
from barcode.writer import SVGWriter
import barcode
import os
import traceback



barcode_utils_bp = Blueprint('barcode_utils', __name__)

@barcode_utils_bp.route('/')
def index():
    return "Barkod oluşturma uygulaması çalışıyor!"

def generate_barcode(shipping_code):
    if not shipping_code:
        return None

    try:
        # Barkod sınıfını al
        barcode_class = barcode.get_barcode_class('code128')

        # SVGWriter için ayarlar
        options = {
            'module_height': 6,
            'font_size': 6,
            'text_distance': 2.2,
            'quiet_zone': 1
        }

        barcode_image = barcode_class(shipping_code, writer=SVGWriter())

        # Barkod dizini oluştur
        barcode_dir = os.path.join('static', 'barcodes')
        os.makedirs(barcode_dir, exist_ok=True)

        # Dosya adını uzantı olmadan belirtiyoruz
        filename = os.path.join(barcode_dir, shipping_code)
        barcode_image.save(filename, options=options)

        # SVGWriter otomatik olarak .svg uzantısını ekleyecek
        relative_path = os.path.join('barcodes', f"{shipping_code}.svg")
        return relative_path

    except Exception as e:
        traceback.print_exc()
        return None


