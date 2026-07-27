"""
generar_vea_cine_series.py
----------------------------------------------------------------
Genera vea_cine_series.json con el mismo formato que vea_latest.json:
    { "notas": [ {"title": "...", "url": "...", "image_url": "..."} ] }
 
Filtra por el tag de taxonomía de Piano/Cxense:
    revista-vea/peliculas-series-y-novelas
 
SUPUESTOS que hice (ajusta si tu pipeline real es distinto):
  1. Rango de fechas: últimos 7 días (puedes cambiar RANGO_DIAS).
  2. Top 5 artículos por "events" (vistas). Cambia TOP_N si quieres más.
  3. La imagen se obtiene leyendo la etiqueta <meta property="og:image">
     de cada URL, porque el reporte de tráfico de Piano NO devuelve
     imágenes. Si tu script actual de "Lo Último" saca la imagen de
     otro lado (otro campo de Piano, o el CMS), avísame y lo cambio
     para que ambos scripts sean consistentes.
  4. NO incluí aquí el paso de subir el JSON a GitHub (commit/push),
     porque no sé cómo lo hace tu pipeline actual de vea_latest.json.
     Agrega ese mismo paso al final de este script, o dime cómo lo
     hacen y lo integro.
----------------------------------------------------------------
"""
 
import json
import hmac
import hashlib
import http.client
import re
import time
from datetime import datetime, timedelta
 
import requests
 
# ============================================================
# 1. CREDENCIALES
#    Se leen de variables de entorno (NO se escriben aquí).
#    Esto es más seguro: si usas GitHub Actions, las configuras
#    como "Secrets" en el repositorio, nunca quedan visibles.
# ============================================================
import os
 
_username = os.environ.get("PIANO_USERNAME", "")
_secret = os.environ.get("PIANO_SECRET", "")
 
if not _username or not _secret:
    raise Exception(
        "Faltan credenciales. Define PIANO_USERNAME y PIANO_SECRET "
        "como variables de entorno (o como Secrets en GitHub Actions)."
    )
 
sites = [
    "1136350383123139311",
    "1139737519858026179",
    "1139744806016722269",
    "1140889074940917807",
    "1354837713151640420",
    "1139736909200993280",
    "9222263900732340960",
    "1136385303456571305",
    "1137487264126862947",
    "1137492443705443966",
    "1135197808711567685",
    "1355978630884678489",
    "1353734962957051748",
    "1355999898595404985",
]
 
TAG_CINE_SERIES = "revista-vea/peliculas-series-y-novelas"
RANGO_DIAS = 7
TOP_N = 5
SALIDA_JSON = "vea_cine_series.json"
 
 
def cxApi(path, obj):
    date = datetime.utcnow().isoformat() + "Z"
    signature = hmac.new(_secret.encode("utf-8"), date.encode("utf-8"), digestmod=hashlib.sha256).hexdigest()
    headers = {"X-cXense-Authentication": "username=%s date=%s hmac-sha256-hex=%s" % (_username, date, signature)}
    connection = http.client.HTTPSConnection("api.cxense.com", 443)
    connection.request("POST", path, json.dumps(obj), headers)
    response = connection.getresponse()
    status = response.status
    responseObj = json.loads(response.read().decode("utf-8"))
    connection.close()
    return status, responseObj
 
 
def obtener_top_cine_series():
    stop = datetime.utcnow()
    start = stop - timedelta(days=RANGO_DIAS)
 
    req = {
        "siteIds": sites,
        "fields": ["events", "uniqueUsers", "title"],
        "groups": ["url"],
        "count": 50,
        "filters": [
            {"group": "taxonomy", "item": TAG_CINE_SERIES, "type": "keyword"}
        ],
        "start": start.strftime("%Y-%m-%dT%H:%M:%S.0-0500"),
        "stop": stop.strftime("%Y-%m-%dT%H:%M:%S.0-0500"),
    }
 
    status, resp = cxApi("/traffic/event", req)
    if status != 200:
        raise Exception("Error consultando Piano/Cxense: %s" % resp)
 
    items = resp.get("groups", [{}])[0].get("items", [])
    items_ordenados = sorted(items, key=lambda it: it["data"].get("events", 0), reverse=True)
    return items_ordenados[:TOP_N]
 
 
IMAGEN_RESPALDO = "https://www.elespectador.com/pf/resources/images/logoShort.svg?d=1197"
 
def extraer_og_image_y_descripcion(url, intentos=3):
    imagen, descripcion = "", ""
    articulo_vivo = False
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "es-CO,es;q=0.9",
    }
    for intento in range(intentos):
        try:
            r = requests.get(url, timeout=12, headers=headers, allow_redirects=True)
            if r.status_code >= 400:
                print("  [!] Intento %d: %s respondió código %d (posible link roto/retirado)" % (intento + 1, url, r.status_code))
                articulo_vivo = False
            else:
                articulo_vivo = 'article:published_time' in r.text or 'cXenseParse:articleid' in r.text
                if not articulo_vivo:
                    print("  [!] Intento %d: %s no parece ser un artículo válido (genérico, bloqueo anti-bot, o retirado)" % (intento + 1, url))
                else:
                    m_img = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', r.text, re.I)
                    if m_img:
                        imagen = m_img.group(1)
                    m_desc = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', r.text, re.I)
                    if m_desc:
                        descripcion = m_desc.group(1)
            if articulo_vivo and imagen:
                break
        except Exception as e:
            print("  [!] Intento %d falló para %s: %s" % (intento + 1, url, e))
        if not (articulo_vivo and imagen) and intento < intentos - 1:
            time.sleep(3)
 
    if not articulo_vivo:
        return None, None, False
 
    if not imagen:
        print("  [!] No se pudo obtener imagen de %s tras %d intentos, uso imagen de respaldo" % (url, intentos))
        imagen = IMAGEN_RESPALDO
 
    return imagen, descripcion, True    return imagen, descripcion
 
 
def main():
    print("Consultando Piano/Cxense (tag: %s)..." % TAG_CINE_SERIES)
    top_items = obtener_top_cine_series()
    print("Encontrados %d artículos." % len(top_items))
 
    notas = []
    for it in top_items:
        url = it.get("item", "")
        title = it.get("title", "(sin título)")
        if not url:
            continue
        print("  -> %s" % title)
        image_url, resumen, vivo = extraer_og_image_y_descripcion(url)
        if not vivo:
            print("     [descartada: el link ya no existe / fue retirado]")
            continue
        notas.append({"title": title, "url": url, "image_url": image_url, "resumen": resumen})
 
    salida = {"notas": notas}
    with open(SALIDA_JSON, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
 
    print("\nListo. Se guardó %s con %d notas." % (SALIDA_JSON, len(notas)))
    print("Súbelo al mismo repositorio de GitHub donde está vea_latest.json,")
    print("con el mismo paso (commit + push) que usa ese script hoy.")
 
 
if __name__ == "__main__":
    main()
