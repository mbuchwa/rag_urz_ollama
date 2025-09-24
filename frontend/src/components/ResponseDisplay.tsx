// frontend/src/components/ResponseDisplay.tsx
import { useEffect, useMemo, useRef, useState } from "react";

declare global {
  interface Window {
    marked?: {
      setOptions: (o: any) => void;
      parse: (md: string, opts?: any) => string;
      Renderer: new () => any;
    };
    DOMPurify?: { sanitize: (html: string, cfg?: any) => string };
  }
}

export interface Citation {
  docId: string
  ord: number
  title: string | null
  chunkId?: string | null
  text?: string | null
}

export interface Message {
  sender: "user" | "bot"
  text: unknown
  think?: string
  citations?: Citation[]
}

type Props = {
  messages: Message[];
  loading: boolean;
  onSelectThinking: (think: string) => void;
  thinkingEnabled: boolean;
  onSelectCitation?: (citation: Citation) => void;
};

function toStr(v: unknown) {
  if (v == null) return "";
  return typeof v === "string" ? v : String(v);
}

function escapeHtml(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/**
 * Wrap bare emails in <...> so Marked converts to mailto:
 * Skips fenced code blocks ```...``` and inline code `...`.
 */
function linkifyEmailsOutsideCode(md: string): string {
  // Hold fenced blocks
  const fenceRe = /```[\s\S]*?```/g;
  const fences: string[] = [];
  let tmp = md.replace(fenceRe, (m) => {
    fences.push(m);
    return `\u0000F${fences.length - 1}\u0000`;
  });

  // Hold inline code
  const inlineRe = /`[^`]*`/g;
  const inlines: string[] = [];
  tmp = tmp.replace(inlineRe, (m) => {
    inlines.push(m);
    return `\u0001I${inlines.length - 1}\u0001`;
  });

  // Linkify bare emails in the remaining text
  const emailRe = /\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b/g;
  tmp = tmp.replace(emailRe, (_m, addr) => `<${addr}>`);

  // Restore inline code then fences
  tmp = tmp.replace(/\u0001I(\d+)\u0001/g, (_, i) => inlines[Number(i)]);
  tmp = tmp.replace(/\u0000F(\d+)\u0000/g, (_, i) => fences[Number(i)]);
  return tmp;
}

function renderMarkdown(mdInput: unknown): { html: string; ok: boolean } {
  const md = toStr(mdInput);

  if (!window.marked || !window.DOMPurify) {
    return { html: `<p>${escapeHtml(md)}</p>`, ok: false };
  }

  try {
    const m: any = window.marked;

    m.setOptions({
      gfm: true,
      breaks: true,
      mangle: false,      // do not obfuscate emails
      headerIds: false,
    });

    // robust renderer across marked versions
    const renderer: any = new m.Renderer();

    // Old signature: link(href, title, text)
    if (typeof renderer.link === "function" && renderer.link.length === 3) {
      renderer.link = (href: string, _title: string, text: string) => {
        const safeHref = escapeHtml(href || "");
        const safeText = escapeHtml(text || href || "");
        return `<a href="${safeHref}" target="_blank" rel="noreferrer" class="chat-link">${safeText}</a>`;
      };
    } else {
      // New signature: link(token)
      renderer.link = (token: any) => {
        const href = token?.href ?? "";
        const text = token?.text ?? href;
        const safeHref = escapeHtml(String(href));
        const safeText = escapeHtml(String(text));
        return `<a href="${safeHref}" target="_blank" rel="noreferrer" class="chat-link">${safeText}</a>`;
      };
    }

    // Pre-pass: make bare emails clickable (outside code)
    const prepared = linkifyEmailsOutsideCode(md);

    const raw = m.parse(prepared, { renderer });
    const html = window.DOMPurify!.sanitize(raw, {
      ADD_ATTR: ["target", "rel", "class"],
    });
    return { html, ok: true };
  } catch (e) {
    console.warn("Markdown render error -> fallback to escaped text:", e);
    return { html: `<p>${escapeHtml(md)}</p>`, ok: false };
  }
}

export default function ResponseDisplay({
  messages,
  loading,
  onSelectThinking,
  thinkingEnabled,
  onSelectCitation,
}: Props) {
  const [libsReady, setLibsReady] = useState(
    !!(window.marked && window.DOMPurify)
  );
  const lastGood = useRef<string[]>([]);

  useEffect(() => {
    if (!libsReady) {
      const id = window.setInterval(() => {
        if (window.marked && window.DOMPurify) {
          setLibsReady(true);
          window.clearInterval(id);
        }
      }, 100);
      return () => window.clearInterval(id);
    }
  }, [libsReady]);

  const htmlMsgs = useMemo(() => {
    return messages.map((m, i) => {
      const { html, ok } = renderMarkdown(m.text);
      if (ok) {
        lastGood.current[i] = html;
        return { ...m, __html: html };
      }
      // fallback: keep last good to avoid flicker back to plain text
      return { ...m, __html: lastGood.current[i] ?? html };
    });
  }, [messages, libsReady]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-3">
      {htmlMsgs.map((m: any, i) => (
        <div
          key={i}
          onClick={
            thinkingEnabled && m.sender === "bot"
              ? () => onSelectThinking(m.think || "")
              : undefined
          }
          className={`max-w-xl px-4 py-3 rounded-2xl shadow-md ${
            m.sender === "user"
              ? "bg-[#b52230] text-white self-end ml-auto"
              : "bg-gray-100 text-gray-900" +
                (thinkingEnabled ? " cursor-pointer" : "")
          }`}
        >
          <div
            className={`chat-markdown ${
              m.sender === "user" ? "prose-invert" : ""
            }`}
            dangerouslySetInnerHTML={{ __html: m.__html }}
          />
          {m.sender === "bot" && Array.isArray(m.citations) && m.citations.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {m.citations.map((citation: Citation, idx: number) => (
                <button
                  key={`${citation.docId}-${citation.ord}-${idx}`}
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation()
                    onSelectCitation?.(citation)
                  }}
                  className="citation-badge"
                >
                  <span className="font-semibold">Source {idx + 1}</span>
                  {citation.title && (
                    <span className="ml-1 truncate text-xs text-gray-600">
                      {citation.title}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}

      {loading && (
        <div className="flex justify-center py-2">
          <svg
            className="animate-spin h-6 w-6 text-gray-500"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
            />
          </svg>
        </div>
      )}
    </div>
  );
}
