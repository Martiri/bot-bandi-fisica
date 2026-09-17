import csv
from datetime import date, datetime, timedelta
import io
import json
import os
import re
import sys
import time
from urllib.parse import urljoin
import zoneinfo

from bs4 import BeautifulSoup
import requests

# Supporta sia pypdf (moderno) sia PyPDF2 (legacy)
try:
    import pypdf as pdf_lib
except ImportError:
    try:
        import PyPDF2 as pdf_lib
    except ImportError:
        pdf_lib = None

# Fuso orario italiano
try:
    ROME_TZ = zoneinfo.ZoneInfo("Europe/Rome")
except Exception:
    ROME_TZ = None

# Percorsi relativi allo script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
FILE_MEMORIA_LEGACY = os.path.join(SCRIPT_DIR, "bandi_trovati.json")
FILE_CACHE_DETTAGLI = os.path.join(DATA_DIR, "bandi_memoria.json")

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "bandi_attivi.csv")
OUTPUT_HTML = os.path.join(SCRIPT_DIR, "bandi_attivi.html")
OUTPUT_MD_ATTIVI = os.path.join(SCRIPT_DIR, "bandi_attivi.md")
OUTPUT_MD_SCADENZE = os.path.join(SCRIPT_DIR, "bandi_in_scadenza.md")

# URL portale bandi UniBo
BASE_URL = "https://bandi.unibo.it"
URL_OPPORTUNITA = f"{BASE_URL}/agevolazioni/opportunita"
URL_TUTORATO = f"{BASE_URL}/didattica/incarichi-tutorato"

# Configurazione target: Studente 3° anno Laurea Triennale in Fisica (Bologna)
CODICI_CORSO_FISICA = "9244"
TIPO_CORSO_LAUREA = "laurea"
STRUTTURA_DIFA = "difa"  # Dipartimento di Fisica e Astronomia "Augusto Righi"

# Lunghezza massima riassunto estratto
MAX_RIASSUNTO_LEN = 450

MESI_ITA = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12
}

GIORNI_SETTIMANA = [
    "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"
]


def ora_italiana_ora():
    """Restituisce datetime attuale con fuso orario di Roma."""
    if ROME_TZ:
        return datetime.now(ROME_TZ)
    return datetime.now()


def crea_sessione():
    """Inizializza una sessione requests con timeout e User-Agent appropriato."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    })
    return session


def pulisci_spazi(testo):
    return " ".join(testo.split()) if testo else ""


def parse_scadenza(scadenza_str, data_riferimento=None):
    """Estrae la data di scadenza (datetime.date) da una stringa e calcola i giorni rimanenti."""
    if not scadenza_str:
        return None, None

    if data_riferimento is None:
        data_riferimento = ora_italiana_ora().date()

    s_clean = scadenza_str.lower().strip()
    data_scad = None

    # 1. Scadenza con giorno, mese e anno espliciti (es: "16 novembre 2026, 18:00")
    m = re.search(r"(\d{1,2})\s+(" + "|".join(MESI_ITA.keys()) + r")\s+(\d{4})", s_clean)
    if m:
        giorno, mese, anno = int(m.group(1)), MESI_ITA[m.group(2)], int(m.group(3))
        try:
            data_scad = date(anno, mese, giorno)
        except ValueError:
            pass

    # 2. Periodo (es: "settembre - ottobre 2026" o "aprile - giugno 2026")
    if not data_scad:
        m2 = re.search(r"(?:–|-)\s*(" + "|".join(MESI_ITA.keys()) + r")\s+(\d{4})", s_clean)
        if m2:
            mese, anno = MESI_ITA[m2.group(1)], int(m2.group(2))
            # Stima fine mese
            giorni_nel_mese = 30 if mese in (4, 6, 9, 11) else (28 if mese == 2 else 31)
            try:
                data_scad = date(anno, mese, giorni_nel_mese)
            except ValueError:
                pass

    if data_scad:
        giorni_mancanti = (data_scad - data_riferimento).days
        return data_scad, giorni_mancanti

    return None, None


def trova_pdf_nel_bando(session, url_bando):
    """Esamina la pagina di dettaglio del bando per trovare il link al PDF."""
    try:
        r = session.get(url_bando, timeout=12)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            href_low = href.lower()
            if ".pdf" in href_low or "/@@download/file" in href_low or "/download/" in href_low:
                return urljoin(BASE_URL, href)
        return None
    except Exception as e:
        print(f"    ⚠️  Errore ricerca PDF su {url_bando}: {e}")
        return None


def estrai_sintesi_pdf(session, url_pdf):
    """Scarica ed estrae in modo mirato l'oggetto o la finalità dal PDF del bando."""
    if not pdf_lib:
        return "Modulo PDF non disponibile (pypdf/PyPDF2 non installato)."

    try:
        r = session.get(url_pdf, stream=True, timeout=15)
        r.raise_for_status()
        raw = bytearray()
        for chunk in r.iter_content(chunk_size=65536):
            raw.extend(chunk)
            if len(raw) > 4 * 1024 * 1024:  # Max 4 MB
                break

        reader = pdf_lib.PdfReader(io.BytesIO(raw))
        testo = ""
        for pagina in reader.pages[:3]:
            estratto = pagina.extract_text()
            if estratto:
                testo += estratto + "\n"

        if not testo.strip():
            return "Testo del PDF non estratto (possibile scansione immagine)."

        # Cerca Art. 1 / Oggetto o Finalità
        m = re.search(
            r'(?:art(?:icolo|\.)\s*1\b[^\n]*\n)(.*?)(?=\n\s*art(?:icolo|\.)\s*2\b|\Z)',
            testo,
            re.IGNORECASE | re.DOTALL
        )
        if m:
            clean = pulisci_spazi(m.group(1))
            if len(clean) > MAX_RIASSUNTO_LEN:
                clean = clean[:MAX_RIASSUNTO_LEN] + "…"
            return clean

        m2 = re.search(
            r'(?:oggetto|finalit[àa])\s*[:\-–]\s*(.*?)(?=\n\s*(?:art|requisiti|[A-Z0-9\.\-]{3,})|\Z)',
            testo,
            re.IGNORECASE | re.DOTALL
        )
        if m2:
            clean = pulisci_spazi(m2.group(1))
            if len(clean) > MAX_RIASSUNTO_LEN:
                clean = clean[:MAX_RIASSUNTO_LEN] + "…"
            return clean

        righe = [line.strip() for line in testo.splitlines() if line.strip()]
        righe_utili = []
        for riga in righe:
            r_low = riga.lower()
            if any(scarta in r_low for scarta in [
                "responsabile del procedimento", "via marsala", "protocollo", "rep.",
                "alma mater studiorum", "area di campus", "settore servizi", "decreto",
                "visto lo statuto", "visto il regolamento", "la dirigente", "il dirigente"
            ]):
                continue
            righe_utili.append(riga)

        clean = pulisci_spazi(" ".join(righe_utili[:8]))
        if len(clean) > MAX_RIASSUNTO_LEN:
            clean = clean[:MAX_RIASSUNTO_LEN] + "…"
        return clean or "Dettagli completi consultabili nel testo del bando."

    except Exception as e:
        return f"Impossibile leggere il PDF: {e}"


