import os
import io
import re
import json
import time
from datetime import date
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

# Supporta sia pypdf (moderno) sia PyPDF2 (legacy)
try:
    import pypdf as pdf_lib
except ImportError:
    try:
        import PyPDF2 as pdf_lib
    except ImportError:
        pdf_lib = None

# Percorso file di memoria relativo allo script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_MEMORIA = os.path.join(SCRIPT_DIR, "bandi_trovati.json")

# URL portale bandi UniBo
BASE_URL = "https://bandi.unibo.it"
URL_OPPORTUNITA = f"{BASE_URL}/agevolazioni/opportunita"
URL_TUTORATO = f"{BASE_URL}/didattica/incarichi-tutorato"

# Configurazione target: Studente 3° anno Laurea Triennale in Fisica (Bologna)
# Codice corso per "Fisica - L - Bologna": 9244
CODICI_CORSO_FISICA = "9244"
TIPO_CORSO_LAUREA = "laurea"
STRUTTURA_DIFA = "difa"  # Dipartimento di Fisica e Astronomia "Augusto Righi"

# Lunghezza massima riassunto
MAX_RIASSUNTO_LEN = 450

# Se impostato su 'true', crea una issue anche quando non ci sono nuovi bandi.
# Default: False (per non intasare il repository con notifiche quotidiane vuote).
NOTIFICA_SE_NESSUN_BANDO = os.environ.get("NOTIFICA_SE_NESSUN_BANDO", "false").lower() in ("true", "1", "yes")


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


def carica_memoria():
    """Carica i link dei bandi già notificati.
    Supporta sia liste di stringhe (retrocompatibilità) sia set."""
    if os.path.exists(FILE_MEMORIA):
        try:
            with open(FILE_MEMORIA, "r", encoding="utf-8") as f:
                dati = json.load(f)
                memoria = set()
                for el in dati:
                    if isinstance(el, str):
                        memoria.add(el.strip())
                    elif isinstance(el, dict) and "link" in el:
                        memoria.add(el["link"].strip())
                return memoria
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️  Errore lettura memoria ({e}), inizializzo vuota.")
            return set()
    return set()


def salva_memoria(memoria):
    """Salva i link in formato JSON ordinato."""
    try:
        with open(FILE_MEMORIA, "w", encoding="utf-8") as f:
            json.dump(sorted(list(memoria)), f, ensure_ascii=False, indent=2)
        print(f"💾 Memoria aggiornata: {len(memoria)} bandi registrati in {os.path.basename(FILE_MEMORIA)}")
    except OSError as e:
        print(f"❌ Errore salvataggio memoria: {e}")


def pulisci_spazi(testo):
    return " ".join(testo.split()) if testo else ""


