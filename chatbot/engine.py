import os
import glob
import pickle
import logging
import asyncio
import re
import time
from datetime import datetime
from typing import List, Optional, Union, Dict
from urllib.parse import urlparse, urlunparse
import json
import threading

import aiohttp
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

from llama_index.core import (
    Settings,
    Document,
    VectorStoreIndex,
    QueryBundle,
    load_index_from_storage,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import NodeWithScore
from llama_index.core.retrievers import VectorIndexRetriever, BaseRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.storage import StorageContext
from llama_index.vector_stores.faiss import FaissVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.base.llms.types import LLMMetadata
from llama_index.llms.ollama import Ollama
from llama_index.core.llms import ChatMessage

from sentence_transformers import CrossEncoder
import faiss
import torch

from .utils import normalize_url, extract_url, clean_response_text

# ============================== DEBUG SETUP ================================= #

DEBUG_RAG = os.getenv("HEIBOT_DEBUG", "0") == "1"
DEBUG_TO_CHAT = os.getenv("HEIBOT_DEBUG_TO_CHAT", "0") == "1"

def _setup_debug_logging():
    if DEBUG_RAG:
        root = logging.getLogger()
        if not any(isinstance(h, logging.FileHandler) and getattr(h, "_hei_dbg", False) for h in root.handlers):
            fh = logging.FileHandler("rag_debug.log", encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh._hei_dbg = True  # mark so we don't add twice
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            fh.setFormatter(fmt)
            root.addHandler(fh)
        root.setLevel(logging.DEBUG)

_setup_debug_logging()

def _snip(text: str, n: int = 320) -> str:
    if not text:
        return ""
    t = re.sub(r"\s+", " ", text.strip())
    return t[:n] + ("…" if len(t) > n else "")

def _jdump(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)

# ============================================================================ #

# --------------------------------------------------------------------------- #
#                              LLM & SYSTEM PROMPT                            #
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """
You are a helpful research assistant that answers user questions with the help of a retrieval-augmented knowledge library. The library is populated from documents that users upload or crawl, so only rely on material that appears in the retrieved context.

Think and plan silently. Never reveal hidden reasoning. Respond with only the final answer (with citations when applicable).

Language handling:
- Detect the user’s language. If the message is mostly German, reply in German; otherwise reply in English.

When answering content questions:
- Base your answer strictly on the retrieved context snippets. If you use information from the context, add a Markdown citation immediately after each relevant sentence and append a **Sources/Quellen** section listing the cited URLs.
- If the context does not contain the necessary information, clearly state that the knowledge library does not cover it yet and kindly suggest that the user upload files or website content that might help.
- Keep responses concise but complete. Use **bold** section headers, numbered steps for procedures, and bullet lists for overviews. Expand acronyms on first use and use _underline_ for key terms when helpful.

Meta or chit-chat questions about yourself or the system:
- Answer briefly from your built-in knowledge without consulting the library and do not add citations or a Sources section.
- Mention that you are a retrieval-augmented assistant that depends on the user-provided library.

Out-of-scope requests that clearly cannot be assisted by the library:
- Politely redirect the user to provide or upload relevant material.

If the knowledge library is empty, explicitly inform the user that no documents are available yet and invite them to upload content so you can assist.
"""

class PatchedOllama(Ollama):
    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=self.context_window,
            num_output=512,
            is_chat_model=True,
            model_name=self.model,
        )

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

# ---- Ollama runtime tuning ------------------------------------------------- #

def _env_int(name: str, default: int) -> int:
    try:
        value = os.getenv(name)
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        value = os.getenv(name)
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:27b")
OLLAMA_TEMPERATURE = _env_float("OLLAMA_TEMPERATURE", 0.2)
OLLAMA_NUM_PREDICT = _env_int("OLLAMA_NUM_PREDICT", 512)
OLLAMA_NUM_CTX = _env_int("OLLAMA_NUM_CTX", 2048)
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "5m")

ollama_options = {}

_num_gpu = os.getenv("OLLAMA_NUM_GPU")
if _num_gpu is not None:
    try:
        ollama_options["num_gpu"] = int(_num_gpu)
    except ValueError:
        logger.warning("Invalid OLLAMA_NUM_GPU=%s (expected int)", _num_gpu)

_main_gpu = os.getenv("OLLAMA_MAIN_GPU")
if _main_gpu is not None:
    try:
        ollama_options["main_gpu"] = int(_main_gpu)
    except ValueError:
        logger.warning("Invalid OLLAMA_MAIN_GPU=%s (expected int)", _main_gpu)

_num_thread = os.getenv("OLLAMA_NUM_THREAD")
if _num_thread is not None:
    try:
        ollama_options["num_thread"] = int(_num_thread)
    except ValueError:
        logger.warning("Invalid OLLAMA_NUM_THREAD=%s (expected int)", _num_thread)