def estrai_dettagli_card(card, categoria_sezione="Opportunità"):
    """Estrae i campi strutturati da una manifesto-card del portale UniBo."""
    h3 = card.find("h3")
    titolo = pulisci_spazi(h3.get_text()) if h3 else "Senza titolo"

    a_tag = card.find("a", href=True)
    if not a_tag:
        return None
    link = urljoin(BASE_URL, a_tag["href"].strip())

    scadenza_el = card.find(class_="details-icon")
    scadenza = pulisci_spazi(scadenza_el.get_text()) if scadenza_el else "Non specificata"

    details = {}
    ul = card.find("ul", class_="details")
    if ul:
        for li in ul.find_all("li"):
            testo_li = li.get_text(" ", strip=True)
            if ":" in testo_li:
                k, v = testo_li.split(":", 1)
                details[k.strip().lower()] = v.strip()

    destinatari = details.get("mi interessa se", "")
    tipo_corso = details.get("tipo di corso", "")
    tipologia = details.get("tipologia", categoria_sezione)
    requisiti = details.get("requisiti", "Non specificati")

    return {
        "titolo": titolo,
        "link": link,
        "scadenza": scadenza,
        "categoria": categoria_sezione,
        "tipologia": tipologia,
        "destinatari": destinatari,
        "tipo_corso": tipo_corso,
        "requisiti": requisiti,
    }


def e_accessibile_terzo_anno_fisica(info_bando):
    """Verifica se il bando è accessibile a uno studente del 3° anno di Fisica Triennale."""
    tipo_corso_low = info_bando["tipo_corso"].lower()
    destinatari_low = info_bando["destinatari"].lower()
    titolo_low = info_bando["titolo"].lower()

    if tipo_corso_low:
        ha_laurea_triennale = ("laurea" in tipo_corso_low.replace("laurea magistrale", ""))
        ha_laurea_semplice = any(
            token.strip() == "laurea" for token in tipo_corso_low.split(",")
        )
        if not (ha_laurea_triennale or ha_laurea_semplice):
            if not any(k in titolo_low for k in ["laurea magistrale", "prosecuzione", "laureand"]):
                return False

    if destinatari_low:
        solo_primo_anno = ("studio al primo anno" in destinatari_low) and ("secondo anno" not in destinatari_low) and ("laurea" not in destinatari_low)
        if solo_primo_anno and not any(k in titolo_low for k in ["laureand", "prova finale", "terzo anno"]):
            return False

    return True