def trova_pdf_nel_bando(session, url_bando):
    """Esamina la pagina di dettaglio del bando per trovare il link al PDF."""
    try:
        r = session.get(url_bando, timeout=10)
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
    """Scarica (in streaming, max 4MB) ed estrae in modo mirato
    l'oggetto o la finalità (Art. 1) dal PDF del bando."""
    if not pdf_lib:
        return "Modulo PDF non disponibile (pypdf/PyPDF2 non installato)."

    try:
        r = session.get(url_pdf, stream=True, timeout=12)
        r.raise_for_status()
        raw = bytearray()
        for chunk in r.iter_content(chunk_size=65536):
            raw.extend(chunk)
            if len(raw) > 4 * 1024 * 1024:  # Max 4 MB
                break

        reader = pdf_lib.PdfReader(io.BytesIO(raw))
        testo = ""
        # Esamina solo le prime 3 pagine (dove risiedono oggetto e finalità)
        for pagina in reader.pages[:3]:
            estratto = pagina.extract_text()
            if estratto:
                testo += estratto + "\n"

        if not testo.strip():
            return "Testo del PDF non estratto (possibile scansione immagine)."

        # 1. Cerca Art. 1 / Articolo 1 (Oggetto o Finalità del bando)
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

        # 2. Cerca blocco 'Oggetto' o 'Finalità'
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

        # 3. Fallback: pulisce le righe di intestazione burocratica comune
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
    # Titolo
    h3 = card.find("h3")
    titolo = pulisci_spazi(h3.get_text()) if h3 else "Senza titolo"

    # Link al bando
    a_tag = card.find("a", href=True)
    if not a_tag:
        return None
    link = urljoin(BASE_URL, a_tag["href"].strip())

    # Scadenza / Periodo
    scadenza_el = card.find(class_="details-icon")
    scadenza = pulisci_spazi(scadenza_el.get_text()) if scadenza_el else "Non specificata"

    # Dettagli (Mi interessa se, Tipo di corso, Tipologia, Requisiti)
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
    """Verifica se il bando è accessibile a uno studente del 3° anno di Fisica Triennale.
    Un bando è idoneo se:
    - Include corsi di tipo 'Laurea' (triennale) tra i destinatari.
    - NON è riservato esclusivamente alle sole matricole (primo anno), a meno che non
      riguardi laureandi / debito di sola prova finale.
    - Include bandi per iscritti dal 2° anno in poi, laureandi, borse STEAM, tutorato e agevolazioni generali.
    """
    tipo_corso_low = info_bando["tipo_corso"].lower()
    destinatari_low = info_bando["destinatari"].lower()
    titolo_low = info_bando["titolo"].lower()

    # Se ci sono informazioni sul tipo di corso, deve comprendere "laurea" di 1° ciclo
    if tipo_corso_low:
        # Se menziona solo "laurea magistrale" e NON "laurea" semplice
        ha_laurea_triennale = ("laurea" in tipo_corso_low.replace("laurea magistrale", ""))
        ha_laurea_semplice = any(
            token.strip() == "laurea" for token in tipo_corso_low.split(",")
        )
        if not (ha_laurea_triennale or ha_laurea_semplice):
            # Eccezione: esoneri o borse per prosecuzione su magistrale per chi si sta laureando al 3° anno
            if not any(k in titolo_low for k in ["laurea magistrale", "prosecuzione", "laureand"]):
                return False

    # Se destinatari è specificato:
    if destinatari_low:
        # Esclude bandi che sono SOLO per matricole (studio al primo anno) e NON per secondo anno in poi
        solo_primo_anno = ("studio al primo anno" in destinatari_low) and ("secondo anno" not in destinatari_low) and ("laurea" not in destinatari_low)
        if solo_primo_anno and not any(k in titolo_low for k in ["laureand", "prova finale", "terzo anno"]):
            return False

    return True


