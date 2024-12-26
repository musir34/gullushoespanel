
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from datetime import datetime
from models import db, MaliyetFisi, Product

maliyet_fisi_bp = Blueprint("maliyet_fisi_bp", __name__)

@maliyet_fisi_bp.route("/maliyet_fisi_sayfasi")
def maliyet_fisi_sayfasi():
    model_kodu = request.args.get('model_kodu', '')
    renk = request.args.get('renk', '')
    
    query = MaliyetFisi.query
    
    if model_kodu:
        query = query.filter(MaliyetFisi.urun_model_kodu.ilike(f'%{model_kodu}%'))
    if renk:
        query = query.filter(MaliyetFisi.renk.ilike(f'%{renk}%'))
        
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    pagination = query.order_by(MaliyetFisi.created_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    fisler = pagination.items
    
    return render_template(
        "maliyet_fisi.html",
        fisler=fisler,
        pagination=pagination
    )

@maliyet_fisi_bp.route("/maliyet_fisi/olustur", methods=["GET", "POST"])
def maliyet_fisi_olustur():
    if request.method == "POST":
        # Form verilerini al
        model_code = request.form.get("model_code")
        selected_color = request.form.get("color")
        
        # Maliyetleri al
        deri_maliyeti = float(request.form.get("deri_maliyeti", 0))
        taban_maliyeti = float(request.form.get("taban_maliyeti", 0))
        aksesuar_maliyeti = float(request.form.get("aksesuar_maliyeti", 0))
        kesim_maliyeti = float(request.form.get("kesim_maliyeti", 0))
        dikim_maliyeti = float(request.form.get("dikim_maliyeti", 0))
        montaj_maliyeti = float(request.form.get("montaj_maliyeti", 0))
        
        # Beden adetlerini al
        beden_35 = int(request.form.get("beden_35", 0))
        beden_36 = int(request.form.get("beden_36", 0))
        beden_37 = int(request.form.get("beden_37", 0))
        beden_38 = int(request.form.get("beden_38", 0))
        beden_39 = int(request.form.get("beden_39", 0))
        beden_40 = int(request.form.get("beden_40", 0))
        beden_41 = int(request.form.get("beden_41", 0))
        
        toplam_adet = (beden_35 + beden_36 + beden_37 + beden_38 + 
                      beden_39 + beden_40 + beden_41)
        
        toplam_maliyet = (deri_maliyeti + taban_maliyeti + aksesuar_maliyeti +
                         kesim_maliyeti + dikim_maliyeti + montaj_maliyeti)
                         
        birim_maliyet = toplam_maliyet / toplam_adet if toplam_adet > 0 else 0
        
        # Ürün görselini al
        product = Product.query.filter_by(product_main_id=model_code).first()
        image_url = f"/static/images/{product.barcode}.jpg" if product else ""
        
        yeni_fis = MaliyetFisi(
            urun_model_kodu=model_code,
            renk=selected_color,
            deri_maliyeti=deri_maliyeti,
            taban_maliyeti=taban_maliyeti,
            aksesuar_maliyeti=aksesuar_maliyeti,
            kesim_maliyeti=kesim_maliyeti,
            dikim_maliyeti=dikim_maliyeti,
            montaj_maliyeti=montaj_maliyeti,
            toplam_maliyet=toplam_maliyet,
            beden_35=beden_35,
            beden_36=beden_36,
            beden_37=beden_37,
            beden_38=beden_38,
            beden_39=beden_39,
            beden_40=beden_40,
            beden_41=beden_41,
            toplam_adet=toplam_adet,
            birim_maliyet=birim_maliyet,
            image_url=image_url
        )
        
        db.session.add(yeni_fis)
        db.session.commit()
        
        return redirect(url_for("maliyet_fisi_bp.maliyet_fisi_sayfasi"))
        
    return render_template("maliyet_fisi_olustur.html")
