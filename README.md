<p align="center">
  <img src="frontend/imgs/logo.png" alt="URZ logo" height="80" />
  <img src="frontend/imgs/chatbot_logo.png" alt="Chatbot logo" height="80" />
</p>

# RAG Script for the URZ Chat Bot

This repository contains a Retrieval-Augmented Generation (RAG) script designed for the University of Heidelberg's URZ Chat Bot. The application allows for crawling content from URZ-related websites and PDFs, embedding the text, and querying it using the `gpt-oss-20b` model served through an [Ollama](https://ollama.com) API.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [File Structure](#file-structure)
- [Endpoints](#endpoints)
- [Acknowledgments](#acknowledgments)

## Features

- Crawls websites and PDFs for content extraction.
- Embeds content using HuggingFace embeddings.
- Utilizes FAISS for fast similarity search.
- Uses the `gpt-oss:20b` model via Ollama for natural language querying.
- Supports RAG-based document retrieval.
- Web interface built using Flask and a React frontend.
- Retrieval is tuned to return results from different URLs so the model can cite specific subpages.
- Search results are re-ranked with a cross-encoder to surface the most relevant pages.
- Lexical token matching expands the candidate set before re-ranking.
- The UI streams tokens from the backend so responses appear progressively.
- A sidebar can display the model's intermediate "thinking" when the model returns reasoning wrapped in `<think>` tags.

**New / Improved:**

- **Multilingual retrieval (DE/EN):**  
  Uses `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` so German and English queries rank pages consistently.

- **Multilingual cross-encoder re-ranking:**  
  Uses `BAAI/bge-reranker-v2-m3` to re-rank candidate passages across languages.

- **Pronoun-aware follow-ups:**  
  Follow-up questions like “How can I get **it**?” work reliably. The vector query adds compact topic hints from recent **user-only** turns when the current query is pronoun-like.

- **Topic-switch reset:**  
  If the new question is off-topic (low token overlap with the last user question in the same language), the system temporarily **drops history** to avoid dragging unrelated context.

- **Same-language, user-only history:**  
  Retrieval only considers **user** messages in the **same language** as the current turn, improving accuracy when switching German/English.

- **Stable citation footer (guarded):**  
  “Sources/Quellen” is appended only if retrieved context is **meaningfully** relevant (relative score gate / token fallback), reducing spurious citations.

- **RAG debugging tools:**  
  Set `HEIBOT_DEBUG=1` to log detailed per-turn traces (`rag_debug.log`) including vector & reranker queries, candidate URLs with scores, context preview, and citations.  
  Set `HEIBOT_DEBUG_TO_CHAT=1` to also embed a collapsible debug block in the chat (dev-only).


## Requirements

Python 3.9 (for Ubuntu 22.04.).
The Python packages which are required are specified in `requirements.txt`.
Note that `BeautifulSoupWebReader` requires at least `llama-index` version 0.10.32 for the `exclude_selectors` option.

Node.js and npm are required for the React frontend (tested with Node 20).

If you run the application outside of Docker you also need a running [Ollama](https://ollama.com) server hosting the `gpt-oss-20b` model and accessible at `http://localhost:11434`.

Additionally, `tesseract-ocr` needs to be installed on your machine for OCR processing of PDFs:

```bash
# On Ubuntu
sudo apt-get install tesseract-ocr

# On macOS (with Homebrew)
brew install tesseract
```

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/your-repository-url.git
   cd your-repository-folder
   ```

2. Create a virtual environment and activate it:

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. Install the required Python packages (requires `llama-index` version 0.10.32 or later):

   ```bash
   pip install -r requirements.txt
   ```

4. Install the frontend dependencies and build the React app:

   ```bash
   cd frontend
   npm install
   npm run build
   cd ..
   ```

5. Install `tesseract-ocr` for PDF OCR support (see instructions in the [Requirements](#requirements) section).

6. Ensure an Ollama server is running with the Deepseek model (see [Running Deepseek with Ollama](#running-deepseek-with-ollama)).

## Usage

1. Ensure the React frontend is built (`npm run build` as shown above) and start the Flask web server:

   ```bash
   python app.py
   ```

2. Open your web browser and navigate to the port specified in app.py:

   ```
   http://localhost:7000
   ```

   You can now use the URZ Chat Bot to ask questions based on the crawled and indexed documents.


### Debugging (Optional)
   ```bash
   # Linux/macOS (temporary for this shell)
   HEIBOT_DEBUG=1 python app.py

   # Include debug info inside the chat (dev-only)
   HEIBOT_DEBUG=1 HEIBOT_DEBUG_TO_CHAT=1 python app.py
   ```
- Logs are written to rag_debug.log.

- The debug blob includes: same-language user history, vector & reranker queries, top candidate URLs with scores/snippets, context length & preview, final LLM prompt preview, and citations.

### Running GPT-OSS 20B with Ollama

Install [Ollama](https://ollama.com):

```bash
# stop old daemon (optional but tidy)
sudo systemctl stop ollama 2>/dev/null || true

# upgrade Ollama (same command as install)
curl -fsSL https://ollama.com/install.sh | sh

# start it
sudo systemctl enable --now ollama
ollama --version  # expect 0.4.x or 0.5.x
```

Pull and test the model:

```bash
ollama pull gpt-oss:20b
ollama run gpt-oss:20b "Say hello"
ollama list
````

```bash
ollama pull gpt-oss-20b
```

Ollama serves models on `http://localhost:11434` by default. Running `ollama run gpt-oss-20b` will start the server if it is not already running.


### Crawling and Indexing

The script crawls the following base URLs:

- `https://www.urz.uni-heidelberg.de`
- `https://www.urz.uni-heidelberg.de/de/support/anleitungen`
- `https://www.urz.uni-heidelberg.de/de/service-katalog/services-a-z`

Content from these websites and any linked PDFs will be crawled, extracted, and embedded for querying.
A total of 610 HTML Pages and two PDFs are retrieved.

## Configuration

The following parameters can be tuned in `chatbot/engine.py` and `chatbot/server.py`:

- `PERSIST_DIR` – directory used to persist the FAISS index (`index_store`).
- `Settings.llm` – model name served by Ollama (`gpt-oss-20b`).
- `Settings.embed_model` – embedding model (`sentence-transformers/all-mpnet-base-v2`).
- `rerank_model` – cross encoder used for re-ranking (`ms-marco-MiniLM-L-6-v2`).
- `ConversationManager.max_history` – number of messages kept per session (default `5`).
- `PERMANENT_SESSION_LIFETIME` – session timeout configured in `server.py`.

## File Structure

```
├── app.py               # Run script starting the Flask server
├── chatbot/             # Python package with application code
│   ├── engine.py        # Retrieval and indexing logic
│   ├── server.py        # Flask app factory and routes
│   └── utils.py         # Helper utilities
├── frontend/            # React frontend source
├── web_html.py          # Legacy HTML template
├── requirements.txt     # Python dependencies
└── README.md            # This documentation
```

## Endpoints

- `/`: Serves the React application.
- `/chat`: POST endpoint for querying the chat bot with streamed responses.

## Acknowledgments

- The project uses the `gpt-oss-20b` model served via Ollama for language modeling.
- HuggingFace's sentence-transformers for embedding text.
- FAISS for efficient similarity search.
- pdfplumber and pytesseract for handling PDFs with OCR.

### 2024 by Marcus Buchwald & Holger Altenbach
