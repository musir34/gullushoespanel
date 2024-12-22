# siparis_fisi.py

from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from datetime import datetime
from models import db, SiparisFisi

siparis_fisi_bp = Blueprint("siparis_fisi_bp", __name__)

# ================
# 1) Liste Gorunumu
# ================
@siparis_fisi_bp.route("/siparis_fisi_sayfasi", methods=["GET"])
def siparis_fisi_sayfasi():
    """
    'siparis_fisi.html' adli sablonu ac,
    fişleri tablo/kart seklinde gosterir
    """
    fisler = SiparisFisi.query.order_by(SiparisFisi.created_date.desc()).all()
    return render_template("siparis_fisi.html", fisler=fisler)

# =====================
# 2) Ozet Liste Gorunumu
# =====================
@siparis_fisi_bp.route("/siparis_fisi_listesi", methods=["GET"])
def siparis_fisi_listesi():
    """
    'siparis_fisi_listesi.html' adli sablonu ac,
    fişlerin sadece ID, tarih vb. gibi ozet bilgilerini gostermek icin
    """
    fisler = SiparisFisi.query.order_by(SiparisFisi.created_date.desc()).all()
    return render_template("siparis_fisi.html", fisler=fisler)

# ======================
# 3) Tek Fisin Detay Sayfasi
# ======================
@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/yazdir", methods=["GET"])
def siparis_fisi_yazdir(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404
    return render_template("siparis_fisi_print.html", fis=fis)

@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/detay", methods=["GET"])
def siparis_fisi_detay(siparis_id):
    """
    'siparis_fisi_detay.html' sablonunda, tek fişin
    (siparis_id) ayrintili bilgilerini gosterir
    """
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    return render_template("siparis_fisi_detay.html", fis=fis)

# ==================================
# 4) YENI SIPARIS FISI OLUSTUR (Form)
# ==================================
@siparis_fisi_bp.route("/siparis_fisi/olustur", methods=["GET", "POST"])
def siparis_fisi_olustur():
    """
    GET: 'siparis_fisi_olustur.html' formu ac
    POST: Form verilerini al -> SiparisFisi nesnesi yarat -> DB'ye kaydet -> Listeye don
    """
    if request.method == "POST":
        # Yeni ana fiş oluştur
        yeni_fis = SiparisFisi()
        db.session.add(yeni_fis)
        db.session.flush()  # siparis_id'yi almak için flush
        
        # Form verilerini al (çoklu model için)
        model_kodlari = request.form.getlist("urun_model_kodu[]")
        renkler = request.form.getlist("renk[]")
        beden_35_list = request.form.getlist("beden_35[]")
        beden_36_list = request.form.getlist("beden_36[]")
        beden_37_list = request.form.getlist("beden_37[]")
        beden_38_list = request.form.getlist("beden_38[]")
        beden_39_list = request.form.getlist("beden_39[]")
        beden_40_list = request.form.getlist("beden_40[]")
        beden_41_list = request.form.getlist("beden_41[]")
        fiyatlar = request.form.getlist("cift_basi_fiyat[]")
        image_urls = request.form.getlist("image_url[]")
        
        toplam_genel = 0
        
        # Her model için detay oluştur
        for i in range(len(model_kodlari)):
            beden_35 = int(beden_35_list[i] or 0)
            beden_36 = int(beden_36_list[i] or 0)
            beden_37 = int(beden_37_list[i] or 0)
            beden_38 = int(beden_38_list[i] or 0)
            beden_39 = int(beden_39_list[i] or 0)
            beden_40 = int(beden_40_list[i] or 0)
            beden_41 = int(beden_41_list[i] or 0)
            
            toplam_adet = (beden_35 + beden_36 + beden_37 +
                          beden_38 + beden_39 + beden_40 + beden_41)
            toplam_fiyat = float(toplam_adet) * float(fiyatlar[i])
            toplam_genel += toplam_fiyat
            
            detay = SiparisFisiDetay(
                siparis_id=yeni_fis.siparis_id,
                urun_model_kodu=model_kodlari[i],
                renk=renkler[i],
                beden_35=beden_35,
                beden_36=beden_36,
                beden_37=beden_37,
                beden_38=beden_38,
                beden_39=beden_39,
                beden_40=beden_40,
                beden_41=beden_41,
                cift_basi_fiyat=fiyatlar[i],
                toplam_adet=toplam_adet,
                toplam_fiyat=toplam_fiyat,
                image_url=image_urls[i] if i < len(image_urls) else ""
            )
            db.session.add(detay)
        
        yeni_fis.toplam_fiyat = toplam_genel

        db.session.add(yeni_fis)
        db.session.commit()

        # Islemi bitince listesine yonlendir
        # Ister 'siparis_fisi_sayfasi' ister 'siparis_fisi_listesi' rotasina donebilirsin
        return redirect(url_for("siparis_fisi_bp.siparis_fisi_sayfasi"))
    else:
        # GET istegi: form sablonu
        return render_template("siparis_fisi_olustur.html")

# ===========================
# 5) CRUD JSON Endpoint'leri
# ===========================

# Tum siparis fislerini JSON getiren
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

# Tek siparis fisini JSON getiren
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

# Guncelleme
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

    # Guncellerken yeni image_url girildi mi
    if "image_url" in data:
        fis.image_url = data["image_url"]

    # created_date'i de degistirmek istersen
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

# Silme
@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>", methods=["DELETE"])
def delete_siparis_fisi(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    db.session.delete(fis)
    db.session.commit()
    return jsonify({"mesaj": "Sipariş fişi silindi."}), 200
