from flask import Blueprint, render_template, request, redirect, url_for, jsonify
import json
from datetime import datetime
from models import db, SiparisFisi, Product
from PIL import Image
import os

siparis_fisi_bp = Blueprint("siparis_fisi_bp", __name__)

@siparis_fisi_bp.app_template_filter('json_loads')
def json_loads_filter(s):
    return json.loads(s)


# ------------------------------------------------------------
# YARDIMCI FONKSİYONLAR (Gruplama & Beden Sıralama)
# ------------------------------------------------------------
def group_products_by_model_and_color(products):
    """
    Product tablosundan gelen kayıtları (model, renk) ikilisine göre gruplar.
    Örn: grouped_products[(model_id, color)] = [list_of_products]
    """
    grouped_products = {}
    for product in products:
        # product_main_id veya color eksikse, boş string ile geçici olarak dolduralım
        key = (product.product_main_id or '', product.color or '')
        grouped_products.setdefault(key, []).append(product)
    return grouped_products

def sort_variants_by_size(product_group):
    """
    Ürünlerin 'size' alanını (beden) büyükten küçüğe doğru sıralar.
    Numerik değilse, alfabetik ters sırada sıralama yapar.
    """
    try:
        return sorted(product_group, key=lambda x: float(x.size), reverse=True)
    except (ValueError, TypeError):
        return sorted(product_group, key=lambda x: x.size, reverse=True)


# ------------------------------------------------------------
# YENİ ROTA: /siparis_fisi_urunler
# ------------------------------------------------------------
@siparis_fisi_bp.route("/siparis_fisi_urunler")
def siparis_fisi_urunler():
    """
    Product tablosundaki ürünleri (model_main_id, color) bazında gruplar,
    sayfalama yapar ve 'siparis_fisi_urunler.html' şablonuna gönderir.
    """
    # Tüm veya bir filtreyle çekebilirsiniz (örneğin hidden=False).
    products = Product.query.all()

    # 1) Gruplama: (model, color) bazında
    grouped_products = group_products_by_model_and_color(products)

    # 2) Sayfalama ayarları
    page = request.args.get('page', 1, type=int)
    per_page = 9
    total_groups = len(grouped_products)

    # 3) Grupları keylerine göre sıralayalım
    sorted_keys = sorted(grouped_products.keys())
    paginated_keys = sorted_keys[(page - 1) * per_page : page * per_page]

    # 4) Her grup içindeki product listelerini 'size' alanına göre sırala
    paginated_product_groups = {
        key: sort_variants_by_size(grouped_products[key])
        for key in paginated_keys
    }

    # 5) Toplam sayfa hesabı
    total_pages = (total_groups + per_page - 1) // per_page

    return render_template(
        "siparis_fisi_urunler.html",  # Bu şablonu oluşturmalısınız
        grouped_products=paginated_product_groups,
        page=page,
        per_page=per_page,
        total_pages=total_pages
    )