def cerca_bandi_opportunita(session):
    """Interroga la sezione agevolazioni/opportunita per studenti di Fisica Triennale."""
    bandi = []
    visti = set()

    params_fisica = {
        "corsi": CODICI_CORSO_FISICA,
        "tipocorso": TIPO_CORSO_LAUREA,
    }
    try:
        r = session.get(URL_OPPORTUNITA, params=params_fisica, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for acc in soup.find_all(class_="accordion-content"):
            btn = acc.find_previous("button")
            nome_categoria = btn.get_text(strip=True) if btn else "Bandi e Agevolazioni"

            for card in acc.find_all(class_="manifesto-card"):
                info = estrai_dettagli_card(card, nome_categoria)
                if info and e_accessibile_terzo_anno_fisica(info) and info["link"] not in visti:
                    visti.add(info["link"])
                    bandi.append(info)
    except Exception as e:
        print(f"❌ Errore interrogazione portale opportunità: {e}")

    try:
        r_difa = session.get(URL_OPPORTUNITA, params={"struttura": STRUTTURA_DIFA}, timeout=15)
        r_difa.raise_for_status()
        soup_difa = BeautifulSoup(r_difa.text, "html.parser")
        for card in soup_difa.find_all(class_="manifesto-card"):
            info = estrai_dettagli_card(card, "Bandi DIFA / Dipartimento")
            if info and e_accessibile_terzo_anno_fisica(info) and info["link"] not in visti:
                visti.add(info["link"])
                bandi.append(info)
    except Exception as e:
        print(f"⚠️  Errore verifica opportunità DIFA: {e}")

    return bandi


def cerca_bandi_tutorato_difa(session):
    """Controlla se ci sono bandi per incarichi di tutorato didattico afferenti a DIFA o Fisica."""
    bandi_tutorato = []
    try:
        r = session.get(URL_TUTORATO, params={"struttura": STRUTTURA_DIFA}, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if "/s/" in href:
                link_completo = urljoin(BASE_URL, href)
                titolo = pulisci_spazi(a.get_text())
                if len(titolo) > 10 and not any(ign in titolo.lower() for ign in ["vai al", "scadut"]):
                    bandi_tutorato.append({
                        "titolo": titolo,
                        "link": link_completo,
                        "scadenza": "Vedi bando",
                        "categoria": "Incarichi di Tutorato Didattico (DIFA)",
                        "tipologia": "Tutorato",
                        "destinatari": "Studenti/Laureandi Fisica",
                        "tipo_corso": "Laurea / Laurea Magistrale",
                        "requisiti": "Specifici da bando di tutorato",
                    })
    except Exception as e:
        print(f"⚠️  Errore ricerca tutorato DIFA: {e}")

    return bandi_tutorato


def carica_memoria():
    """Carica i link storici noti da bandi_trovati.json e la cache ricca da data/bandi_memoria.json."""
    os.makedirs(DATA_DIR, exist_ok=True)
    memoria_link = set()
    cache_dettagli = {}

    # 1. Carica memoria legacy di link
    if os.path.exists(FILE_MEMORIA_LEGACY):
        try:
            with open(FILE_MEMORIA_LEGACY, "r", encoding="utf-8") as f:
                dati = json.load(f)
                for el in dati:
                    if isinstance(el, str):
                        memoria_link.add(el.strip())
                    elif isinstance(el, dict) and "link" in el:
                        memoria_link.add(el["link"].strip())
        except Exception as e:
            print(f"⚠️  Errore lettura {FILE_MEMORIA_LEGACY}: {e}")

    # 2. Carica cache arricchita con sintesi e PDF già estratti
    if os.path.exists(FILE_CACHE_DETTAGLI):
        try:
            with open(FILE_CACHE_DETTAGLI, "r", encoding="utf-8") as f:
                cache_dettagli = json.load(f)
                if not isinstance(cache_dettagli, dict):
                    cache_dettagli = {}
                for k in cache_dettagli.keys():
                    memoria_link.add(k)
        except Exception as e:
            print(f"⚠️  Errore lettura {FILE_CACHE_DETTAGLI}: {e}")

    return memoria_link, cache_dettagli


def salva_memoria(tutti_link_visti, cache_dettagli):
    """Salva la memoria dei link per retrocompatibilità e il catalogo completo dei dettagli."""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(FILE_MEMORIA_LEGACY, "w", encoding="utf-8") as f:
            json.dump(sorted(list(tutti_link_visti)), f, ensure_ascii=False, indent=2)
        print(f"💾 Salvato {FILE_MEMORIA_LEGACY} ({len(tutti_link_visti)} link totali archiviati).")
    except Exception as e:
        print(f"❌ Errore salvataggio {FILE_MEMORIA_LEGACY}: {e}")

    try:
        with open(FILE_CACHE_DETTAGLI, "w", encoding="utf-8") as f:
            json.dump(cache_dettagli, f, ensure_ascii=False, indent=2)
        print(f"💾 Salvato {FILE_CACHE_DETTAGLI} ({len(cache_dettagli)} schede arricchite).")
    except Exception as e:
        print(f"❌ Errore salvataggio {FILE_CACHE_DETTAGLI}: {e}")


def arricchisci_bandi(session, candidati, memoria_link, cache_dettagli, oggi_str):
    """Arricchisce i bandi con PDF e sintesi, utilizzando la cache per evitare chiamate ripetute."""
    bandi_completi = []
    nuovi_di_oggi = []

    for b in candidati:
        link = b["link"]
        is_nuovo = link not in memoria_link

        # Se già in cache con sintesi, usa i dati memorizzati
        if link in cache_dettagli and cache_dettagli[link].get("riassunto"):
            b_info = dict(cache_dettagli[link])
            # Aggiorna campi dinamici (es. scadenza aggiornata o categoria)
            b_info.update(b)
            b_info["is_nuovo"] = is_nuovo
            b_info["last_seen"] = oggi_str
        else:
            print(f"  ✨ Lettura dettagli bando: {b['titolo'][:60]}...")
            pdf_url = trova_pdf_nel_bando(session, link)
            sintesi = ""
            nota_fonte = ""
            if pdf_url:
                sintesi = estrai_sintesi_pdf(session, pdf_url)
                nota_fonte = "Riassunto estratto dal PDF del bando"
            else:
                try:
                    r = session.get(link, timeout=10)
                    soup = BeautifulSoup(r.text, "html.parser")
                    content = soup.find("div", id="content-core") or soup.find("main")
                    testo_pagina = pulisci_spazi(content.get_text()) if content else ""
                    sintesi = (testo_pagina[:MAX_RIASSUNTO_LEN] + "…") if len(testo_pagina) > MAX_RIASSUNTO_LEN else testo_pagina
                    nota_fonte = "Descrizione tratta dalla scheda informativa web"
                except Exception:
                    sintesi = "Consulta la pagina ufficiale del bando per tutti i requisiti e le modalità."
                    nota_fonte = "Scheda informativa web"

            if not sintesi:
                sintesi = "Nessuna descrizione specificata nel bando."

            b_info = dict(b)
            b_info["pdf_url"] = pdf_url
            b_info["riassunto"] = sintesi
            b_info["nota_fonte"] = nota_fonte
            b_info["first_seen"] = oggi_str
            b_info["last_seen"] = oggi_str
            b_info["is_nuovo"] = is_nuovo

            # Salva in cache
            cache_dettagli[link] = dict(b_info)

        # Calcola data scadenza e giorni rimanenti
        data_scad, giorni_mancanti = parse_scadenza(b_info.get("scadenza", ""))
        b_info["data_scadenza_parsed"] = data_scad.isoformat() if data_scad else None
        b_info["giorni_mancanti"] = giorni_mancanti

        bandi_completi.append(b_info)

        if is_nuovo:
            nuovi_di_oggi.append(b_info)
            memoria_link.add(link)

    # Ordinamento:
    # 1. Bandi con scadenza imminente (giorni_mancanti >= 0) in ordine crescente
    # 2. Bandi senza scadenza definita / tutto l'anno
    # 3. Eventuali già scaduti
    def sort_key(item):
        gm = item.get("giorni_mancanti")
        if gm is not None and gm >= 0:
            return (0, gm)
        elif gm is None:
            return (1, 9999)
        else:
            return (2, gm)

    bandi_completi.sort(key=sort_key)
    return bandi_completi, nuovi_di_oggi


def export_csv(bandi, filepath):
    """Esporta tutti i bandi in formato CSV compatibile Excel/Google Sheets."""
    fieldnames = [
        "Titolo",
        "Categoria",
        "Tipologia",
        "Scadenza",
        "Giorni Alla Scadenza",
        "Destinatari",
        "Requisiti",
        "Sintesi Oggetto",
        "Link Bando",
        "Link PDF"
    ]
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for b in bandi:
            gm = b.get("giorni_mancanti")
            gm_str = f"{gm} giorni" if gm is not None and gm >= 0 else ("Scaduto" if gm is not None else "Aperto / N/D")
            writer.writerow({
                "Titolo": b.get("titolo", ""),
                "Categoria": b.get("categoria", ""),
                "Tipologia": b.get("tipologia", ""),
                "Scadenza": b.get("scadenza", ""),
                "Giorni Alla Scadenza": gm_str,
                "Destinatari": b.get("destinatari", ""),
                "Requisiti": b.get("requisiti", ""),
                "Sintesi Oggetto": b.get("riassunto", ""),
                "Link Bando": b.get("link", ""),
                "Link PDF": b.get("pdf_url", "") or ""
            })


def export_markdown_table(bandi, filepath, titolo):
    """Esporta un file Markdown con la tabella formattata."""
    lines = [f"# {titolo}\n"]
    if not bandi:
        lines.append("*Nessun bando presente.*\n")
    else:
        lines.append("| N° | Titolo Bando | Categoria | Scadenza | Scheda UniBo | PDF Bando |")
        lines.append("| :---: | :--- | :--- | :--- | :---: | :---: |")
        for i, b in enumerate(bandi, 1):
            pdf_cell = f"[Scarica PDF]({b['pdf_url']})" if b.get("pdf_url") else "-"
            scad = b.get("scadenza", "-")
            gm = b.get("giorni_mancanti")
            if gm is not None and 0 <= gm <= 30:
                scad = f"🔥 **{scad}** *(mancano {gm} gg)*"
            lines.append(f"| {i} | **[{b['titolo']}]({b['link']})** | {b['categoria']} | {scad} | [Apri]({b['link']}) | {pdf_cell} |")
        lines.append(f"\n*Totale opportunità monitorate: {len(bandi)}*\n")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def export_html_table(bandi, filepath, now_dt, nuovi, in_scadenza):
    """Genera una pagina web HTML moderna, responsive e filtrabile."""
    date_str = now_dt.strftime("%d/%m/%Y")
    time_str = now_dt.strftime("%H:%M")

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bandi UniBo Fisica 3° Anno - {date_str}</title>
<style>
  :root {{
    --unibo-red: #bb2e29;
    --unibo-dark: #8b1d19;
    --bg: #f8f9fa;
    --card-bg: #ffffff;
    --text: #212529;
    --muted: #6c757d;
    --border: #e9ecef;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    margin: 0;
    padding: 24px;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
  }}
  .container {{
    max-width: 1200px;
    margin: 0 auto;
  }}
  header {{
    background: var(--card-bg);
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 20px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    border-left: 6px solid var(--unibo-red);
  }}
  h1 {{
    margin: 0 0 8px 0;
    color: var(--unibo-red);
    font-size: 1.8rem;
  }}
  .subtitle {{
    color: var(--muted);
    margin: 0 0 16px 0;
  }}
  .stats {{
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
  }}
  .stat-badge {{
    background: #f1f3f5;
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 0.9rem;
    font-weight: 600;
  }}
  .stat-badge.highlight {{
    background: #ffe3e3;
    color: var(--unibo-red);
  }}
  .stat-badge.warning {{
    background: #fff3bf;
    color: #d9480f;
  }}
  .search-bar {{
    margin-bottom: 20px;
  }}
  .search-input {{
    width: 100%;
    padding: 12px 16px;
    border-radius: 8px;
    border: 1px solid #ced4da;
    font-size: 1rem;
    box-sizing: border-box;
  }}
  .table-card {{
    background: var(--card-bg);
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    overflow-x: auto;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    text-align: left;
  }}
  th, td {{
    padding: 14px 16px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }}
  th {{
    background: #f1f3f5;
    font-weight: 600;
    color: #495057;
  }}
  tr:hover {{
    background-color: #fdfdfe;
  }}
  .badge {{
    display: inline-block;
    padding: 4px 8px;
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 600;
  }}
  .badge-category {{ background: #e3f2fd; color: #0d47a1; }}
  .badge-urgent {{ background: #ffe3e3; color: #c92a2a; }}
  .badge-warn {{ background: #fff3bf; color: #d9480f; }}
  .badge-ok {{ background: #e8f5e9; color: #2b8a3e; }}
  .badge-open {{ background: #f3f0ff; color: #5f3dc4; }}
  .btn {{
    display: inline-block;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 0.85rem;
    text-decoration: none;
    font-weight: 600;
    margin-right: 6px;
    margin-top: 4px;
  }}
  .btn-primary {{
    background: var(--unibo-red);
    color: white;
  }}
  .btn-secondary {{
    background: #495057;
    color: white;
  }}
  .btn:hover {{
    opacity: 0.9;
  }}
  .sintesi {{
    font-size: 0.88rem;
    color: #495057;
    margin-top: 6px;
    line-height: 1.4;
  }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>🎓 Bandi e Opportunità UniBo — Fisica Triennale (3° Anno)</h1>
    <p class="subtitle">Monitoraggio autonomo per il Corso di Laurea in Fisica (Codice <code>9244</code>) | Ultimo controllo: <strong>{date_str} alle {time_str}</strong></p>
    <div class="stats">
      <span class="stat-badge">📋 Totale bandi attivi: {len(bandi)}</span>
      <span class="stat-badge {'highlight' if nuovi else ''}">✨ Nuovi oggi: {len(nuovi)}</span>
      <span class="stat-badge {'warning' if in_scadenza else ''}">⏰ In scadenza imminente: {len(in_scadenza)}</span>
    </div>
  </header>

  <div class="search-bar">
    <input type="text" id="searchInput" class="search-input" placeholder="🔍 Cerca per bando, categoria, parola chiave (es. STEAM, tutorato, esonero)..." onkeyup="filterTable()">
  </div>

  <div class="table-card">
    <table id="bandiTable">
      <thead>
        <tr>
          <th style="width: 45px;">#</th>
          <th>Bando & Finalità</th>
          <th>Categoria</th>
          <th>Scadenza</th>
          <th style="min-width: 170px;">Azioni</th>
        </tr>
      </thead>
      <tbody>
"""
    for i, b in enumerate(bandi, 1):
        gm = b.get("giorni_mancanti")
        scad_text = b.get("scadenza", "N/D")

        if gm is not None and gm >= 0:
            if gm <= 15:
                badge_class = "badge-urgent"
                sub_scad = f"<br><small style='color: #c92a2a; font-weight: 700;'>🔥 Mancano {gm} giorni!</small>"
            elif gm <= 30:
                badge_class = "badge-warn"
                sub_scad = f"<br><small style='color: #d9480f; font-weight: 600;'>⏰ Mancano {gm} giorni</small>"
            else:
                badge_class = "badge-ok"
                sub_scad = f"<br><small style='color: #2b8a3e;'>Mancano {gm} giorni</small>"
        else:
            badge_class = "badge-open"
            sub_scad = ""

        nuovo_badge = "<span class='badge badge-urgent' style='margin-left: 6px;'>NUOVO</span>" if b.get("is_nuovo") else ""
        pdf_btn = f"<a href='{b['pdf_url']}' target='_blank' class='btn btn-secondary'>📄 Scarica PDF</a>" if b.get("pdf_url") else ""

        html += f"""
        <tr>
          <td><strong>{i}</strong></td>
          <td>
            <strong><a href="{b['link']}" target="_blank" style="color: #bb2e29; text-decoration: none;">{b['titolo']}</a></strong>{nuovo_badge}
            <div class="sintesi">{b.get('riassunto', '')}</div>
          </td>
          <td><span class="badge badge-category">{b['categoria']}</span></td>
          <td>
            <span class="badge {badge_class}">{scad_text}</span>
            {sub_scad}
          </td>
          <td>
            <a href="{b['link']}" target="_blank" class="btn btn-primary">🔗 Scheda</a>
            {pdf_btn}
          </td>
        </tr>
"""

    html += """
      </tbody>
    </table>
  </div>
</div>

<script>
function filterTable() {
  var input = document.getElementById("searchInput");
  var filter = input.value.toLowerCase();
  var table = document.getElementById("bandiTable");
  var tr = table.getElementsByTagName("tr");

  for (var i = 1; i < tr.length; i++) {
    var text = tr[i].textContent || tr[i].innerText;
    if (text.toLowerCase().indexOf(filter) > -1) {
      tr[i].style.display = "";
    } else {
      tr[i].style.display = "none";
    }
  }
}
</script>
</body>
</html>
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)


def costruisci_testo_issue(bandi_attivi, nuovi, in_scadenza, is_first_run, now_dt):
    """Costruisce il titolo e il corpo Markdown dell'Issue GitHub quotidiana."""
    date_str = now_dt.strftime("%d/%m/%Y")
    day_name = GIORNI_SETTIMANA[now_dt.weekday()]

    if nuovi:
        titolo = f"🚨 {len(nuovi)} nuov{'o' if len(nuovi)==1 else 'i'} band{'o' if len(nuovi)==1 else 'i'} — Fisica Triennale ({date_str})"
    elif in_scadenza:
        titolo = f"⏰ Bandi in Scadenza e Attivi — Fisica Triennale ({day_name} {date_str})"
    else:
        titolo = f"🔭 Bandi e Opportunità Attive — Fisica Triennale ({day_name} {date_str})"

    lines = [f"# 🎓 Bandi e Opportunità UniBo — Fisica Triennale ({day_name} {date_str})\n"]

    # 1. NUOVI BANDI
    if nuovi:
        lines.append("> [!IMPORTANT]")
        lines.append(f"> ### 🚨 Rilevat{'o' if len(nuovi)==1 else 'i'} {len(nuovi)} nuov{'o' if len(nuovi)==1 else 'i'} band{'o' if len(nuovi)==1 else 'i'} per Fisica Triennale!\n")
        for i, b in enumerate(nuovi, 1):
            pdf_txt = f" | 📄 [Scarica il PDF del Bando]({b['pdf_url']})" if b.get("pdf_url") else ""
            lines.append(f"### {i}. [{b['titolo']}]({b['link']})")
            lines.append(f"- 🏷️ **Categoria:** {b['categoria']}")
            lines.append(f"- ⏰ **Scadenza:** {b['scadenza']}")
            lines.append(f"- 🎯 **Destinatari:** {b.get('destinatari', 'Non specificati')}")
            lines.append(f"- 📋 **Requisiti:** {b.get('requisiti', 'Specifici da bando')}")
            lines.append(f"\n**ℹ️ Finalità ({b.get('nota_fonte', 'Estratto')}):**\n> {b['riassunto']}\n")
            lines.append(f"🔗 **[Apri Scheda Bando]({b['link']})**{pdf_txt}\n")
        lines.append("")
    elif is_first_run:
        lines.append("> [!NOTE]")
        lines.append(f"> **Inizializzazione completata**: Sono state caricate in archivio **{len(bandi_attivi)} opportunità** per Fisica Triennale (corso `9244`). Da domani ogni nuova pubblicazione verrà notificata con massima priorità.\n")
    else:
        lines.append("> [!TIP]")
        lines.append(f"> ✅ **Nessun nuovo bando oggi**: Tutte le **{len(bandi_attivi)} opportunità attive** per Fisica Triennale sono confermate e monitorate.\n")

    # 2. BANDI IN SCADENZA IMMINENTE
    if in_scadenza:
        lines.append("## ⏰ Bandi in Scadenza nei Prossimi 30 Giorni\n")
        lines.append("| Bando | Scadenza | Mancano | Scheda Web | PDF |")
        lines.append("| :--- | :--- | :---: | :---: | :---: |")
        for b in in_scadenza:
            pdf_c = f"[PDF]({b['pdf_url']})" if b.get("pdf_url") else "-"
            gm = b.get("giorni_mancanti", 0)
            lines.append(f"| **[{b['titolo']}]({b['link']})** | {b['scadenza']} | **{gm} giorni** | [Apri]({b['link']}) | {pdf_c} |")
        lines.append("")

    # 3. TABELLA COMPLETA DI TUTTI I BANDI ATTIVI
    lines.append(f"## 📋 Elenco Completo Opportunità Attive ({len(bandi_attivi)})\n")
    lines.append("| N° | Titolo Bando | Categoria | Scadenza | Scheda | PDF |")
    lines.append("| :---: | :--- | :--- | :--- | :---: | :---: |")
    for i, b in enumerate(bandi_attivi, 1):
        pdf_c = f"[PDF]({b['pdf_url']})" if b.get("pdf_url") else "-"
        scad = b.get("scadenza", "-")
        gm = b.get("giorni_mancanti")
        if gm is not None and 0 <= gm <= 30:
            scad = f"⏰ **{scad}** *(-{gm}g)*"
        lines.append(f"| {i} | [{b['titolo']}]({b['link']}) | `{b['categoria']}` | {scad} | [Apri]({b['link']}) | {pdf_c} |")
    lines.append("")

    # 4. DOWNLOAD E TABELLE
    lines.append("---")
    lines.append("### 📥 Tabelle Scaricabili")
    lines.append("- 📊 Tabella CSV completa per Excel / Google Sheets: [`bandi_attivi.csv`](./bandi_attivi.csv)")
    lines.append("- 🌐 Pagina web interattiva con ricerca rapida: [`bandi_attivi.html`](./bandi_attivi.html)")
    lines.append("- 📄 Elenco in formato Markdown: [`bandi_attivi.md`](./bandi_attivi.md)")
    lines.append("\n*Notifica generata automaticamente dal Bot Bandi UniBo (Fisica).*")

    return titolo, "\n".join(lines)


def invia_issue_github(titolo, corpo, labels=None):
    """Crea o aggiorna la Issue nel repository GitHub usando GITHUB_TOKEN e GITHUB_REPOSITORY."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("ℹ️  GITHUB_TOKEN o GITHUB_REPOSITORY non presenti (esecuzione locale o senza credenziali).")
        return False

    if labels is None:
        labels = ["bando"]

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "BotBandiFisica",
    }

    oggi_str = ora_italiana_ora().strftime("%d/%m/%Y")
    existing_issue_number = None

    # 1. Controlla le issue aperte con label bando: chiudi quelle dei giorni precedenti e trova se ne esiste già una per oggi
    try:
        list_url = f"https://api.github.com/repos/{repo}/issues?labels=bando&state=open&per_page=10"
        r = requests.get(list_url, headers=headers, timeout=12)
        if r.status_code == 200:
            issues = r.json()
            for iss in issues:
                if oggi_str in iss.get("title", ""):
                    existing_issue_number = iss["number"]
                else:
                    # Chiudi la issue del giorno precedente per mantenere pulito il repository
                    close_url = f"https://api.github.com/repos/{repo}/issues/{iss['number']}"
                    try:
                        requests.patch(close_url, headers=headers, json={"state": "closed"}, timeout=10)
                        print(f"ℹ️  Chiusa precedente issue archiviata #{iss['number']}")
                    except Exception:
                        pass
    except Exception as e:
        print(f"⚠️  Impossibile verificare issue esistenti: {e}")

    # 2. Se esiste già una issue per oggi, aggiornala
    if existing_issue_number:
        patch_url = f"https://api.github.com/repos/{repo}/issues/{existing_issue_number}"
        payload = {"title": titolo, "body": corpo}
        try:
            r = requests.patch(patch_url, headers=headers, json=payload, timeout=12)
            if r.status_code == 200:
                print(f"✅ Issue #{existing_issue_number} aggiornata con successo per oggi ({oggi_str}).")
                return True
        except Exception as e:
            print(f"⚠️  Errore aggiornamento Issue #{existing_issue_number}: {e}")

    # 3. Altrimenti crea una nuova Issue
    create_url = f"https://api.github.com/repos/{repo}/issues"
    payload = {
        "title": titolo,
        "body": corpo,
        "labels": labels,
    }

    try:
        r = requests.post(create_url, headers=headers, json=payload, timeout=12)
        if r.status_code == 422:
            # Se fallisce per etichetta non esistente, ritenta senza label
            payload.pop("labels", None)
            r = requests.post(create_url, headers=headers, json=payload, timeout=12)
        r.raise_for_status()
        res_data = r.json()
        print(f"✅ Issue GitHub creata con successo: #{res_data.get('number')} - {titolo}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Errore durante la creazione della Issue GitHub: {e}")
        return False


def invia_telegram(nuovi, bandi_attivi, file_allegati=None):
    """Invia notifiche via Telegram se configurati i relativi secret."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    oggi_str = ora_italiana_ora().strftime("%d/%m/%Y")
    print("  📱 Invio aggiornamenti Telegram...")

    # Se ci sono nuovi bandi, manda un messaggio per ciascun nuovo bando
    if nuovi:
        url_msg = f"https://api.telegram.org/bot{token}/sendMessage"
        for b in nuovi:
            msg = (
                f"🎓 <b>Nuovo Bando UniBo — Fisica Triennale</b> ({oggi_str})\n\n"
                f"📌 <b>{b['titolo']}</b>\n"
                f"⏰ <b>Scadenza:</b> {b['scadenza']}\n"
                f"🏷️ <b>Categoria:</b> {b['categoria']}\n"
                f"🎯 <b>Destinatari:</b> {b.get('destinatari', 'N/D')}\n\n"
                f"ℹ️ <i>{b['riassunto'][:280]}...</i>\n\n"
                f"🔗 <a href=\"{b['link']}\">Apri scheda bando</a>"
            )
            if b.get("pdf_url"):
                msg += f" | <a href=\"{b['pdf_url']}\">Scarica PDF</a>"

            try:
                requests.post(url_msg, json={
                    "chat_id": chat_id,
                    "text": msg,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False
                }, timeout=10)
            except Exception as e:
                print(f"     ⚠️  Errore invio messaggio Telegram: {e}")

    # Invia tabella CSV come documento allegato
    if file_allegati:
        url_doc = f"https://api.telegram.org/bot{token}/sendDocument"
        for f_path in file_allegati:
            if os.path.exists(f_path):
                try:
                    with open(f_path, "rb") as doc_file:
                        caption = f"📊 Tabella bandi e opportunità aggiornata al {oggi_str} ({len(bandi_attivi)} bandi attivi)."
                        requests.post(url_doc, data={"chat_id": chat_id, "caption": caption}, files={"document": doc_file}, timeout=20)
                except Exception as e:
                    print(f"     ⚠️  Errore invio documento Telegram ({f_path}): {e}")


def invia_ntfy(titolo, messaggio):
    """Invia una notifica push via ntfy.sh."""
    ntfy_topic = os.environ.get("NTFY_TOPIC")
    if not ntfy_topic:
        return

    try:
        url = f"https://ntfy.sh/{ntfy_topic}"
        requests.post(url, data=messaggio.encode("utf-8"), headers={
            "Title": titolo,
            "Tags": "mortar_board,telescope",
        }, timeout=10)
        print(f"✅ Notifica push ntfy.sh inviata a topic {ntfy_topic}")
    except Exception as e:
        print(f"⚠️  Errore invio ntfy: {e}")


def aggiorna_step_summary(corpo_markdown):
    """Scrive il riepilogo in GITHUB_STEP_SUMMARY se in esecuzione su GitHub Actions."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return

    try:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write("\n" + corpo_markdown + "\n")
        print("📊 Riepilogo scritto in GITHUB_STEP_SUMMARY.")
    except Exception as e:
        print(f"⚠️  Errore scrittura GITHUB_STEP_SUMMARY: {e}")


def main():
    now_rome = ora_italiana_ora()
    oggi_str = now_rome.strftime("%Y-%m-%d")

    print("=" * 65)
    print("  Avvio Monitoraggio Bandi UniBo — Laurea Triennale in Fisica")
    print(f"  Data ed ora italiana: {now_rome.strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 65)

    session = crea_sessione()
    memoria_link, cache_dettagli = carica_memoria()
    is_first_run = (len(memoria_link) == 0)

    print(f"\n📂 Memoria storica: {len(memoria_link)} link già archiviati.")

    # 1. Ricerca bandi sul portale di Ateneo
    print("\n🔍 1. Interrogazione opportunità per Fisica Triennale (Codice 9244)...")
    candidati_opp = cerca_bandi_opportunita(session)
    print(f"   → Trovate {len(candidati_opp)} schede opportunità.")

    print("🔍 2. Verifica incarichi tutorato didattico (DIFA)...")
    candidati_tut = cerca_bandi_tutorato_difa(session)
    print(f"   → Trovati {len(candidati_tut)} bandi tutorato.")

    tutti_candidati = candidati_opp + candidati_tut

    # Deduplicazione per link
    dedup = {}
    for c in tutti_candidati:
        if c["link"] not in dedup:
            dedup[c["link"]] = c
    candidati_unici = list(dedup.values())
    print(f"   → Totale bandi unici attivi oggi: {len(candidati_unici)}")

    # 2. Arricchimento dettagli e rilevamento novità
    print("\n🧐 3. Arricchimento dettagli (PDF, sintesi, calcolo scadenze)...")
    bandi_attivi, nuovi = arricchisci_bandi(session, candidati_unici, memoria_link, cache_dettagli, oggi_str)

    # Identifica bandi in scadenza nei prossimi 30 giorni
    in_scadenza = [
        b for b in bandi_attivi
        if b.get("giorni_mancanti") is not None and 0 <= b.get("giorni_mancanti") <= 30
    ]

    print(f"   ✨ Nuovi bandi rilevati oggi: {len(nuovi)}")
    print(f"   ⏰ Bandi con scadenza nei prossimi 30 giorni: {len(in_scadenza)}")

    # 3. Generazione tabelle e file esportati
    print("\n📊 4. Generazione tabelle scaricabili...")
    export_csv(bandi_attivi, OUTPUT_CSV)
    export_markdown_table(bandi_attivi, OUTPUT_MD_ATTIVI, f"Bandi e Opportunità Attive - {oggi_str}")
    export_markdown_table(in_scadenza, OUTPUT_MD_SCADENZE, f"Bandi in Scadenza nei Prossimi 30 Giorni - {oggi_str}")
    export_html_table(bandi_attivi, OUTPUT_HTML, now_rome, nuovi, in_scadenza)

    print(f"  - CSV scaricabile: {OUTPUT_CSV}")
    print(f"  - HTML interattivo: {OUTPUT_HTML}")
    print(f"  - Markdown attivi:  {OUTPUT_MD_ATTIVI}")
    print(f"  - Markdown scadenze:{OUTPUT_MD_SCADENZE}")

    # 4. Gestione Issue GitHub e Step Summary
    print("\n📬 5. Creazione o aggiornamento notifica via GitHub Issue...")
    titolo_issue, corpo_issue = costruisci_testo_issue(bandi_attivi, nuovi, in_scadenza, is_first_run, now_rome)
    invia_issue_github(titolo_issue, corpo_issue, labels=["bando"])
    aggiorna_step_summary(corpo_issue)

    # 5. Notifiche push esterne (opzionali)
    invia_telegram(nuovi, bandi_attivi, file_allegati=[OUTPUT_CSV])
    invia_ntfy(titolo_issue, f"UniBo Fisica: {len(bandi_attivi)} bandi attivi, {len(nuovi)} nuovi oggi.")

    # 6. Salvataggio memoria aggiornata
    salva_memoria(memoria_link, cache_dettagli)

    print("\n" + "=" * 65)
    print(f"🏁 Completato con successo. {len(bandi_attivi)} bandi attivi monitorati.")
    print("=" * 65)


if __name__ == "__main__":
    main()