_num_batch = os.getenv("OLLAMA_NUM_BATCH")
if _num_batch is not None:
    try:
        ollama_options["num_batch"] = int(_num_batch)
    except ValueError:
        logger.warning("Invalid OLLAMA_NUM_BATCH=%s (expected int)", _num_batch)

for flag in ("use_mmap", "use_mlock", "low_vram"):
    env_name = f"OLLAMA_{flag.upper()}"
    val = os.getenv(env_name)
    if val is not None:
        if val.lower() in {"1", "true", "yes", "on"}:
            ollama_options[flag] = True
        elif val.lower() in {"0", "false", "no", "off"}:
            ollama_options[flag] = False
        else:
            logger.warning("Invalid %s=%s (expected boolean)", env_name, val)

additional_kwargs = {"num_predict": OLLAMA_NUM_PREDICT, "num_ctx": OLLAMA_NUM_CTX}
if ollama_options:
    additional_kwargs["options"] = ollama_options

Settings.llm = PatchedOllama(
    model=OLLAMA_MODEL,
    base_url=OLLAMA_BASE_URL,
    temperature=OLLAMA_TEMPERATURE,
    system_prompt=SYSTEM_PROMPT,
    additional_kwargs=additional_kwargs,
    keep_alive=OLLAMA_KEEP_ALIVE,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#                                Embeddings (DE/EN)                           #
# --------------------------------------------------------------------------- #

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
Settings.embed_model = HuggingFaceEmbedding(
    model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    device=DEVICE,
)

# --------------------------------------------------------------------------- #
#                         Cross-encoder reranker (multilingual)               #
# --------------------------------------------------------------------------- #

rerank_model = CrossEncoder(
    "BAAI/bge-reranker-v2-m3",
    max_length=512,
    device=DEVICE,
)

if DEVICE == "cuda":
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    if os.getenv("RERANKER_FP16", "1").lower() not in {"0", "false", "no"}:
        try:
            rerank_model.model.half()
        except AttributeError:
            logger.debug("Cross-encoder model does not support half precision")

# Serialize cross-encoder calls across threads to avoid GPU/torch races
_RERANK_LOCK = threading.Lock()

PERSIST_DIR = "index_store"

RAG_CHAR_MIN = 300

INSUFFICIENT_PATTERNS = [
    "context provided does not contain",
    "i couldn’t find that information",
    "i couldn't find that information",
    "in the provided materials",
    "kontext enthält keine informationen",
    "dazu finde ich in den unterlagen nichts",
]

# --------------------------------------------------------------------------- #
#                          Conversation & Chat History                        #
# --------------------------------------------------------------------------- #

STOPWORDS_DE_EN = {
    "der","die","das","und","ist","nicht","sie","ich","du","wir","ihr","es","ein","eine","den","dem","des",
    "wie","was","wo","warum","wann","zum","zur","für","mit","ohne","auf","im","in","an","am","oder","auch",
    "dass","so","nur","bitte","noch","danke","frage",
    "the","and","is","are","was","were","be","to","of","in","on","for","a","an","it","this","that","how",
    "what","why","when","or","also","please","thanks","thank","you","your","my","our","their"
}


def _library_empty_message(is_german: bool) -> str:
    if is_german:
        return (
            "Es befinden sich noch keine Dokumente in der Wissensbibliothek. "
            "Bitte laden Sie Dateien hoch oder fügen Sie Website-Inhalte hinzu, damit ich Sie unterstützen kann."
        )
    return (
        "There are no documents in the knowledge library yet. "
        "Please upload files or add website content so I can assist you."
    )


def _is_german(text: str) -> bool:
    t = (text or "").lower()
    return bool(re.search(r"[äöüß]|\b(der|die|das|und|ist|nicht|wie|wo|sie|ich)\b", t))

def recent_user_text(history, max_turns: int = 3) -> str:
    users = [h.get("content","").replace("\n"," ").strip()
             for h in history if h.get("role") == "user"]
    return " | ".join(users[-max_turns:])

def extract_hint_keywords(text: str, limit: int = 6) -> List[str]:
    toks = re.findall(r"[A-Za-zÄÖÜäöüß\-]{3,}", text)
    seen, out = set(), []
    for t in toks:
        tl = t.lower()
        if tl in STOPWORDS_DE_EN:
            continue
        if tl not in seen:
            seen.add(tl)
            out.append(tl)
        if len(out) >= limit:
            break
    return out

def format_user_history_same_lang(history, current_text, max_turns: int = 3, max_chars: int = 600) -> str:
    """Return only recent USER turns in the same language as current_text."""
    is_de = _is_german(current_text)
    parts = []
    for h in reversed(history):
        if h.get("role") != "user":
            continue
        txt = (h.get("content") or "").replace("\n", " ").strip()
        if not txt:
            continue
        if _is_german(txt) != is_de:
            continue
        parts.append(f"User: {txt}")
        if len(parts) >= max_turns:
            break
    parts.reverse()
    ctx = "\n".join(parts).strip()
    if len(ctx) > max_chars:
        ctx = ctx[-max_chars:]
    return ctx

# ---- Topic overlap / pronoun handling ------------------------------------- #

_TOKEN_PAT = re.compile(r"[A-Za-zÄÖÜäöüß\-]{3,}")

def _content_tokens(s: str) -> set:
    return {t.lower() for t in _TOKEN_PAT.findall(s or "") if t.lower() not in STOPWORDS_DE_EN}

def _topic_overlap(a: str, b: str) -> float:
    A, B = _content_tokens(a), _content_tokens(b)
    return 0.0 if not A or not B else len(A & B) / len(A | B)

PRONOUNS = {
    "it","this","that","these","those","they","them",
    "es","das","dies","diese","dieses","jenes","sie"
}

def _pronoun_only(q: str) -> bool:
    toks = [t.lower() for t in _TOKEN_PAT.findall((q or "").lower()) if t.lower() not in STOPWORDS_DE_EN]
    return (not toks) or all(t in PRONOUNS for t in toks)

# --------------------------------------------------------------------------- #

class ConversationManager:
    def __init__(self, max_history: int = 5):
        self.max_history = max_history
        self.conversations: Dict[str, List[Dict]] = {}
        self._lock = threading.RLock()

    def add_message(self, session_id: str, role: str, content: str):
        with self._lock:
            hist = self.conversations.setdefault(session_id, [])
            hist.append({"role": role, "content": content, "timestamp": datetime.now()})
            if len(hist) > self.max_history:
                hist.pop(0)

    def get_conversation_history(self, session_id: str):
        with self._lock:
            return list(self.conversations.get(session_id, []))

    def clear_conversation(self, session_id: str):
        with self._lock:
            self.conversations.pop(session_id, None)

conversation_manager = ConversationManager()

# --------------------------------------------------------------------------- #
#                               Helpers & gates                               #
# --------------------------------------------------------------------------- #

def _as_node(x):
    return x.node if isinstance(x, NodeWithScore) else x

def _tokenize_query(text: str) -> List[str]:
    toks = re.findall(r"[A-Za-zÄÖÜäöüß\-]{3,}", (text or "").lower())
    return [t for t in toks if t not in STOPWORDS_DE_EN]

def _context_text(nodes: List) -> str:
    parts = []
    for n in nodes:
        try:
            parts.append(_as_node(n).get_content(metadata_mode="node_only").lower())
        except Exception:
            pass
    return "\n".join(parts)

def _looks_like_meta_or_oos(query: str, answer: str) -> bool:
    q = (query or "").lower()
    a = (answer or "").lower()
    META_TRIGGERS = [
        "who are you","wer bist du","what model","welches modell",
        "which model","system prompt","capabilities","fähigkeiten",
        "languages","sprachen","ollama","gemma","backend","role","rolle"
    ]
    if any(t in q for t in META_TRIGGERS):
        return True
    if any(p in a for p in INSUFFICIENT_PATTERNS):
        return True
    return False

def _used_rag_meaningfully(query: str, answer: str, nodes: List[NodeWithScore]) -> bool:
    """True iff retrieved context is actually relevant to the query (relative thresholds)."""
    if _looks_like_meta_or_oos(query, answer):
        return False
    if not nodes:
        return False
    scores = [float(getattr(n, "score")) for n in nodes if getattr(n, "score", None) is not None]
    if scores:
        smin, smax = min(scores), max(scores)
        spread = (smax - smin) or 1.0
        top1 = scores[0]
        top3 = scores[: min(3, len(scores))]
        top1_norm = (top1 - smin) / spread
        top3_mean_norm = ((sum(top3) / len(top3)) - smin) / spread
        return (top1_norm >= 0.65) or (top3_mean_norm >= 0.55)
    ctx = _context_text(nodes)
    if len(ctx) < RAG_CHAR_MIN:
        return False
    q_tokens = set(_tokenize_query(query))
    if not q_tokens:
        return False
    hit_ratio = sum(t in ctx for t in q_tokens) / max(1, len(q_tokens))
    return hit_ratio >= 0.15

# --------------------------------------------------------------------------- #
#                          Retrieval wrappers / chain                          #
# --------------------------------------------------------------------------- #

class HistoryAwareVectorRetriever(BaseRetriever):
    """Augments latest query with compact topic hints (pronoun-aware).

    DEBUG: stores last_query for inspection.
    """
    def __init__(self, base: VectorIndexRetriever, max_chars: int = 512):
        super().__init__()
        self.base = base
        self.max_chars = max_chars
        self.last_query: Optional[str] = None

    def _compose(self, latest_query: str, chat_history: Optional[str], history_for_keywords: Optional[str]) -> str:
        # Prefer current query keywords; fall back to history when the query is pronoun-like
        kw_cur  = extract_hint_keywords(latest_query, limit=4)
        kw_hist = extract_hint_keywords(history_for_keywords or "", limit=6)

        if _pronoun_only(latest_query) or not kw_cur:
            hint = kw_hist[:6]
        else:
            # merge unique, keep compact
            seen = set()
            hint = []
            for k in kw_cur + kw_hist:
                if k not in seen:
                    seen.add(k)
                    hint.append(k)
                if len(hint) >= 6:
                    break

        hint_blob = f" topic:{' '.join(hint)}" if hint else ""
        return f"{latest_query}{hint_blob}".strip()

    def _to_text(self, qb: Union[QueryBundle, str]) -> str:
        return qb.query_str if isinstance(qb, QueryBundle) else str(qb)

    def _retrieve(self, query_bundle: Union[QueryBundle, str], **kwargs):
        user_context = kwargs.get("user_context", "")
        full_q = self._compose(self._to_text(query_bundle), None, user_context)
        self.last_query = full_q
        fwd = {k: v for k, v in kwargs.items() if k not in ("chat_history", "user_context")}
        return self.base.retrieve(full_q, **fwd)

    async def aretrieve(self, query_bundle: Union[QueryBundle, str], **kwargs):
        user_context = kwargs.get("user_context", "")
        full_q = self._compose(self._to_text(query_bundle), None, user_context)
        self.last_query = full_q
        fwd = {k: v for k, v in kwargs.items() if k not in ("chat_history", "user_context")}
        return await self.base.aretrieve(full_q, **fwd)

class UniqueUrlRetriever(BaseRetriever):
    def __init__(self, base: BaseRetriever, max_unique: int = 10):
        super().__init__()
        self.base = base
        self.max_unique = max_unique

    def _filter_unique(self, nodes):
        unique = {}
        filtered = []
        for n in nodes:
            base = n.node if isinstance(n, NodeWithScore) else n
            url = extract_url(base)
            if url not in unique:
                unique[url] = True
                filtered.append(n if isinstance(n, NodeWithScore) else NodeWithScore(node=base))
            if len(filtered) >= self.max_unique:
                break
        return filtered

    def _retrieve(self, query_bundle: QueryBundle, **kwargs):
        nodes = self.base.retrieve(query_bundle, **kwargs)
        return self._filter_unique(nodes)

    async def aretrieve(self, query_bundle: QueryBundle, **kwargs):
        nodes = await self.base.aretrieve(query_bundle, **kwargs)
        return self._filter_unique(nodes)

class KeywordFallbackRetriever(BaseRetriever):
    """Primary results + token/keyword matches. DEBUG: stores last tokens & urls."""
    def __init__(
        self,
        primary: BaseRetriever,
        nodes,
        url_map,
        token_index,
        keyword_map=None,
        token_node_limit=None,
        fallback_limit=None,
    ):
        super().__init__()
        self.primary = primary
        self.nodes = nodes
        self.url_map = url_map
        self.token_index = token_index
        self.keyword_map = {}
        self.token_node_limit = token_node_limit or len(nodes)
        self.fallback_limit = fallback_limit or len(nodes)
        self._token_pattern = re.compile(r"[A-Za-zÄÖÜäöüß]{4,}")
        self._url_pattern = re.compile(r"https?://[^\s]+")
        # debug
        self.last_tokens: List[str] = []
        self.last_priority_urls: List[str] = []
        self.last_combined_urls: List[str] = []

        if keyword_map:
            for key, urls in keyword_map.items():
                merged = []
                for u in urls:
                    norm = normalize_url(u)
                    merged.extend(url_map.get(norm, []))
                if merged:
                    self.keyword_map[key] = merged

    def _tokenize(self, text: str) -> List[str]:
        toks = self._token_pattern.findall(text.lower())
        seen, out = set(), []
        for t in toks:
            if t in STOPWORDS_DE_EN: continue
            if t not in seen:
                seen.add(t); out.append(t)
        return out

    def _tokens_from_query_and_history(self, q: str, history: Optional[str], user_ctx: Optional[str]) -> List[str]:
        base = q
        if history: base = f"{history}\n{base}"
        if user_ctx: base = f"{user_ctx}\n{base}"
        return self._tokenize(base)

    def _retrieve_common(self, query_bundle: QueryBundle, **kwargs):
        if isinstance(query_bundle, str):
            query_bundle = QueryBundle(query_bundle)
        q = query_bundle.query_str
        history = kwargs.get("chat_history")
        user_ctx = kwargs.get("user_context")

        q_full = f"{user_ctx or ''}\n{history or ''}\n{q}".lower()

        # explicit URL presence
        for url in self._url_pattern.findall(q_full):
            norm = normalize_url(url)
            if norm in self.url_map:
                nodes = [NodeWithScore(node=n) for n in self.url_map[norm]]
                self.last_tokens = []
                self.last_priority_urls = [norm]
                self.last_combined_urls = [norm]
                return nodes

        priority = []
        priority_urls = []
        for key, knodes in self.keyword_map.items():
            if key in q_full:
                priority.extend(knodes)
                for n in knodes:
                    u = extract_url(n)
                    if u: priority_urls.append(u)

        tokens = self._tokens_from_query_and_history(q, history, user_ctx)
        self.last_tokens = tokens

        return priority, priority_urls, tokens

    def _post(self, combined):
        if combined:
            filtered, seen_urls = [], set()
            for n in combined:
                url = extract_url(_as_node(n))
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    filtered.append(n if isinstance(n, NodeWithScore) else NodeWithScore(node=n))
            self.last_combined_urls = list(seen_urls)
            return filtered
        self.last_combined_urls = []
        return []

    def _retrieve(self, query_bundle: QueryBundle, **kwargs):
        res = self._retrieve_common(query_bundle, **kwargs)
        if isinstance(res, list):  # direct return
            return res
        priority, priority_urls, tokens = res
        results = self.primary.retrieve(query_bundle, **kwargs)
        token_nodes = []
        for t in tokens:
            for n in self.token_index.get(t, []):
                if n not in token_nodes:
                    token_nodes.append(n)
                if len(token_nodes) >= self.token_node_limit:
                    break
        self.last_priority_urls = priority_urls
        return self._post(priority + token_nodes + (results or []))

    async def aretrieve(self, query_bundle: QueryBundle, **kwargs):
        res = self._retrieve_common(query_bundle, **kwargs)
        if isinstance(res, list):  # direct return
            return res
        priority, priority_urls, tokens = res
        results = await self.primary.aretrieve(query_bundle, **kwargs)
        token_nodes = []
        for t in tokens:
            for n in self.token_index.get(t, []):
                if n not in token_nodes:
                    token_nodes.append(n)
                if len(token_nodes) >= self.token_node_limit:
                    break
        self.last_priority_urls = priority_urls
        return self._post(priority + token_nodes + (results or []))

class CrossEncoderReranker(BaseRetriever):
    """DEBUG: stores last query and scored candidates."""
    def __init__(self, base: BaseRetriever, model: CrossEncoder, top_k: int = 10):
        super().__init__()
        self.base = base
        self.model = model
        self.top_k = top_k
        self.last_query_text: Optional[str] = None
        self.last_candidates: List[Dict] = []

    def _make_query(self, latest_query: str, chat_history: Optional[str], user_ctx: Optional[str]) -> str:
        # Drop history/topic hints here to avoid drift; vector stage handles pronouns.
        self.last_query_text = latest_query
        return latest_query

    def _rerank(self, query: str, nodes):
        if not nodes:
            self.last_candidates = []
            return []
        bases = [_as_node(n) for n in nodes]
        pairs = [(query, b.get_content()) for b in bases]
        # serialize predict for thread-safety on shared GPU/CPU model
        with _RERANK_LOCK:
            scores = self.model.predict(pairs, batch_size=8)

        order = sorted(range(len(bases)), key=lambda i: scores[i], reverse=True)[: self.top_k]
        out = []
        cands = []
        for i in range(len(bases)):
            url = extract_url(bases[i]) or "N/A"
            cands.append({
                "idx": i,
                "url": url,
                "score": float(scores[i]),
                "preview": _snip(bases[i].get_content()),
            })
        self.last_candidates = sorted(cands, key=lambda x: x["score"], reverse=True)[: self.top_k]

        for i in order:
            out.append(NodeWithScore(node=bases[i], score=float(scores[i])))
        return out

    def _retrieve(self, query_bundle: QueryBundle, **kwargs):
        nodes = self.base.retrieve(query_bundle, **kwargs)
        latest = query_bundle.query_str if not isinstance(query_bundle, str) else query_bundle
        q = self._make_query(latest, kwargs.get("chat_history"), kwargs.get("user_context"))
        return self._rerank(q, nodes)

    async def aretrieve(self, query_bundle: QueryBundle, **kwargs):
        nodes = await self.base.aretrieve(query_bundle, **kwargs)
        latest = query_bundle.query_str if not isinstance(query_bundle, str) else query_bundle
        q = self._make_query(latest, kwargs.get("chat_history"), kwargs.get("user_context"))
        return self._rerank(q, nodes)

# -------------------------- chain walkers (debug) --------------------------- #

def _get_chain_parts(top: BaseRetriever):
    """Return (reranker, hybrid, unique, history_aware) where available."""
    rer = top if isinstance(top, CrossEncoderReranker) else None
    hyb = rer.base if rer and isinstance(rer.base, KeywordFallbackRetriever) else None
    uniq = hyb.primary if hyb and isinstance(hyb.primary, UniqueUrlRetriever) else None
    hist = uniq.base if uniq and isinstance(uniq.base, HistoryAwareVectorRetriever) else None
    return rer, hyb, uniq, hist

# --------------------------------------------------------------------------- #
#                              Chat processing                                 #
# --------------------------------------------------------------------------- #

async def process_query(message: str, query_engine: RetrieverQueryEngine, session_id: str):
    """Non-streaming path; same-language user history, topic-switch reset, pronoun-aware vector hints."""
    try:
        history = conversation_manager.get_conversation_history(session_id)

        # topic-switch logic (reset unless same topic or pronoun-only)
        is_de = _is_german(message)
        last_same_lang = ""
        for h in reversed(history):
            if h.get("role") == "user" and _is_german(h.get("content","")) == is_de:
                last_same_lang = h.get("content","")
                break

        if _topic_overlap(message, last_same_lang) < 0.25 and not _pronoun_only(message):
            chat_ctx = ""
            user_ctx = ""
        else:
            chat_ctx = format_user_history_same_lang(history, message)
            user_ctx = recent_user_text(history)

        # Retrieve (with the chosen history/user_ctx)
        nodes_ws = await query_engine.retriever.aretrieve(
            message,
            chat_history=chat_ctx,
            user_context=user_ctx,
        )
        base_nodes: List[NodeWithScore] = [
            n if isinstance(n, NodeWithScore) else NodeWithScore(node=_as_node(n)) for n in nodes_ws
        ]

        library_size = getattr(query_engine, "library_size", None)
        if library_size == 0:
            is_german = _is_german(message)
            response_text = _library_empty_message(is_german)
            conversation_manager.add_message(session_id, "user", message)
            conversation_manager.add_message(session_id, "assistant", response_text)
            return response_text

        context = "\n\n".join(_as_node(n).get_content(metadata_mode="node_only") for n in base_nodes)

        # LLM call (context-constrained)
        user_msg = ChatMessage(
            role="user",
            content=(
                "Answer using ONLY the context below. If the context is insufficient, say so.\n\n"
                f"Context:\n{context}\n\nQuestion:\n{message}"
            ),
        )
        resp = await Settings.llm.achat([user_msg])
        raw_answer = (getattr(resp, "message", None) and getattr(resp.message, "content", "")) or str(resp)
        main_answer, think_text = clean_response_text(raw_answer or "")

        conversation_manager.add_message(session_id, "user", message)

        # Citations
        citations: List[str] = []
        seen: set = set()
        for node in base_nodes:
            url = extract_url(_as_node(node))
            if url and url not in seen:
                seen.add(url); citations.append(url)

        # Footer
        if citations and _used_rag_meaningfully(message, main_answer, base_nodes):
            header = "Quellen" if _is_german(message) else "Sources"
            links = "\n".join(f"- [{u}]({u})" for u in citations)
            main_answer = f"{main_answer}\n\n**{header}:**\n{links}"

        # ---------- DEBUG TRACE ----------
        if DEBUG_RAG:
            rer, hyb, uniq, hist = _get_chain_parts(query_engine.retriever)
            dbg = {
                "turn": "process_query",
                "message": message,
                "same_lang_user_history": chat_ctx,
                "user_ctx_for_keywords": user_ctx,
                "vector_query": (hist and hist.last_query) or "",
                "reranker_query": (rer and rer.last_query_text) or "",
                "reranker_candidates": (rer and rer.last_candidates) or [],
                "keyword_tokens": (hyb and hyb.last_tokens) or [],
                "priority_urls": (hyb and hyb.last_priority_urls) or [],
                "combined_urls": (hyb and hyb.last_combined_urls) or [],
                "context_len": len(context),
                "context_preview": _snip(context, 600),
                "llm_prompt_preview": _snip(user_msg.content, 600),
                "citations": citations,
            }
            logger.debug(_jdump(dbg))
            if DEBUG_TO_CHAT:
                main_answer += (
                    "\n\n<details><summary>Debug</summary>\n\n```json\n"
                    + _jdump(dbg) + "\n```\n</details>"
                )
        # ---------------------------------

        conversation_manager.add_message(session_id, "assistant", main_answer)
        return {"answer": main_answer, "think": think_text, "citations": citations}

    except Exception as exc:
        logger.error("Error processing query: %s", exc, exc_info=True)
        return {"answer": f"Error: {exc}", "citations": []}

async def stream_query(message: str, query_engine: RetrieverQueryEngine, session_id: str):
    """Streaming path; same behavior as non-streaming for history/topic handling."""
    history = conversation_manager.get_conversation_history(session_id)

    is_de = _is_german(message)
    last_same_lang = ""
    for h in reversed(history):
        if h.get("role") == "user" and _is_german(h.get("content","")) == is_de:
            last_same_lang = h.get("content","")
            break

    if _topic_overlap(message, last_same_lang) < 0.25 and not _pronoun_only(message):
        chat_ctx = ""
        user_ctx = ""
    else:
        chat_ctx = format_user_history_same_lang(history, message)
        user_ctx = recent_user_text(history)

    nodes_ws = await query_engine.retriever.aretrieve(
        message,
        chat_history=chat_ctx,
        user_context=user_ctx,
    )
    base_nodes: List[NodeWithScore] = [
        n if isinstance(n, NodeWithScore) else NodeWithScore(node=_as_node(n)) for n in nodes_ws
    ]

    library_size = getattr(query_engine, "library_size", None)
    if library_size == 0:
        response_text = _library_empty_message(is_de)
        conversation_manager.add_message(session_id, "user", message)
        conversation_manager.add_message(session_id, "assistant", response_text)
        yield response_text
        return

    context = "\n\n".join(_as_node(n).get_content(metadata_mode="node_only") for n in base_nodes)

    user_msg = ChatMessage(
        role="user",
        content=(
            "Answer using ONLY the context below. If the context is insufficient, say so.\n\n"
            f"Context:\n{context}\n\nQuestion:\n{message}"
        ),
    )

    stream = await Settings.llm.astream_chat([user_msg])

    main_buf = ""
    async for chunk in stream:
        text = (getattr(chunk, "delta", None) or "")
        if text:
            main_buf += text
            yield text

    main_answer = main_buf.strip()
    conversation_manager.add_message(session_id, "user", message)

    citations: List[str] = []
    seen: set = set()
    for node in base_nodes:
        url = extract_url(_as_node(node))
        if url and url not in seen:
            seen.add(url)
            citations.append(url)

    if citations and _used_rag_meaningfully(message, main_answer, base_nodes):
        header = "Quellen" if _is_german(message) else "Sources"
        links = "\n".join(f"- [{u}]({u})" for u in citations)
        citations_text = f"\n\n**{header}:**\n{links}"
        yield citations_text
        main_answer = f"{main_answer}{citations_text}"

    # ---------- DEBUG TRACE ----------
    if DEBUG_RAG:
        rer, hyb, uniq, hist = _get_chain_parts(query_engine.retriever)
        dbg = {
            "turn": "stream_query",
            "message": message,
            "same_lang_user_history": chat_ctx,
            "user_ctx_for_keywords": user_ctx,
            "vector_query": (hist and hist.last_query) or "",
            "reranker_query": (rer and rer.last_query_text) or "",
            "reranker_candidates": (rer and rer.last_candidates) or [],
            "keyword_tokens": (hyb and hyb.last_tokens) or [],
            "priority_urls": (hyb and hyb.last_priority_urls) or [],
            "combined_urls": (hyb and hyb.last_combined_urls) or [],
            "context_len": len(context),
            "context_preview": _snip(context, 600),
            "llm_prompt_preview": _snip(user_msg.content, 600),
            "citations": citations,
        }
        logger.debug(_jdump(dbg))
        if DEBUG_TO_CHAT:
            dbg_block = "\n\n<details><summary>Debug</summary>\n\n```json\n" + _jdump(dbg) + "\n```\n</details>"
            yield dbg_block
            main_answer = f"{main_answer}{dbg_block}"
    # ---------------------------------

    conversation_manager.add_message(session_id, "assistant", main_answer)

# --------------------------------------------------------------------------- #
#                 CONCURRENCY-SAFE SYNC WRAPPERS FOR WSGI SERVERS            #
# --------------------------------------------------------------------------- #

def process_query_sync(message: str, query_engine: RetrieverQueryEngine, session_id: str):
    """
    Run the async process_query() in a NEW event loop (per call),
    so WSGI/Flask threads never reuse a running loop.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(process_query(message, query_engine, session_id))
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)

def stream_query_sync(message: str, query_engine: RetrieverQueryEngine, session_id: str):
    """
    Yield chunks from the async stream_query() using a NEW event loop
    **owned by this generator**. Safe to iterate from any thread.
    """
    agen = stream_query(message, query_engine, session_id)

    def _iterator():
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            while True:
                try:
                    chunk = loop.run_until_complete(agen.__anext__())
                except StopAsyncIteration:
                    break
                yield chunk
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()
            asyncio.set_event_loop(None)

    return _iterator()

# --------------------------------------------------------------------------- #
#                           Crawling / Index building                          #
# --------------------------------------------------------------------------- #

async def fetch_and_clean_html(session, url, exclude_selectors=None):
    try:
        async with session.get(url, timeout=60) as response:
            if response.status != 200:
                return None
            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            for selector in exclude_selectors or []:
                for tag in soup.select(selector):
                    tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            return Document(text=text, metadata={"url": url})
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return None

async def load_documents_from_urls(urls, exclude_selectors=None):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_and_clean_html(session, u, exclude_selectors) for u in urls]
        results = await asyncio.gather(*tasks)
    return [doc for doc in results if doc is not None]

def clean_sitemap_urls(sitemap_url: str):
    response = requests.get(sitemap_url)
    root = ET.fromstring(response.content)
    namespaces = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    cleaned = []
    for url_element in root.findall(".//sm:url", namespaces):
        loc = url_element.find("sm:loc", namespaces)
        if loc is None or loc.text is None:
            continue
        url = loc.text.strip()
        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        allowed = ["/support", "/service-catalogue", "/service-katalog", "/anleitungen"]
        if not any(seg in path_lower for seg in allowed):
            continue
        clean_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        cleaned.append(clean_url)
    return cleaned

# --------------------------------------------------------------------------- #
#                                Init pipeline                                 #
# --------------------------------------------------------------------------- #

async def async_init(urls: List[str], persist_dir: str = PERSIST_DIR) -> RetrieverQueryEngine:
    has_faiss = os.path.exists(os.path.join(persist_dir, "faiss.index"))
    has_legacy_json = os.path.exists(os.path.join(persist_dir, "index_store.json"))
    has_vector_json = len(glob.glob(os.path.join(persist_dir, "*__vector_store.json"))) > 0
    has_docstore = os.path.exists(os.path.join(persist_dir, "docstore.json"))
    has_vector = has_faiss or has_legacy_json or has_vector_json

    if os.path.isdir(persist_dir) and has_vector and has_docstore:
        logger.info("Loading existing FAISS index from %s", persist_dir)
        faiss_store = FaissVectorStore.from_persist_dir(persist_dir)
        storage_context = StorageContext.from_defaults(
            vector_store=faiss_store, persist_dir=persist_dir
        )
        index = load_index_from_storage(storage_context)
        with open(os.path.join(persist_dir, "nodes.pkl"), "rb") as f:
            nodes = pickle.load(f)
    else:
        logger.info("Building FAISS index from scratch ...")
        docs = await load_documents_from_urls(
            urls, exclude_selectors=["header", "footer", "nav", ".breadcrumbs"]
        )
        parser = SentenceSplitter(chunk_size=256, chunk_overlap=32)
        nodes = parser.get_nodes_from_documents(docs)
        faiss_store = FaissVectorStore(faiss.IndexFlatL2(768))  # matches multilingual-mpnet
        storage_context = StorageContext.from_defaults(vector_store=faiss_store)
        index = VectorStoreIndex(nodes, storage_context=storage_context, show_progress=True)
        storage_context.persist(persist_dir=persist_dir)
        os.makedirs(persist_dir, exist_ok=True)
        with open(os.path.join(persist_dir, "nodes.pkl"), "wb") as f:
            pickle.dump(nodes, f)

    # Helper maps
    url_to_nodes = {}
    for n in nodes:
        u = extract_url(n)
        if u:
            u = normalize_url(u)
            url_to_nodes.setdefault(u, []).append(n)

    token_pattern = re.compile(r"\w{3,}")
    token_to_nodes = {}
    for n in nodes:
        tokens = set(token_pattern.findall(n.get_content().lower()))
        for t in tokens:
            token_to_nodes.setdefault(t, []).append(n)

    # Base vector retriever (history-aware wrapper)
    vect_base = VectorIndexRetriever(index=index, similarity_top_k=8, fetch_k=8)
    vect = HistoryAwareVectorRetriever(vect_base, max_chars=512)

    # Chain
    unique_vect = UniqueUrlRetriever(vect, max_unique=5)
    hybrid = KeywordFallbackRetriever(unique_vect, nodes, url_to_nodes, token_to_nodes)
    reranked = CrossEncoderReranker(hybrid, rerank_model, top_k=3)

    engine = RetrieverQueryEngine(retriever=reranked)
    engine.library_size = len(nodes)
    return engine
