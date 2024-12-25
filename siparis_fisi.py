from flask import Blueprint, render_template, request, redirect, url_for, jsonify
import json
from datetime import datetime
from models import db, SiparisFisi, Product  # Product modelini de ekledik

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
    """
    'siparis_fisi_detay.html' şablonunda, tek fişin
    (siparis_id) ayrıntılı bilgilerini gösterir
    """
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    # Örnek: teslim_kayitlari yoksa default değeri ver
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
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    try:
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

        db.session.commit()
        return redirect(url_for("siparis_fisi_bp.siparis_fisi_detay", siparis_id=siparis_id))

    except Exception as e:
        return jsonify({"mesaj": f"Hata oluştu: {str(e)}"}), 500


# ==================================
# 6) YENİ SİPARİŞ FİŞİ OLUŞTUR (Form)
# ==================================
@siparis_fisi_bp.route("/siparis_fisi/olustur", methods=["GET", "POST"])
def siparis_fisi_olustur():
    # Ürünleri veritabanından çek
    urunler = Product.query.with_entities(
        Product.barcode,
        Product.title,
        Product.color
    ).distinct().all()

    if request.method == "POST":
        # 1) Formdan "barcode" bilgisini alıp products tablosundan ürünü bulalım
        selected_barcode = request.form.get("barcode")  # <select name="barcode"> vb.

        # 2) Seçilen ürünü bul
        product = Product.query.get(selected_barcode)
        if not product:
            return jsonify({"mesaj": "Seçilen ürün bulunamadı!"}), 400

        # 3) Diğer form verileri (bedenler vb.)
        beden_35 = int(request.form.get("beden_35", 0))
        beden_36 = int(request.form.get("beden_36", 0))
        beden_37 = int(request.form.get("beden_37", 0))
        beden_38 = int(request.form.get("beden_38", 0))
        beden_39 = int(request.form.get("beden_39", 0))
        beden_40 = int(request.form.get("beden_40", 0))
        beden_41 = int(request.form.get("beden_41", 0))

        cift_basi_fiyat = float(request.form.get("cift_basi_fiyat", 0))
        image_url = request.form.get("image_url", "")

        # 4) Üründen gelen bilgileri (title, color vs.) sipariş fişine aktaralım
        urun_model_kodu = product.title or "Model Bilgisi Yok"
        renk = product.color or "Renk Bilgisi Yok"

        # 5) Toplam adet ve fiyat hesapla
        toplam_adet = (beden_35 + beden_36 + beden_37 + beden_38 +
                       beden_39 + beden_40 + beden_41)
        toplam_fiyat = float(toplam_adet) * cift_basi_fiyat

        # 6) Yeni fiş nesnesi
        yeni_fis = SiparisFisi(
            urun_model_kodu=urun_model_kodu,
            renk=renk,
            beden_35=beden_35,
            beden_36=beden_36,
            beden_37=beden_37,
            beden_38=beden_38,
            beden_39=beden_39,
            beden_40=beden_40,
            beden_41=beden_41,
            cift_basi_fiyat=cift_basi_fiyat,
            toplam_adet=toplam_adet,
            toplam_fiyat=toplam_fiyat,
            image_url=image_url
        )
        db.session.add(yeni_fis)
        db.session.commit()

        return redirect(url_for("siparis_fisi_bp.siparis_fisi_sayfasi"))

    else:
        # GET isteği: form şablonunu açmadan önce, products tablosundaki ürünleri çekelim
        #urunler = Product.query.filter_by(hidden=False).all()  # hidden=False olanlar
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
    return jsonify({"mesaj": "Sipariş fişi silindi."}), 200