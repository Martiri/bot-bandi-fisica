# 🔭 Bot Bandi UniBo — Laurea Triennale in Fisica (3° Anno)

Repository unificato per il monitoraggio automatico di tutte le opportunità, borse di studio, incentivi STEAM, esoneri tasse, collaborazioni (150 ore) e incarichi di tutorato accessibili a uno studente del **3° anno della Laurea Triennale in Fisica (Codice Corso `9244`)** presso l'**Università di Bologna (Alma Mater Studiorum)**.

> [!NOTE]
> Questo repository unifica e sostituisce `bot-bandi-unibo` e `bandi_tutorato`, integrando le regole di `bot-bandi-fisica` con il monitoraggio delle collaborazioni 150 ore e dei contratti di tutorato d'Ateneo.

---

## ⚡ Caratteristiche Principali

- 🤖 **100% Autonomo su GitHub**: Eseguito ogni mattina su GitHub Actions alle **07:35 (ora italiana)**.
- 📱 **Notifiche solo su Telegram**: Zero Issue create, **nessuna email di spam** nella tua casella di posta.
- 🚨 **Rilevamento Intelligente**: Notifica solo quando ci sono novità:
  - 🆕 **Nuovi bandi aperti** per candidature.
  - 🔥 **Bandi in scadenza** nei prossimi 7 giorni.
  - 📢 **Nuovi bandi in arrivo** annunciati dall'Ateneo.
  - 🏁 **Bandi chiusi o conclusi**.
- 💶 **Regole di Esclusione e Filtri Personalizzati**:
  - ❌ **Esclusi bandi per disabilità**: rimossi tutti gli avvisi ed esoneri legati a disabilità, DSA o inabilità.
  - ❌ **Esclusi bandi con ISEE restrittivo (≤ 40k)**: scartati i sussidi ER.GO, l'esonero per genitori e la riduzione per laureandi a basso reddito.
  - ⚠️ **Eccezione esplicita per situazione economica**: mantenuto il bando *Esoneri e riduzioni per situazione economica generale* per monitorare le scadenze della contribuzione studentesca e della dichiarazione ISEE.
  - ✅ **Bandi monitorati**: incentivi STEAM per merito, borse 150 ore d'Ateneo, incarichi di tutorato didattico (DIFA), tutorato alla pari, esonero magistrale per voto di laurea, riduzione per più familiari universitari.
  - `bandi_attivi.csv`: Tabella completa esportata in foglio di calcolo (Excel, Numbers, Google Sheets).
  - `bandi_attivi.html`: Pagina web responsive con ricerca in tempo reale.
  - `bandi_attivi.md` e `bandi_in_scadenza.md`: Elenchi formattati in Markdown.

---

## 🎯 Opportunità Monitorate

1. **Corso di Laurea in Fisica (`9244`)**:
   - Incentivi STEAM per l'area scientifica (L-30).
   - Esoneri e riduzioni tasse universitarie (merito, reddito/ISEE, DSA, studenti lavoratori, genitori).
   - Riduzione per laureandi in debito della sola prova finale.
   - Esonero totale per merito per immatricolazione alla Laurea Magistrale.
   - Bandi per preparazione tesi all'estero e mobilità.
   - Agevolazioni abbonamenti trasporti TPER, contributi affitto e sussidi ER.GO.
2. **Dipartimento di Fisica e Astronomia "Augusto Righi" (DIFA)**:
   - Bandi del dipartimento su `agevolazioni/opportunita`.
   - Incarichi di tutorato didattico su `didattica/incarichi-tutorato`.
3. **Ateneo (Bologna) — Collaborazioni e Tutorato**:
   - Borse per attività di collaborazione a tempo parziale (150 ore) presso biblioteche e strutture universitarie del Campus di Bologna.
   - Assegni di tutorato alla pari aperti a studenti della triennale.

---

## ⚙️ Configurazione Telegram

I secret necessari in **Settings** > **Secrets and variables** > **Actions**:
- `TELEGRAM_BOT_TOKEN`: Token del bot Telegram (`@BotFather`).
- `TELEGRAM_CHAT_ID`: ID numerico della chat Telegram (`@userinfobot`).

---

## 📁 Struttura del Progetto

```text
├── .github/
│   └── workflows/
│       └── bandi_fisica.yml       # Workflow programmato alle 07:35 italiane
├── data/
│   ├── bandi_memoria.json         # Cache arricchita con sintesi, PDF e scadenze
│   └── ultimo_invio.json          # Tracciamento orario dell'ultima notifica
├── bandi.py                       # Script principale per scraping e notifica Telegram
├── requirements.txt               # Dipendenze Python (requests, beautifulsoup4, pypdf)
├── bandi_trovati.json             # Memoria storica dei link per retrocompatibilità
├── bandi_attivi.csv               # Tabella completa esportata in CSV (Excel)
├── bandi_attivi.html              # Pagina web responsive con ricerca rapida
├── bandi_attivi.md                # Tabella Markdown di tutti i bandi attivi
└── bandi_in_scadenza.md           # Tabella Markdown dei bandi con scadenza vicina
```