# ================
# 1) Liste Görünümü
# ================
@siparis_fisi_bp.route("/siparis_fisi_sayfasi", methods=["GET"])
def siparis_fisi_sayfasi():
    """
    'siparis_fisi.html' adlı şablonu aç,
    fişleri tablo/kart şeklinde gösterir
    """
    model_kodu = request.args.get('model_kodu', '')
    renk = request.args.get('renk', '')

    query = SiparisFisi.query

    if model_kodu:
        query = query.filter(SiparisFisi.urun_model_kodu.ilike(f'%{model_kodu}%'))
    if renk:
        query = query.filter(SiparisFisi.renk.ilike(f'%{renk}%'))

    page = request.args.get('page', 1, type=int)
    per_page = 20  # Her sayfada gösterilecek fiş sayısı

    pagination = query.order_by(SiparisFisi.created_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    fisler = pagination.items

    return render_template(
        "siparis_fisi.html",
        fisler=fisler,
        pagination=pagination
    )


# =====================
# 2) Özet Liste Görünümü
# =====================
@siparis_fisi_bp.route("/siparis_fisi_listesi", methods=["GET"])
def siparis_fisi_listesi():
    """
    'siparis_fisi_listesi.html' adlı şablonu aç,
    fişlerin sadece ID, tarih vb. gibi özet bilgilerini göstermek için
    """
    fisler = SiparisFisi.query.order_by(SiparisFisi.created_date.desc()).all()
    return render_template("siparis_fisi_listesi.html", fisler=fisler)


# ======================
# 3) Tek Fiş Yazdırma
# ======================
@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/yazdir", methods=["GET"])
def siparis_fisi_yazdir(siparis_id):
    """
    Tek bir fişi yazdırmak için şablonu döner.
    'multiple=False' parametresi ile, şablonda
    tekli yazdırma olduğunu belirtiyoruz (yeşil nokta).
    """
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    # Yazdırma tarihini güncelle
    fis.print_date = datetime.now()
    db.session.commit()

    return render_template(
        "siparis_fisi_print.html",
        fis=fis,
        multiple=False
    )

@siparis_fisi_bp.route("/siparis_fisi/bos_yazdir")
def bos_yazdir():
    """
    Boş bir fiş şablonu yazdırmak isterseniz kullanılacak endpoint
    """
    return render_template("siparis_fisi_bos_print.html")


# ======================
# 4) Toplu Fiş Yazdırma
# ======================
@siparis_fisi_bp.route("/siparis_fisi/toplu_yazdir/<fis_ids>")
def toplu_yazdir(fis_ids):
    """
    Birden çok fişi aynı anda yazdırmak için,
    'multiple=True' parametresi gönderiyoruz (kırmızı nokta).
    """
    try:
        id_list = [int(id_) for id_ in fis_ids.split(',')]
        fisler = SiparisFisi.query.filter(SiparisFisi.siparis_id.in_(id_list)).all()
        if not fisler:
            return jsonify({"mesaj": "Seçili fişler bulunamadı"}), 404

        # Yazdırma tarihlerini güncelle
        current_time = datetime.now()
        for fis in fisler:
            fis.print_date = current_time
        db.session.commit()

        return render_template(
            "siparis_fisi_toplu_print.html",
            fisler=fisler,
            multiple=True
        )
    except Exception as e:
        return jsonify({"mesaj": "Hata oluştu", "error": str(e)}), 500


# =====================
# 5) Fiş Detay Sayfası
# =====================
@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/detay", methods=["GET"])
def siparis_fisi_detay(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    if not fis.teslim_kayitlari:
        fis.teslim_kayitlari = "[]"
        fis.kalan_adet = fis.toplam_adet
        db.session.commit()

    return render_template("siparis_fisi_detay.html", fis=fis)



@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/teslimat", methods=["POST"])
def teslimat_kaydi_ekle(siparis_id):
    """
    Yeni teslimat kaydı ekle
    """
    try:
        fis = SiparisFisi.query.get(siparis_id)
        if not fis:
            return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

        if not fis.teslim_kayitlari:
            fis.teslim_kayitlari = "[]"

        model_code = request.form.get("model_code")
        color = request.form.get("color")
            
        beden_35 = int(request.form.get("beden_35", 0))
        beden_36 = int(request.form.get("beden_36", 0))
        beden_37 = int(request.form.get("beden_37", 0))
        beden_38 = int(request.form.get("beden_38", 0))
        beden_39 = int(request.form.get("beden_39", 0))
        beden_40 = int(request.form.get("beden_40", 0))
        beden_41 = int(request.form.get("beden_41", 0))

        toplam = beden_35 + beden_36 + beden_37 + beden_38 + beden_39 + beden_40 + beden_41

        # Mevcut kayıtları al
        kayitlar = json.loads(fis.teslim_kayitlari or "[]")

        # Yeni kaydı ekle
        yeni_kayit = {
            "tarih": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "beden_35": beden_35,
            "beden_36": beden_36,
            "beden_37": beden_37,
            "beden_38": beden_38,
            "beden_39": beden_39,
            "beden_40": beden_40,
            "beden_41": beden_41,
            "toplam": toplam
        }
        kayitlar.append(yeni_kayit)

        # Kalan adedi güncelle
        fis.teslim_kayitlari = json.dumps(kayitlar)
        fis.kalan_adet = fis.toplam_adet - sum(k["toplam"] for k in kayitlar)

        # Stokları güncelle
        if beden_35 > 0 and fis.barkod_35:
            product = Product.query.filter_by(barcode=fis.barkod_35).first()
            if product:
                product.quantity += beden_35
        if beden_36 > 0 and fis.barkod_36:
            product = Product.query.filter_by(barcode=fis.barkod_36).first()
            if product:
                product.quantity += beden_36
        if beden_37 > 0 and fis.barkod_37:
            product = Product.query.filter_by(barcode=fis.barkod_37).first()
            if product:
                product.quantity += beden_37
        if beden_38 > 0 and fis.barkod_38:
            product = Product.query.filter_by(barcode=fis.barkod_38).first()
            if product:
                product.quantity += beden_38
        if beden_39 > 0 and fis.barkod_39:
            product = Product.query.filter_by(barcode=fis.barkod_39).first()
            if product:
                product.quantity += beden_39
        if beden_40 > 0 and fis.barkod_40:
            product = Product.query.filter_by(barcode=fis.barkod_40).first()
            if product:
                product.quantity += beden_40
        if beden_41 > 0 and fis.barkod_41:
            product = Product.query.filter_by(barcode=fis.barkod_41).first()
            if product:
                product.quantity += beden_41

        db.session.commit()
        return redirect(url_for("siparis_fisi_bp.siparis_fisi_detay", siparis_id=siparis_id))

    except Exception as e:
        return jsonify({"mesaj": f"Hata oluştu: {str(e)}"}), 500


# ==================================
# 6) YENİ SİPARİŞ FİŞİ OLUŞTUR (Form)
# ==================================
@siparis_fisi_bp.route("/siparis_fisi/olustur", methods=["GET", "POST"])
def siparis_fisi_olustur():
    search_query = request.args.get('search', '').strip()

    # Base query
    query = Product.query.with_entities(
        Product.product_main_id.label('title'),
        Product.color
    )

    # Filtre
    if search_query:
        query = query.filter(Product.product_main_id == search_query)  # Tam eşleşme

    # Ürünleri gruplu çek
    urunler = query.group_by(Product.product_main_id, Product.color).all()

    if request.method == "POST":
        # Formdan birden çok model satırı al
        model_codes = request.form.getlist("model_codes[]")
        colors = request.form.getlist("colors[]")
        cift_basi_fiyat_list = request.form.getlist("cift_basi_fiyat[]")  # her satır için fiyat
        beden_35_list = request.form.getlist("beden_35[]")
        beden_36_list = request.form.getlist("beden_36[]")
        beden_37_list = request.form.getlist("beden_37[]")
        beden_38_list = request.form.getlist("beden_38[]")
        beden_39_list = request.form.getlist("beden_39[]")
        beden_40_list = request.form.getlist("beden_40[]")
        beden_41_list = request.form.getlist("beden_41[]")

        kalemler = []
        total_adet = 0
        total_fiyat = 0

        def parse_or_zero(lst, index):
            """Liste dolu mu, eleman var mı, int dönüştürülebilir mi? Yoksa 0."""
            if not lst or len(lst) <= index or not lst[index]:
                return 0
            try:
                return int(lst[index])
            except ValueError:
                return 0

        def parse_or_float_zero(lst, index):
            """Benzer mantıkla float dönüştürülür, yoksa 0.0."""
            if not lst or len(lst) <= index or not lst[index]:
                return 0.0
            try:
                return float(lst[index])
            except ValueError:
                return 0.0

        # Bütün satırları gez
        for i in range(len(model_codes)):
            mcode = (model_codes[i] or "").strip()
            clr = (colors[i] or "").strip()
            if not mcode:
                continue

            b35 = parse_or_zero(beden_35_list, i)
            b36 = parse_or_zero(beden_36_list, i)
            b37 = parse_or_zero(beden_37_list, i)
            b38 = parse_or_zero(beden_38_list, i)
            b39 = parse_or_zero(beden_39_list, i)
            b40 = parse_or_zero(beden_40_list, i)
            b41 = parse_or_zero(beden_41_list, i)

            satir_toplam_adet = b35 + b36 + b37 + b38 + b39 + b40 + b41
            cift_fiyat = parse_or_float_zero(cift_basi_fiyat_list, i)
            satir_toplam_fiyat = satir_toplam_adet * cift_fiyat

            # Model + renk'e ait barkodları çekiyoruz (istersen kaydet)
            products = Product.query.filter_by(product_main_id=mcode, color=clr).all()
            barkodlar = {}
            for p in products:
                if p.size and p.barcode:
                    barkodlar[p.size] = p.barcode

            # Bu satırı ekle
            kalemler.append({
                "model_code": mcode,
                "color": clr,
                "beden_35": b35,
                "beden_36": b36,
                "beden_37": b37,
                "beden_38": b38,
                "beden_39": b39,
                "beden_40": b40,
                "beden_41": b41,
                "cift_basi_fiyat": cift_fiyat,
                "satir_toplam_adet": satir_toplam_adet,
                "satir_toplam_fiyat": satir_toplam_fiyat,
                "barkodlar": barkodlar
            })

            total_adet += satir_toplam_adet
            total_fiyat += satir_toplam_fiyat

        if not kalemler:
            return jsonify({"mesaj": "Geçerli satır yok!"}), 400

        # Tek sipariş fişi oluştur
        yeni_fis = SiparisFisi(
            urun_model_kodu="Çoklu Model",  # Burası istersen sabit
            renk="Birden Fazla"
        )

        yeni_fis.toplam_adet = total_adet
        yeni_fis.toplam_fiyat = total_fiyat
        yeni_fis.created_date = datetime.now()

        # kalemler_json diye bir sütun eklediğini varsayıyoruz
        yeni_fis.kalemler_json = json.dumps(kalemler, ensure_ascii=False)

        # Örnek bir image_url istersen
        yeni_fis.image_url = "/static/images/default.jpg"

        db.session.add(yeni_fis)
        db.session.commit()

        # Opsiyonel: Resim boyutlandırma
        image_path = os.path.join('static', 'images', 'default.jpg')
        if os.path.exists(image_path):
            with Image.open(image_path) as img:
                img = img.convert('RGB')
                img = img.resize((250, 150), Image.Resampling.LANCZOS)
                img.save(image_path, 'JPEG', quality=85)

        return redirect(url_for("siparis_fisi_bp.siparis_fisi_sayfasi"))

    else:
        # GET isteği
        return render_template("siparis_fisi_olustur.html", urunler=urunler)



# ===========================
# 7) CRUD JSON Endpoint'leri
# ===========================
@siparis_fisi_bp.route("/siparis_fisi", methods=["GET"])
def get_siparis_fisi_list():
    fisler = SiparisFisi.query.order_by(SiparisFisi.created_date.desc()).all()
    sonuc = []
    for fis in fisler:
        sonuc.append({
            "siparis_id": fis.siparis_id,
            "urun_model_kodu": fis.urun_model_kodu,
            "renk": fis.renk,
            "beden_35": fis.beden_35,
            "beden_36": fis.beden_36,
            "beden_37": fis.beden_37,
            "beden_38": fis.beden_38,
            "beden_39": fis.beden_39,
            "beden_40": fis.beden_40,
            "beden_41": fis.beden_41,
            "cift_basi_fiyat": float(fis.cift_basi_fiyat),
            "toplam_adet": fis.toplam_adet,
            "toplam_fiyat": float(fis.toplam_fiyat),
            "created_date": fis.created_date.strftime("%Y-%m-%d %H:%M:%S") if fis.created_date else None,
            "image_url": fis.image_url
        })
    return jsonify(sonuc), 200

@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>", methods=["GET"])
def get_siparis_fisi(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    return jsonify({
        "siparis_id": fis.siparis_id,
        "urun_model_kodu": fis.urun_model_kodu,
        "renk": fis.renk,
        "beden_35": fis.beden_35,
        "beden_36": fis.beden_36,
        "beden_37": fis.beden_37,
        "beden_38": fis.beden_38,
        "beden_39": fis.beden_39,
        "beden_40": fis.beden_40,
        "beden_41": fis.beden_41,
        "cift_basi_fiyat": float(fis.cift_basi_fiyat),
        "toplam_adet": fis.toplam_adet,
        "toplam_fiyat": float(fis.toplam_fiyat),
        "created_date": fis.created_date.strftime("%Y-%m-%d %H:%M:%S") if fis.created_date else None,
        "image_url": fis.image_url
    }), 200

@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>", methods=["PUT"])
def update_siparis_fisi(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    data = request.json or {}
    fis.urun_model_kodu = data.get("urun_model_kodu", fis.urun_model_kodu)
    fis.renk = data.get("renk", fis.renk)
    fis.beden_35 = data.get("beden_35", fis.beden_35)
    fis.beden_36 = data.get("beden_36", fis.beden_36)
    fis.beden_37 = data.get("beden_37", fis.beden_37)
    fis.beden_38 = data.get("beden_38", fis.beden_38)
    fis.beden_39 = data.get("beden_39", fis.beden_39)
    fis.beden_40 = data.get("beden_40", fis.beden_40)
    fis.beden_41 = data.get("beden_41", fis.beden_41)
    fis.cift_basi_fiyat = data.get("cift_basi_fiyat", fis.cift_basi_fiyat)

    if "image_url" in data:
        fis.image_url = data["image_url"]

    if "created_date" in data:
        created_date_str = data["created_date"]
        fis.created_date = datetime.strptime(created_date_str, "%Y-%m-%d %H:%M:%S")

    # Tekrar hesapla
    fis.toplam_adet = (
        fis.beden_35 + fis.beden_36 + fis.beden_37 +
        fis.beden_38 + fis.beden_39 + fis.beden_40 + fis.beden_41
    )
    fis.toplam_fiyat = float(fis.toplam_adet) * float(fis.cift_basi_fiyat)

    db.session.commit()
    return jsonify({"mesaj": "Sipariş fişi güncellendi."}), 200

@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>", methods=["DELETE"])
def delete_siparis_fisi(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    db.session.delete(fis)
    db.session.commit()


@siparis_fisi_bp.route("/maliyet_fisi_bos", methods=["GET"])
def maliyet_fisi_bos():
    """
    Boş maliyet fişi yazdırma endpoint'i
    """
    from datetime import datetime
    return render_template("maliyet_fisi_print.html", now=datetime.now)

@siparis_fisi_bp.route("/maliyet_fisi/<int:siparis_id>/yazdir", methods=["GET"])
def maliyet_fisi_yazdir(siparis_id):
    """
    Maliyet fişi yazdırma endpoint'i
    """
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    return render_template(
        "maliyet_fisi_print.html",
        fis=fis
    )

    return jsonify({"mesaj": "Sipariş fişi silindi."}), 200
@siparis_fisi_bp.route("/get_product_details/<model_code>")
def get_product_details(model_code):
    products = Product.query.filter_by(product_main_id=model_code).all()
    
    if not products:
        return jsonify({"success": False, "message": "Ürün bulunamadı"})
    
    # Modele ait tüm benzersiz renkleri al
    colors = list(set(p.color for p in products if p.color))
    
    # Renk ve beden-barkod eşleştirmelerini yap
    product_data = {}
    for color in colors:
        product_data[color] = {}
        color_products = [p for p in products if p.color == color]
        for product in color_products:
            if product.size and product.barcode:
                product_data[color][product.size] = product.barcode
    
    return jsonify({
        "success": True,
        "colors": colors,
        "product_data": product_data
    })