def cerca_bandi_opportunita(session):
    """Interroga la sezione agevolazioni/opportunita per studenti di Fisica Triennale."""
    bandi = []
    
    # 1. Query con codice corso Fisica (9244) e tipo corso Laurea
    # NOTA: le virgole NON devono essere codificate come %2C nella stringa
    params_fisica = {
        "corsi": CODICI_CORSO_FISICA,
        "tipocorso": TIPO_CORSO_LAUREA,
    }
    try:
        r = session.get(URL_OPPORTUNITA, params=params_fisica, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Esamina ciascun accordion (Bandi aperti, Riduzioni ed esoneri, Prossimi bandi in uscita)
        for acc in soup.find_all(class_="accordion-content"):
            btn = acc.find_previous("button")
            nome_categoria = btn.get_text(strip=True) if btn else "Bandi e Agevolazioni"
            
            for card in acc.find_all(class_="manifesto-card"):
                info = estrai_dettagli_card(card, nome_categoria)
                if info and e_accessibile_terzo_anno_fisica(info):
                    bandi.append(info)
    except Exception as e:
        print(f"❌ Errore interrogazione portale opportunità: {e}")

    # 2. Query complementare su dipartimento DIFA (Dipartimento di Fisica e Astronomia)
    try:
        r_difa = session.get(URL_OPPORTUNITA, params={"struttura": STRUTTURA_DIFA}, timeout=15)
        r_difa.raise_for_status()
        soup_difa = BeautifulSoup(r_difa.text, "html.parser")
        for card in soup_difa.find_all(class_="manifesto-card"):
            info = estrai_dettagli_card(card, "Bandi DIFA / Dipartimento")
            if info and e_accessibile_terzo_anno_fisica(info):
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


def analizza_bandi_nuovi(session, candidati, memoria):
    """Filtra i bandi già presenti in memoria e arricchisce i nuovi
    con il link al PDF e la sintesi della finalità."""
    nuovi_trovati = []
    visti_in_questo_giro = set()

    for b in candidati:
        link = b["link"]
        if link in memoria or link in visti_in_questo_giro:
            continue

        visti_in_questo_giro.add(link)
        print(f"  ✨ Nuovo bando rilevato: {b['titolo']}")
        print(f"     Scadenza: {b['scadenza']} | Categoria: {b['categoria']}")

        # Cerca PDF e sintesi
        pdf_url = trova_pdf_nel_bando(session, link)
        sintesi = ""
        if pdf_url:
            print(f"     📄 Lettura PDF: {pdf_url}")
            sintesi = estrai_sintesi_pdf(session, pdf_url)
            nota_fonte = "Riassunto estratto direttamente dal PDF del bando"
        else:
            # Estrae la descrizione dalla pagina HTML del bando
            try:
                r = session.get(link, timeout=10)
                soup = BeautifulSoup(r.text, "html.parser")
                content = soup.find("div", id="content-core") or soup.find("main")
                testo_pagina = pulisci_spazi(content.get_text()) if content else ""
                sintesi = (testo_pagina[:MAX_RIASSUNTO_LEN] + "…") if len(testo_pagina) > MAX_RIASSUNTO_LEN else testo_pagina
                nota_fonte = "Descrizione tratta dalla scheda informativa del bando"
            except Exception:
                sintesi = "Consulta la pagina ufficiale del bando per tutti i requisiti e le modalità."
                nota_fonte = "Scheda informativa web"

        if not sintesi:
            sintesi = "Nessuna descrizione o finalità specificata nel bando."

        b_completo = dict(b)
        b_completo["pdf_url"] = pdf_url
        b_completo["riassunto"] = sintesi
        b_completo["nota_fonte"] = nota_fonte

        nuovi_trovati.append(b_completo)
        memoria.add(link)

    return nuovi_trovati


def costruisci_testo_issue(nuovi, oggi):
    """Costruisce il titolo e il corpo Markdown dell'Issue GitHub."""
    if not nuovi:
        titolo = f"📭 Nessun nuovo bando — Fisica Triennale ({oggi})"
        corpo = (
            f"Il controllo automatico di oggi (**{oggi}**) non ha rilevato nuovi bandi "
            f"rispetto a quelli già registrati in memoria.\n\n"
            f"Il monitoraggio per la Laurea Triennale in Fisica (3° anno) rimane attivo."
        )
        return titolo, corpo

    titolo = f"🎓 {len(nuovi)} nuov{'o' if len(nuovi)==1 else 'i'} band{'o' if len(nuovi)==1 else 'i'} — Fisica Triennale ({oggi})"
    
    blocchi = []
    for i, b in enumerate(nuovi, 1):
        dettagli_elenco = [
            f"- 🏷️ **Categoria:** {b['categoria']}",
            f"- ⏰ **Scadenza / Periodo:** {b['scadenza']}",
            f"- 🎯 **Destinatari:** {b.get('destinatari', 'Tutti gli aventi diritto')}",
            f"- 📋 **Requisiti indicati:** {b.get('requisiti', 'Specifici da bando')}",
        ]
        if b.get("tipo_corso"):
            dettagli_elenco.append(f"- 🎓 **Livello corso:** {b['tipo_corso']}")

        link_pdf = f" | 📄 [Scarica il PDF del Bando]({b['pdf_url']})" if b.get("pdf_url") else ""
        
        blocco = (
            f"### {i}. [{b['titolo']}]({b['link']})\n\n"
            + "\n".join(dettagli_elenco) + "\n\n"
            f"**ℹ️ Finalità e oggetto ({b.get('nota_fonte', 'Estratto')}):**\n"
            f"> {b['riassunto']}\n\n"
            f"🔗 **[Visualizza scheda ufficiale del bando]({b['link']})**{link_pdf}"
        )
        blocchi.append(blocco)

    corpo = (
        f"## 🔭 Nuovi bandi rilevati per il 3° anno di Fisica Triennale ({oggi})\n\n"
        f"Sono stati trovati **{len(nuovi)}** nuovi bandi accessibili:\n\n"
        + "\n\n---\n\n".join(blocchi)
        + "\n\n---\n*Notifica generata automaticamente dal Bot Bandi UniBo.*"
    )
    return titolo, corpo


def invia_issue_github(titolo_issue, corpo_messaggio):
    """Crea una issue nel repository GitHub se token e repo sono disponibili."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("ℹ️  GITHUB_TOKEN o GITHUB_REPOSITORY non presenti (esecuzione locale o senza credenziali).")
        return False

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {
        "title": titolo_issue,
        "body": corpo_messaggio,
        "labels": ["bando"],
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=12)
        if r.status_code == 422:
            # Può accadere se la label 'bando' non esiste: ritenta senza label
            payload.pop("labels", None)
            r = requests.post(url, headers=headers, json=payload, timeout=12)
        r.raise_for_status()
        print(f"  ✅ Issue GitHub creata con successo: {titolo_issue}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Errore durante la creazione della Issue GitHub: {e}")
        return False


def invia_telegram(nuovi):
    """Invia le notifiche su Telegram se configurati TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    oggi = date.today().strftime("%d/%m/%Y")

    print("  📱 Invio notifiche Telegram...")
    for b in nuovi:
        msg = (
            f"🎓 <b>Nuovo Bando UniBo — Fisica Triennale</b> ({oggi})\n\n"
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
            r = requests.post(url, json={
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }, timeout=10)
            r.raise_for_status()
            print(f"     ✅ Notifica inviata: {b['titolo'][:40]}…")
        except Exception as e:
            print(f"     ⚠️  Errore invio Telegram: {e}")


def aggiorna_step_summary(nuovi, totale_attivi):
    """Scrive un riepilogo visivo in GITHUB_STEP_SUMMARY per GitHub Actions."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return

    oggi = date.today().strftime("%d/%m/%Y")
    righe = [
        f"## 🔭 Monitoraggio Bandi UniBo — Fisica Triennale 3° Anno ({oggi})\n",
        f"- **Nuovi bandi trovati oggi:** {len(nuovi)}",
        f"- **Totale bandi noti archiviati:** {totale_attivi}\n",
    ]

    if nuovi:
        righe.append("| Titolo Bando | Scadenza | Categoria | Link | PDF |")
        righe.append("|---|---|---|---|---|")
        for b in nuovi:
            pdf_md = f"[PDF]({b['pdf_url']})" if b.get("pdf_url") else "-"
            righe.append(f"| {b['titolo']} | {b['scadenza']} | {b['categoria']} | [Scheda]({b['link']}) | {pdf_md} |")
    else:
        righe.append("Nessun nuovo bando trovato rispetto al controllo precedente.")

    try:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write("\n".join(righe) + "\n")
    except Exception as e:
        print(f"  ⚠️  Errore scrittura GITHUB_STEP_SUMMARY: {e}")


def main():
    print("=" * 65)
    print("  Avvio Monitoraggio Bandi UniBo — Laurea Triennale in Fisica")
    print("=" * 65)

    memoria = carica_memoria()
    lunghezza_iniziale = len(memoria)
    print(f"📂 Bandi già registrati in memoria: {lunghezza_iniziale}")

    session = crea_sessione()

    print("\n🔍 1. Ricerca opportunità (Borse, Agevolazioni, Esoneri, Mobilità, STEAM)...")
    candidati_opp = cerca_bandi_opportunita(session)
    print(f"   → Trovate {len(candidati_opp)} schede pertinenti per Fisica Triennale.")

    print("🔍 2. Verifica incarichi didattici e tutorato per Fisica (DIFA)...")
    candidati_tut = cerca_bandi_tutorato_difa(session)
    print(f"   → Trovati {len(candidati_tut)} bandi tutorato.")

    tutti_candidati = candidati_opp + candidati_tut

    print("\n🧐 3. Controllo novità ed estrazione approfondita...")
    nuovi = analizza_bandi_nuovi(session, tutti_candidati, memoria)

    oggi = date.today().strftime("%d/%m/%Y")

    print("\n📬 4. Gestione notifiche...")
    if nuovi:
        print(f"   🎯 Trovati {len(nuovi)} NUOVI bandi!")
        titolo_issue, corpo_issue = costruisci_testo_issue(nuovi, oggi)
        invia_issue_github(titolo_issue, corpo_issue)
        invia_telegram(nuovi)
    else:
        print("   💤 Nessun nuovo bando rispetto al controllo precedente.")
        if NOTIFICA_SE_NESSUN_BANDO:
            titolo_issue, corpo_issue = costruisci_testo_issue([], oggi)
            invia_issue_github(titolo_issue, corpo_issue)

    # Scrive riepilogo in GitHub Step Summary se eseguito in GitHub Actions
    aggiorna_step_summary(nuovi, len(memoria))

    # Salva la memoria aggiornata
    if len(memoria) > lunghezza_iniziale:
        salva_memoria(memoria)

    print("\n" + "=" * 65)
    if nuovi:
        print(f"🏁 Completato. Notificati {len(nuovi)} nuovi bandi per Fisica Triennale.")
    else:
        print("🏁 Completato. Nessun nuovo bando da notificare.")
    print("=" * 65)


if __name__ == "__main__":
    main()
