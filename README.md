# 🔭 Bot Bandi UniBo — Laurea Triennale in Fisica (3° Anno)

Bot automatico per il monitoraggio e la notifica tempestiva di tutte le opportunità, borse di studio, premi, esoneri tasse, bandi per tesi all'estero, collaborazioni (150 ore) e incarichi di tutorato accessibili a uno studente del **3° anno della Laurea Triennale in Fisica** presso l'**Università di Bologna (Alma Mater Studiorum)**.

---

## 🎯 Opportunità Monitorate

Il bot interroga il portale ufficiale di Ateneo (`bandi.unibo.it`) combinando:
1. **Filtro Corsi di Fisica Triennale**: codice corso `6639, 9244, 8007` (*Fisica - L - Bologna*).
2. **Livello di corso**: Laurea Triennale (`laurea`).
3. **Target 3° Anno e Laureandi**:
   - **Incentivi STEAM** per studenti iscritti a corsi dell'area scientifica (classe L-30).
   - **Borse per attività di collaborazione a tempo parziale (150 ore)** (aperte dal 2° anno in poi).
   - **Bandi di mobilità internazionale** (Erasmus+, mobilità per preparazione tesi all'estero).
   - **Riduzioni ed esoneri tasse**: per merito, per reddito/ISEE, per disabilità/DSA, per studenti lavoratori.
   - **Riduzione tasse per laureandi in debito di sola prova finale** (fondamentale per il 3° anno).
   - **Esonero totale per merito per immatricolazione alla Laurea Magistrale** (transizione dal 3° anno alla magistrale).
   - **Agevolazioni abbonamenti trasporti TPER**, contributi affitto e spese sanitarie fuori sede.
   - **Interventi di emergenza ER.GO**.
4. **Dipartimento di Fisica e Astronomia "Augusto Righi" (DIFA)**:
   - Bandi del dipartimento su `agevolazioni/opportunita`.
   - Bandi per contratti di tutorato didattico e supporto su `didattica/incarichi-tutorato`.

---

## 📬 Canali di Notifica

1. **GitHub Issues**: Crea un'Issue nel repository con il riepilogo Markdown formattato per ciascun nuovo bando trovato (titolo, scadenza, destinatari, requisiti, finalità estratta dal PDF e link diretti).
2. **GitHub Actions Step Summary**: Mostra una tabella visiva immediata nel tab Actions di ogni esecuzione.
3. **Telegram (Opzionale)**: Invia una notifica istantanea sullo smartphone tramite Bot Telegram se sono valorizzate le variabili d'ambiente `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
4. **Terminale / Console**: Output leggibile ed esaustivo in caso di esecuzione manuale in locale.

---

## ⚙️ Configurazione GitHub Actions

Nel file [`.github/workflows/orario.yml`](.github/workflows/orario.yml), lo script è schedulato ogni mattina alle 08:00 UTC (10:00 ora italiana):
- `GITHUB_TOKEN`: Già fornito automaticamente da GitHub con permessi `issues: write` e `contents: write`.
- (Opzionale) **Secrets del Repository** per Telegram:
  - `TELEGRAM_BOT_TOKEN`: Token del bot generato tramite BotFather.
  - `TELEGRAM_CHAT_ID`: ID della chat o del canale Telegram su cui ricevere gli avvisi.

---

## 🚀 Esecuzione in Locale

```bash
# 1. Crea l'ambiente virtuale e installa le dipendenze
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Avvia il controllo
python bandi.py
```