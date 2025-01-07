from flask import Blueprint, render_template, jsonify, request
from models import db, Order, Product
from sqlalchemy import func
from datetime import datetime, timedelta
import json

analysis_bp = Blueprint('analysis', __name__)

# Yukarıdaki büyük sözlüğü ekliyoruz
TURKEY_CITIES_DISTRICTS = {
    "Adana": [
        "Aladağ", "Ceyhan", "Çukurova", "Feke", "İmamoğlu", "Karaisalı",
        "Karataş", "Kozan", "Pozantı", "Saimbeyli", "Sarıçam", "Seyhan",
        "Tufanbeyli", "Yumurtalık", "Yüreğir"
    ],
    "Adıyaman": [
        "Besni", "Çelikhan", "Gerger", "Gölbaşı", "Kahta", "Merkez",
        "Samsat", "Sincik", "Tut"
    ],
    "Afyonkarahisar": [
        "Başmakçı", "Bayat", "Bolvadin", "Çay", "Çobanlar", "Dazkırı",
        "Dinar", "Emirdağ", "Evciler", "Hocalar", "İhsaniye", "İscehisar",
        "Kızılören", "Merkez", "Sandıklı", "Sinanpaşa", "Şuhut", "Sultandağı"
    ],
    "Ağrı": [
        "Diyadin", "Doğubayazıt", "Eleşkirt", "Hamur", "Merkez",
        "Patnos", "Taşlıçay", "Tutak"
    ],
    "Aksaray": [
        "Ağaçören", "Eskil", "Gülağaç", "Güzelyurt", "Merkez",
        "Ortaköy", "Sarıyahşi", "Sultanhanı"
    ],
    "Amasya": [
        "Göynücek", "Gümüşhacıköy", "Hamamözü", "Merkez",
        "Merzifon", "Suluova", "Taşova"
    ],
    "Ankara": [
        "Akyurt", "Altındağ", "Ayaş", "Bala", "Beypazarı", "Çamlıdere",
        "Çankaya", "Çubuk", "Elmadağ", "Etimesgut", "Evren", "Gölbaşı",
        "Haymana", "Kahramankazan", "Kalecik", "Keçiören", "Kızılcahamam",
        "Mamak", "Nallıhan", "Polatlı", "Pursaklar", "Şereflikoçhisar",
        "Sincan", "Yenimahalle"
    ],
    "Antalya": [
        "Akseki", "Aksu", "Alanya", "Demre", "Döşemealtı", "Elmalı",
        "Finike", "Gazipaşa", "Gündoğmuş", "İbradı", "Kaş", "Kemer",
        "Kepez", "Konyaaltı", "Korkuteli", "Kumluca", "Manavgat",
        "Muratpaşa", "Serik"
    ],
    "Ardahan": [
        "Çıldır", "Damal", "Göle", "Hanak", "Merkez", "Posof"
    ],
    "Artvin": [
        "Ardanuç", "Arhavi", "Borçka", "Hopa", "Kemalpaşa", "Murgul",
        "Merkez", "Şavşat", "Yusufeli"
    ],
    "Aydın": [
        "Bozdoğan", "Buharkent", "Çine", "Didim", "Efeler", "Germencik",
        "İncirliova", "Karpuzlu", "Koçarlı", "Köşk", "Kuşadası",
        "Kuyucak", "Nazilli", "Söke", "Sultanhisar", "Yenipazar"
    ],
    "Balıkesir": [
        "Altıeylül", "Ayvalık", "Balya", "Bandırma", "Bigadiç",
        "Burhaniye", "Dursunbey", "Edremit", "Erdek", "Gömeç", "Gönen",
        "Havran", "İvrindi", "Karesi", "Kepsut", "Manyas",
        "Marmara", "Savaştepe", "Sındırgı", "Susurluk"
    ],
    "Bartın": [
        "Amasra", "Kurucaşile", "Merkez", "Ulus"
    ],
    "Batman": [
        "Beşiri", "Gercüş", "Hasankeyf", "Kozluk", "Merkez", "Sason"
    ],
    "Bayburt": [
        "Aydıntepe", "Demirözü", "Merkez"
    ],
    "Bilecik": [
        "Bozüyük", "Gölpazarı", "İnhisar", "Merkez", "Osmaneli",
        "Pazaryeri", "Söğüt", "Yenipazar"
    ],
    "Bingöl": [
        "Adaklı", "Genç", "Karlıova", "Kiğı", "Merkez",
        "Solhan", "Yayladere", "Yedisu"
    ],
    "Bitlis": [
        "Adilcevaz", "Ahlat", "Güroymak", "Hizan", "Merkez", "Mutki", "Tatvan"
    ],
    "Bolu": [
        "Dörtdivan", "Gerede", "Göynük", "Kıbrıscık", "Mengen",
        "Merkez", "Mudurnu", "Seben", "Yeniçağa"
    ],
    "Burdur": [
        "Ağlasun", "Altınyayla", "Bucak", "Çavdır", "Çeltikçi", "Gölhisar",
        "Karamanlı", "Kemer", "Merkez", "Tefenni", "Yeşilova"
    ],
    "Bursa": [
        "Büyükorhan", "Gemlik", "Gürsu", "Harmancık", "İnegöl", "İznik",
        "Karacabey", "Keles", "Kestel", "Mudanya", "Mustafakemalpaşa",
        "Nilüfer", "Orhaneli", "Orhangazi", "Osmangazi",
        "Yenişehir", "Yıldırım"
    ],
    "Çanakkale": [
        "Ayvacık", "Bayramiç", "Biga", "Bozcaada", "Çan", "Eceabat",
        "Ezine", "Gelibolu", "Gökçeada", "Lapseki", "Merkez", "Yenice"
    ],
    "Çankırı": [
        "Atkaracalar", "Bayramören", "Çerkeş", "Eldivan", "Ilgaz",
        "Kızılırmak", "Korgun", "Kurşunlu", "Merkez", "Orta",
        "Şabanözü", "Yapraklı"
    ],
    "Çorum": [
        "Alaca", "Bayat", "Boğazkale", "Dodurga", "İskilip", "Kargı",
        "Laçin", "Mecitözü", "Merkez", "Oğuzlar", "Ortaköy", "Osmancık",
        "Sungurlu", "Uğurludağ"
    ],
    "Denizli": [
        "Acıpayam", "Babadağ", "Baklan", "Bekilli", "Beyağaç", "Bozkurt",
        "Buldan", "Çal", "Çameli", "Çardak", "Çivril", "Güney",
        "Honaz", "Kale", "Merkezefendi", "Pamukkale", "Sarayköy",
        "Serinhisar", "Tavas"
    ],
    "Diyarbakır": [
        "Bağlar", "Bismil", "Çermik", "Çınar", "Çüngüş", "Dicle",
        "Ergani", "Hani", "Hazro", "Kayapınar", "Kocaköy", "Kulp",
        "Lice", "Silvan", "Sur", "Yenişehir"
    ],
    "Düzce": [
        "Akçakoca", "Cumayeri", "Çilimli", "Gölyaka", "Gümüşova",
        "Kaynaşlı", "Merkez", "Yığılca"
    ],
    "Edirne": [
        "Enez", "Havsa", "İpsala", "Keşan", "Lalapaşa",
        "Meriç", "Merkez", "Süloğlu", "Uzunköprü"
    ],
    "Elazığ": [
        "Ağın", "Alacakaya", "Arıcak", "Baskil", "Karakoçan",
        "Keban", "Maden", "Merkez", "Palu", "Sivrice"
    ],
    "Erzincan": [
        "Çayırlı", "İliç", "Kemah", "Kemaliye", "Merkez",
        "Otlukbeli", "Refahiye", "Tercan", "Üzümlü"
    ],
    "Erzurum": [
        "Aşkale", "Aziziye", "Çat", "Hınıs", "Horasan", "İspir",
        "Karaçoban", "Karayazı", "Köprüköy", "Narman", "Oltu",
        "Olur", "Palandöken", "Pasinler", "Pazaryolu", "Şenkaya",
        "Tekman", "Tortum", "Uzundere", "Yakutiye"
    ],
    "Eskişehir": [
        "Alpu", "Beylikova", "Çifteler", "Günyüzü", "Han", "İnönü",
        "Mahmudiye", "Mihalgazi", "Mihalıççık", "Odunpazarı",
        "Sarıcakaya", "Seyitgazi", "Sivrihisar", "Tepebaşı"
    ],
    "Gaziantep": [
        "Araban", "İslahiye", "Karkamış", "Nizip", "Nurdağı",
        "Oğuzeli", "Şahinbey", "Şehitkamil", "Yavuzeli"
    ],
    "Giresun": [
        "Alucra", "Bulancak", "Çamoluk", "Çanakçı", "Dereli", "Doğankent",
        "Espiye", "Eynesil", "Görele", "Güce", "Keşap", "Merkez",
        "Piraziz", "Şebinkarahisar", "Tirebolu", "Yağlıdere"
    ],
    "Gümüşhane": [
        "Kelkit", "Köse", "Kürtün", "Merkez", "Şiran", "Torul"
    ],
    "Hakkari": [
        "Çukurca", "Derecik", "Merkez", "Şemdinli", "Yüksekova"
    ],
    "Hatay": [
        "Altınözü", "Antakya", "Arsuz", "Defne", "Dörtyol", "Erzin",
        "Hassa", "İskenderun", "Kırıkhan", "Kumlu", "Payas",
        "Reyhanlı", "Samandağ", "Yayladağı"
    ],
    "Iğdır": [
        "Aralık", "Karakoyunlu", "Merkez", "Tuzluca"
    ],
    "Isparta": [
        "Aksu", "Atabey", "Eğirdir", "Gelendost", "Gönen",
        "Keçiborlu", "Merkez", "Şarkikaraağaç", "Senirkent",
        "Sütçüler", "Uluborlu", "Yalvaç", "Yenişarbademli"
    ],
    "İstanbul": [
        "Adalar", "Arnavutköy", "Ataşehir", "Avcılar", "Bağcılar",
        "Bahçelievler", "Bakırköy", "Başakşehir", "Bayrampaşa",
        "Beşiktaş", "Beykoz", "Beylikdüzü", "Beyoğlu", "Büyükçekmece",
        "Çatalca", "Çekmeköy", "Esenler", "Esenyurt", "Eyüpsultan",
        "Fatih", "Gaziosmanpaşa", "Güngören", "Kadıköy", "Kağıthane",
        "Kartal", "Küçükçekmece", "Maltepe", "Pendik", "Sancaktepe",
        "Sarıyer", "Silivri", "Sultanbeyli", "Sultangazi", "Şile",
        "Şişli", "Tuzla", "Ümraniye", "Üsküdar", "Zeytinburnu"
    ],
    "İzmir": [
        "Aliağa", "Balçova", "Bayındır", "Bayraklı", "Bergama",
        "Beydağ", "Bornova", "Buca", "Çeşme", "Çiğli", "Dikili",
        "Foça", "Gaziemir", "Güzelbahçe", "Karabağlar", "Karaburun",
        "Karşıyaka", "Kemalpaşa", "Kınık", "Kiraz", "Konak",
        "Menderes", "Menemen", "Narlıdere", "Ödemiş", "Seferihisar",
        "Selçuk", "Tire", "Torbalı", "Urla"
    ],
    "Kahramanmaraş": [
        "Afşin", "Andırın", "Dulkadiroğlu", "Ekinözü", "Elbistan",
        "Göksun", "Nurhak", "Onikişubat", "Pazarcık", "Türkoğlu"
    ],
    "Karabük": [
        "Eflani", "Eskipazar", "Merkez", "Ovacık", "Safranbolu", "Yenice"
    ],
    "Karaman": [
        "Ayrancı", "Başyayla", "Ermenek", "Kazımkarabekir", "Merkez",
        "Sarıveliler"
    ],
    "Kars": [
        "Akyaka", "Arpaçay", "Digor", "Kağızman", "Merkez",
        "Sarıkamış", "Selim", "Susuz"
    ],
    "Kastamonu": [
        "Abana", "Ağlı", "Araç", "Azdavay", "Bozkurt", "Cide",
        "Çatalzeytin", "Daday", "Devrekani", "Doğanyurt", "Hanönü",
        "İhsangazi", "İnebolu", "Küre", "Merkez", "Pınarbaşı",
        "Seydiler", "Şenpazar", "Taşköprü", "Tosya"
    ],
    "Kayseri": [
        "Akkışla", "Bünyan", "Develi", "Felahiye", "Hacılar",
        "İncesu", "Kocasinan", "Melikgazi", "Özvatan", "Pınarbaşı",
        "Sarıoğlan", "Sarız", "Talas", "Tomarza", "Yahyalı",
        "Yeşilhisar"
    ],
    "Kırıkkale": [
        "Bahşili", "Balışeyh", "Çelebi", "Delice", "Karakeçili",
        "Keskin", "Merkez", "Sulakyurt", "Yahşihan"
    ],
    "Kırklareli": [
        "Babaeski", "Demirköy", "Kofçaz", "Lüleburgaz", "Merkez",
        "Pehlivanköy", "Pınarhisar", "Vize"
    ],
    "Kırşehir": [
        "Akçakent", "Akpınar", "Boztepe", "Çiçekdağı", "Kaman",
        "Merkez", "Mucur"
    ],
    "Kilis": [
        "Elbeyli", "Merkez", "Musabeyli", "Polateli"
    ],
    "Kocaeli": [
        "Başiskele", "Çayırova", "Darıca", "Derince", "Dilovası",
        "Gebze", "Gölcük", "İzmit", "Kandıra", "Karamürsel",
        "Kartepe", "Körfez"
    ],
    "Konya": [
        "Ahırlı", "Akören", "Akşehir", "Altınekin", "Beyşehir", "Bozkır",
        "Çumra", "Derbent", "Derebucak", "Doğanhisar", "Emirgazi",
        "Ereğli", "Güneysınır", "Hadim", "Halkapınar", "Hüyük",
        "Ilgın", "Kadınhanı", "Karapınar", "Karatay", "Kulu", "Meram",
        "Sarayönü", "Selçuklu", "Seydişehir", "Taşkent", "Tuzlukçu",
        "Yalıhüyük", "Yunak"
    ],
    "Kütahya": [
        "Altıntaş", "Aslanapa", "Çavdarhisar", "Domaniç", "Dumlupınar",
        "Emet", "Gediz", "Hisarcık", "Merkez", "Pazarlar",
        "Şaphane", "Simav", "Tavşanlı"
    ],
    "Malatya": [
        "Akçadağ", "Arapgir", "Arguvan", "Battalgazi", "Darende",
        "Doğanşehir", "Doğanyol", "Hekimhan", "Kale", "Kuluncak",
        "Pütürge", "Yazıhan", "Yeşilyurt"
    ],
    "Manisa": [
        "Ahmetli", "Akhisar", "Alaşehir", "Demirci", "Gölmarmara",
        "Gördes", "Kırkağaç", "Köprübaşı", "Kula", "Salihli", "Sarıgöl",
        "Saruhanlı", "Selendi", "Soma", "Şehzadeler", "Turgutlu",
        "Yunusemre"
    ],
    "Mardin": [
        "Artuklu", "Dargeçit", "Derik", "Kızıltepe", "Mazıdağı",
        "Midyat", "Nusaybin", "Ömerli", "Savur", "Yeşilli"
    ],
    "Mersin": [
        "Akdeniz", "Anamur", "Aydıncık", "Bozyazı", "Çamlıyayla",
        "Erdemli", "Gülnar", "Mezitli", "Mut", "Silifke",
        "Tarsus", "Toroslar", "Yenişehir"
    ],
    "Muğla": [
        "Bodrum", "Dalaman", "Datça", "Fethiye", "Kavaklıdere",
        "Köyceğiz", "Marmaris", "Menteşe", "Milas", "Ortaca",
        "Seydikemer", "Ula", "Yatağan"
    ],
    "Muş": [
        "Bulanık", "Hasköy", "Korkut", "Malazgirt", "Merkez", "Varto"
    ],
    "Nevşehir": [
        "Acıgöl", "Avanos", "Derinkuyu", "Gülşehir", "Hacıbektaş",
        "Kozaklı", "Merkez", "Ürgüp"
    ],
    "Niğde": [
        "Altunhisar", "Bor", "Çamardı", "Çiftlik", "Merkez", "Ulukışla"
    ],
    "Ordu": [
        "Akkuş", "Altınordu", "Aybastı", "Çamaş", "Çatalpınar",
        "Çaybaşı", "Fatsa", "Gölköy", "Gülyalı", "Gürgentepe", "İkizce",
        "Kabadüz", "Kabataş", "Korgan", "Kumru", "Mesudiye",
        "Perşembe", "Ulubey", "Ünye"
    ],
    "Osmaniye": [
        "Bahçe", "Düziçi", "Hasanbeyli", "Kadirli", "Merkez",
        "Sumbas", "Toprakkale"
    ],
    "Rize": [
        "Ardeşen", "Çamlıhemşin", "Çayeli", "Derepazarı", "Fındıklı",
        "Güneysu", "Hemşin", "İkizdere", "İyidere", "Kalkandere",
        "Merkez", "Pazar"
    ],
    "Sakarya": [
        "Adapazarı", "Akyazı", "Arifiye", "Erenler", "Ferizli", "Geyve",
        "Hendek", "Karapürçek", "Karasu", "Kaynarca", "Kocaali",
        "Pamukova", "Sapanca", "Serdivan", "Söğütlü", "Taraklı"
    ],
    "Samsun": [
        "Alaçam", "Asarcık", "Atakum", "Ayvacık", "Bafra", "Canik",
        "Çarşamba", "Havza", "İlkadım", "Kavak", "Ladik", "Ondokuzmayıs",
        "Salıpazarı", "Tekkeköy", "Terme", "Vezirköprü", "Yakakent"
    ],
    "Siirt": [
        "Baykan", "Eruh", "Kurtalan", "Merkez", "Pervari", "Şirvan", "Tillo"
    ],
    "Sinop": [
        "Ayancık", "Boyabat", "Dikmen", "Durağan", "Erfelek", "Gerze",
        "Merkez", "Saraydüzü", "Türkeli"
    ],
    "Sivas": [
        "Akıncılar", "Altınyayla", "Divriği", "Doğanşar", "Gemerek",
        "Gölova", "Gürün", "Hafik", "İmranlı", "Kangal", "Koyulhisar",
        "Merkez", "Suşehri", "Şarkışla", "Ulaş", "Yıldızeli", "Zara"
    ],
    "Şanlıurfa": [
        "Akçakale", "Birecik", "Bozova", "Ceylanpınar", "Eyyübiye",
        "Halfeti", "Haliliye", "Harran", "Hilvan", "Karaköprü",
        "Siverek", "Suruç", "Viranşehir"
    ],
    "Şırnak": [
        "Beytüşşebap", "Cizre", "Güçlükonak", "İdil", "Silopi",
        "Uludere", "Merkez"
    ],
    "Tekirdağ": [
        "Çerkezköy", "Çorlu", "Ergene", "Hayrabolu", "Kapaklı",
        "Malkara", "Muratlı", "Saray", "Süleymanpaşa", "Şarköy"
    ],
    "Tokat": [
        "Almus", "Artova", "Başçiftlik", "Erbaa", "Merkez",
        "Niksar", "Pazar", "Reşadiye", "Sulusaray", "Turhal",
        "Yeşilyurt", "Zile"
    ],
    "Trabzon": [
        "Akçaabat", "Araklı", "Arsin", "Beşikdüzü", "Çarşıbaşı",
        "Çaykara", "Dernekpazarı", "Düzköy", "Hayrat", "Köprübaşı",
        "Maçka", "Of", "Ortahisar", "Sürmene", "Şalpazarı", "Tonya",
        "Vakfıkebir", "Yomra"
    ],
    "Tunceli": [
        "Çemişgezek", "Hozat", "Mazgirt", "Merkez", "Nazımiye",
        "Ovacık", "Pertek", "Pülümür"
    ],
    "Uşak": [
        "Banaz", "Eşme", "Karahallı", "Merkez", "Sivaslı", "Ulubey"
    ],
    "Van": [
        "Bahçesaray", "Başkale", "Çaldıran", "Çatak", "Edremit",
        "Erciş", "Gevaş", "Gürpınar", "İpekyolu", "Muradiye",
        "Özalp", "Saray", "Tuşba"
    ],
    "Yalova": [
        "Altınova", "Armutlu", "Çınarcık", "Çiftlikköy", "Merkez",
        "Termal"
    ],
    "Yozgat": [
        "Akdağmadeni", "Aydıncık", "Boğazlıyan", "Çandır",
        "Çayıralan", "Çekerek", "Kadışehri", "Merkez", "Saraykent",
        "Sarıkaya", "Şefaatli", "Sorgun", "Yenifakılı", "Yerköy"
    ],
    "Zonguldak": [
        "Alaplı", "Çaycuma", "Devrek", "Gökçebey", "Kilimli",
        "Kozlu", "Merkez"
    ]
}

