# 🔭 Bot Bandi UniBo — Laurea Triennale in Fisica (3° Anno)

Sistema autonomo basato su **GitHub Actions** per il monitoraggio quotidiano e la notifica tempestiva di tutte le opportunità, borse di studio, incentivi STEAM, esoneri tasse, bandi per tesi all'estero, collaborazioni (150 ore) e incarichi di tutorato accessibili a uno studente del **3° anno della Laurea Triennale in Fisica (Codice Corso `9244`)** presso l'**Università di Bologna (Alma Mater Studiorum)**.

---

## ⚡ Caratteristiche Principali

- 🤖 **100% Autonomo su GitHub**: Eseguito ogni mattina su GitHub Actions, senza bisogno di server o computer accesi.
- ⏰ **Notifica alle 8:00 (Ora Italiana)**: Schedulato per eseguire il controllo alle **08:00 italiane** (06:00 UTC).
- 🚨 **Rilevamento Nuovi Bandi e Scadenze**: Rileva immediatamente qualsiasi nuova pubblicazione rispetto al giorno precedente e segnala con avvisi prioritari le scadenze imminenti (< 30 giorni).
- 📬 **Notifiche via GitHub Issues (Zero Configurazione)**: Crea o aggiorna l'Issue del giorno con la tabella Markdown formattata, chiudendo in automatico le issue dei giorni passati per mantenere il repository ordinato.
- 📊 **GitHub Actions Step Summary**: Mostra la tabella e il riepilogo direttamente nella schermata dell'esecuzione del workflow.
- 📥 **Tabelle Scaricabili Subito**:
  - `bandi_attivi.csv`: Tabella completa esportata in formato foglio di calcolo (Excel con separatore `;`, Numbers, Google Sheets).
  - `bandi_attivi.html`: Pagina web responsive con casella di ricerca in tempo reale e pulsanti rapidi per aprire la scheda ufficiale e scaricare il PDF.
  - `bandi_attivi.md`: Elenco Markdown di tutte le opportunità attive.
  - `bandi_in_scadenza.md`: Tabella focalizzata sui bandi con scadenza ravvicinata.
- 📦 **GitHub Artifacts**: Le tabelle vengono caricate automaticamente come archivio scaricabile con 1 click al termine di ogni esecuzione del workflow.
- 📲 **Notifiche Telegram & Push (Opzionali)**: Invio opzionale su Telegram con il file `.csv` allegato in chat, oppure via push tramite **ntfy.sh**.

---

## 🎯 Opportunità Monitorate (Corso `9244`)

Il bot interroga il portale ufficiale di Ateneo (`bandi.unibo.it`) combinando:
1. **Filtro Corso di Fisica Triennale**: codice corso `9244` (*Fisica - L - Bologna*).
2. **Livello di corso**: Laurea Triennale (`laurea`).
3. **Target 3° Anno e Laureandi**:
   - **Incentivi STEAM** per studenti iscritti a corsi dell'area scientifica (classe L-30).
   - **Borse per attività di collaborazione a tempo parziale (150 ore)** (dal 2° anno in poi).
   - **Bandi di mobilità internazionale** (Erasmus+, mobilità per preparazione tesi all'estero).
   - **Riduzioni ed esoneri tasse**: per merito, per reddito/ISEE, per disabilità/DSA, per studenti lavoratori.
   - **Riduzione tasse per laureandi in debito di sola prova finale** (specifico per il 3° anno).
   - **Esonero totale per merito per immatricolazione alla Laurea Magistrale** (transizione triennale-magistrale).
   - **Agevolazioni abbonamenti trasporti TPER**, contributi affitto e spese sanitarie fuori sede.
   - **Interventi di emergenza ER.GO**.
4. **Dipartimento di Fisica e Astronomia "Augusto Righi" (DIFA)**:
   - Bandi del dipartimento su `agevolazioni/opportunita`.
   - Bandi per contratti di tutorato didattico e supporto su `didattica/incarichi-tutorato`.

---

## 🚀 Funzionamento 100% Autonomo (Zero Configurazione)

Il bot è **immediatamente operativo** e configurato per funzionare in totale autonomia:

- **Nessun Secret obbligatorio**: Utilizza i permessi automatici `GITHUB_TOKEN` per aprire e aggiornare le Issue e committare le tabelle.
- **Nessun bot Telegram necessario**: Ricevi gli aggiornamenti e gli avvisi direttamente nella scheda **Issues** del repository e via email da GitHub.
- **Aggiornamento quotidiano**: Il workflow si avvia ogni mattina alle **08:00 (ora italiana)**:
  1. Scarica i bandi aggiornati dal portale UniBo per il codice `9244`.
  2. Legge e memorizza i dettagli e i PDF ufficiali di ciascun bando.
  3. Evidenzia eventuali nuovi bandi pubblicati o scadenze ravvicinate.
  4. Crea o aggiorna l'**Issue del giorno** e archivia le precedenti.
  5. Salva lo storico e genera le tabelle CSV, HTML e Markdown nel repository.

---

## 🧪 Esecuzione Manuale (Opzionale)

Se vuoi forzare un controllo immediato a qualsiasi ora:
1. Vai nella scheda **Actions** del repository: [Actions](https://github.com/Martiri/bot-bandi-fisica/actions).
2. Seleziona **Controllo Bandi Fisica UniBo**.
3. Clicca su **Run workflow** > pulsante verde.
4. In meno di un minuto la Issue e le tabelle saranno aggiornate!

---

## 📲 Notifiche Esterne (Facoltative)

### Telegram
Se desideri ricevere gli avvisi anche su Telegram:
1. Crea un bot con `@BotFather` e ottieni il Token.
2. Ricava il tuo ID con `@userinfobot`.
3. Aggiungi i secret `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` in **Settings** > **Secrets and variables** > **Actions**.
*(Invierà anche il file `bandi_attivi.csv` direttamente in chat!)*

### Notifiche Push (ntfy.sh)
Se preferisci notifiche push su smartphone senza Telegram:
1. Scarica l'app **ntfy** (Android / iOS).
2. Iscriviti a un topic a tua scelta (es. `bandi_fisica_unibo_franco`).
3. Nei Secret di GitHub imposta `NTFY_TOPIC = bandi_fisica_unibo_franco`.

---

## 📁 Struttura del Progetto

```text
├── .github/
│   └── workflows/
│       └── bandi_fisica.yml       # Workflow schedulato alle 8:00 su GitHub Actions
├── data/
│   └── bandi_memoria.json         # Cache arricchita con sintesi, PDF e date scadenze
├── bandi.py                       # Script principale Python per scraping e notifica
├── bandi_attivi.csv               # Tabella completa esportata in CSV (Excel)
├── bandi_attivi.html              # Pagina web responsive con ricerca rapida
├── bandi_attivi.md                # Tabella Markdown di tutti i bandi attivi
├── bandi_in_scadenza.md           # Tabella Markdown dei bandi con scadenza vicina
├── bandi_trovati.json             # Memoria storica dei link per retrocompatibilità
└── requirements.txt               # Dipendenze Python (requests, beautifulsoup4, pypdf)
```