@analysis_bp.route('/api/turkey-cities-districts')
def get_turkey_cities_districts():
    """
    81 il ve her ildeki ilçelerin listesini JSON formatında döndürür.
    """
    return jsonify(TURKEY_CITIES_DISTRICTS)


@analysis_bp.route('/analysis')
def analysis_page():
    return render_template('analysis.html')

@analysis_bp.route('/api/inventory-stats')
def inventory_stats():
    """Stok durumu analizi"""
    products = Product.query.all()
    stock_levels = {
        'low_stock': len([p for p in products if p.stock_quantity < 10]),
        'out_of_stock': len([p for p in products if p.stock_quantity == 0]),
        'healthy_stock': len([p for p in products if p.stock_quantity >= 10])
    }
    return jsonify(stock_levels)

@analysis_bp.route('/api/shipping-performance')
def shipping_performance():
    """Kargo performans analizi"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date and end_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
    else:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
    
    orders = Order.query.filter(
        Order.order_date.between(start_date, end_date)
    ).all()
    
    performance_data = {
        'on_time_delivery': 0,
        'late_delivery': 0,
        'avg_delivery_time': 0
    }
    
    delivery_times = []
    for order in orders:
        if order.delivery_date and order.order_date:
            delivery_time = (order.delivery_date - order.order_date).days
            delivery_times.append(delivery_time)
            
            if delivery_time <= 3:  # 3 gün ve altı zamanında teslimat sayılır
                performance_data['on_time_delivery'] += 1
            else:
                performance_data['late_delivery'] += 1
    
    if delivery_times:
        performance_data['avg_delivery_time'] = sum(delivery_times) / len(delivery_times)
    
    return jsonify(performance_data)

@analysis_bp.route('/api/sales-prediction')
def sales_prediction():
    """Basit satış tahminleme"""
    last_30_days = datetime.now() - timedelta(days=30)
    
    daily_sales = db.session.query(
        func.date(Order.order_date).label('date'),
        func.count(Order.id).label('count')
    ).filter(
        Order.order_date >= last_30_days
    ).group_by(
        func.date(Order.order_date)
    ).all()
    
    # Son 30 günün ortalamasını al
    total_sales = sum(day.count for day in daily_sales)
    avg_daily_sales = total_sales / 30 if daily_sales else 0
    
    # Gelecek 7 gün için tahmin
    prediction = []
    current_date = datetime.now()
    for i in range(7):
        future_date = current_date + timedelta(days=i)
        prediction.append({
            'date': future_date.strftime('%Y-%m-%d'),
            'predicted_sales': round(avg_daily_sales * (1 + (i * 0.02)), 2)  # Her gün %2 artış varsayımı
        })
    
    return jsonify(prediction)

@analysis_bp.route('/api/sales-stats')
def sales_stats():
    start_date = request.args.get('start_date', None)
    end_date = request.args.get('end_date', None)
    
    if start_date and end_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
    else:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
    
    # Günlük satış miktarları
    daily_sales = db.session.query(
        func.date(Order.order_date).label('date'),
        func.count(Order.id).label('count'),
        func.sum(Order.amount).label('total_amount')
    ).filter(
        Order.order_date >= start_date,
        Order.order_date <= end_date
    ).group_by(
        func.date(Order.order_date)
    ).all()
    
    # Ürün bazlı detaylı satışlar
    product_sales = db.session.query(
        Order.product_barcode,
        Order.merchant_sku,
        Order.product_size,
        Order.product_color,
        Order.product_name,
        func.count(Order.id).label('count'),
        func.sum(Order.amount).label('total_amount')
    ).filter(
        Order.order_date >= start_date,
        Order.order_date <= end_date
    ).group_by(
        Order.product_barcode,
        Order.merchant_sku,
        Order.product_size,
        Order.product_color,
        Order.product_name
    ).order_by(
        func.count(Order.id).desc()
    ).limit(10).all()
    
    # Haftalık büyüme oranları
    weekly_sales = db.session.query(
        func.date_trunc('week', Order.order_date).label('week'),
        func.sum(Order.amount).label('total_amount')
    ).filter(
        Order.order_date >= start_date,
        Order.order_date <= end_date
    ).group_by(
        func.date_trunc('week', Order.order_date)
    ).order_by(
        func.date_trunc('week', Order.order_date)
    ).all()

    weekly_growth = []
    for i in range(1, len(weekly_sales)):
        prev_amount = float(weekly_sales[i-1].total_amount or 0)
        curr_amount = float(weekly_sales[i].total_amount or 0)
        growth_rate = ((curr_amount - prev_amount) / prev_amount * 100) if prev_amount > 0 else 0
        weekly_growth.append({
            'week': str(weekly_sales[i].week.date()),
            'growth_rate': round(growth_rate, 2)
        })

    # En iyi müşteriler analizi
    customer_segments = db.session.query(
        Order.customer_name,
        Order.customer_surname,
        func.count(Order.id).label('order_count'),
        func.sum(Order.amount).label('total_spent'),
        func.avg(Order.amount).label('avg_order_value')
    ).filter(
        Order.order_date >= start_date,
        Order.order_date <= end_date,
        Order.customer_name != '',  # Boş müşteri isimlerini filtrele
        Order.customer_surname != '' # Boş müşteri soyadlarını filtrele
    ).group_by(
        Order.customer_name,
        Order.customer_surname
    ).having(
        func.count(Order.id) > 1  # En az 2 sipariş vermiş olanlar
    ).order_by(
        func.count(Order.id).desc(),  # Önce sipariş sayısına göre
        func.sum(Order.amount).desc()  # Sonra toplam tutara göre sırala
    ).limit(10).all()

    # En çok satın alım yapan şehirler
    top_cities = db.session.query(
        func.substring(Order.customer_address, '([^,]+)(?:,[^,]+)*$').label('city'),
        func.count(Order.id).label('order_count'),
        func.sum(Order.amount).label('total_amount')
    ).filter(
        Order.order_date >= start_date,
        Order.order_date <= end_date
    ).group_by(
        'city'
    ).order_by(
        func.sum(Order.amount).desc()
    ).limit(5).all()

    # Ürün kategorileri
    product_categories = db.session.query(
        func.substring(Order.product_name, '^([^-]+)').label('category'),
        func.count(Order.id).label('count'),
        func.sum(Order.amount).label('total_amount')
    ).filter(
        Order.order_date >= start_date,
        Order.order_date <= end_date
    ).group_by(
        'category'
    ).order_by(
        func.sum(Order.amount).desc()
    ).limit(5).all()

    return jsonify({
        'daily_sales': [{'date': str(d.date), 'count': d.count, 'amount': float(d.total_amount or 0)} for d in daily_sales],
        'product_sales': [{
            'name': p.product_name or 'Bilinmeyen Ürün',
            'barcode': p.product_barcode or '-',
            'sku': p.merchant_sku or '-',
            'size': p.product_size or '-',
            'color': p.product_color or '-',
            'count': p.count,
            'amount': float(p.total_amount or 0)
        } for p in product_sales],
        'weekly_growth': weekly_growth,
        'customer_segments': [{
            'name': f"{c.customer_name} {c.customer_surname}",
            'order_count': c.order_count,
            'total_spent': float(c.total_spent or 0),
            'avg_order': float(c.avg_order_value or 0)
        } for c in customer_segments],
        'top_cities': [{
            'city': str(c.city).strip(),
            'order_count': c.order_count,
            'amount': float(c.total_amount or 0)
        } for c in top_cities],
        'product_categories': [{
            'category': str(c.category).strip(),
            'count': c.count,
            'amount': float(c.total_amount or 0)
        } for c in product_categories]
    })