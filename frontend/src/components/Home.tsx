import { useCallback, useEffect, useMemo, useState } from 'react'

import { useAuth } from '../context/AuthContext'
import logo from '/imgs/logo.png'
import chatbotLogo from '/imgs/chatbot_logo.png'
import QueryInterface from './QueryInterface'
import ResponseDisplay, {
  type Message as DisplayMessage,
  type Citation,
} from './ResponseDisplay'
import ThinkingSidebar from './ThinkingSidebar'
import Navbar from './Navbar'
import SourceSidebar from './SourceSidebar'
import { ErrorBoundary } from './ErrorBoundary'
import Upload from './Upload'
import CrawlJobs from './CrawlJobs'
import Library, { type DocumentRecord } from './Library'

const THINKING_ENABLED = import.meta.env.VITE_ENABLE_MODEL_THINKING === 'true'

const EXAMPLE_PROMPTS = [
  'How do I connect to Eduroam?',
  'Wie erhalte ich eine Microsoft-Lizenz?',
  'How to setup MFA Token?',
]

export default function Home() {
  const { csrfToken, namespaces } = useAuth()
  const [namespaceId, setNamespaceId] = useState<string | null>(null)
  const namespace = useMemo(
    () => namespaces.find((ns) => ns.id === namespaceId) ?? null,
    [namespaces, namespaceId],
  )
  const [activeTab, setActiveTab] = useState<'chat' | 'library'>('chat')
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [think, setThink] = useState('')
  const [showThinking, setShowThinking] = useState(false)
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [docsLoading, setDocsLoading] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [selectedSource, setSelectedSource] = useState<Citation | null>(null)

  useEffect(() => {
    setNamespaceId((prev) => {
      if (prev && namespaces.some((ns) => ns.id === prev)) {
        return prev
      }
      return namespaces[0]?.id ?? null
    })
  }, [namespaces])

  const fetchDocuments = useCallback(async () => {
    if (!namespace) {
      setDocuments([])
      return
    }
    setDocsLoading(true)
    try {
      const res = await fetch(`/api/docs?namespace_id=${namespace.id}`, { credentials: 'include' })
      if (!res.ok) {
        throw new Error(`Failed to load documents (${res.status})`)
      }
      const data = await res.json()
      const rawDocs = Array.isArray(data.documents) ? data.documents : []
      const mapped: DocumentRecord[] = rawDocs
        .map((doc: any) => {
          const chunkCountNumeric = Number(doc.chunk_count)
          const metadata = typeof doc?.metadata === 'object' && doc.metadata !== null ? doc.metadata : null
          return {
            id: String(doc.id ?? ''),
            title: typeof doc.title === 'string' ? doc.title : null,
            status: typeof doc.status === 'string' ? doc.status : 'uploaded',
            contentType: typeof doc.content_type === 'string' ? doc.content_type : 'application/octet-stream',
            createdAt: typeof doc.created_at === 'string' ? doc.created_at : new Date().toISOString(),
            updatedAt: typeof doc.updated_at === 'string' ? doc.updated_at : null,
            error: typeof doc.error === 'string' ? doc.error : null,
            chunkCount: Number.isFinite(chunkCountNumeric) ? chunkCountNumeric : 0,
            metadata,
          }
        })
        .filter((doc) => doc.id)
      setDocuments(mapped)
    } catch (error) {
      console.error('Failed to load documents', error)
    } finally {
      setDocsLoading(false)
    }
  }, [namespace])

  useEffect(() => {
    if (activeTab !== 'library') return
    if (!namespace) {
      setDocuments([])
      return
    }
    void fetchDocuments()
    const interval = window.setInterval(() => {
      void fetchDocuments()
    }, 5000)
    return () => window.clearInterval(interval)
  }, [activeTab, namespace, fetchDocuments])

  useEffect(() => {
    if (activeTab !== 'chat') {
      setShowThinking(false)
      setSelectedSource(null)
    }
  }, [activeTab])

  useEffect(() => {
    setMessages([])
    setConversationId(null)
    setSelectedSource(null)
    setThink('')
  }, [namespaceId])

  const ensureConversation = useCallback(async () => {
    if (!namespace) return null
    if (conversationId) return conversationId

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken
    }

    const payload: Record<string, unknown> = { namespace_id: namespace.id }
    if (conversationId) {
      payload.conversation_id = conversationId
    }

    const res = await fetch('/api/chat/start', {
      method: 'POST',
      headers,
      credentials: 'include',
      body: JSON.stringify(payload),
    })

    if (!res.ok) {
      throw new Error(`Failed to start conversation (${res.status})`)
    }

    const data = await res.json()
    if (typeof data.conversation_id !== 'string' || !data.conversation_id) {
      throw new Error('Invalid conversation response')
    }
    setConversationId(data.conversation_id)
    return data.conversation_id as string
  }, [conversationId, csrfToken, namespace])

  const handleSend = useCallback(
    async (text: string) => {
      if (!text || !namespace) return
      setSelectedSource(null)
      setMessages((m) => [...m, { sender: 'user', text }])
      setLoading(true)
      try {
        const convId = await ensureConversation()
        if (!convId) {
          throw new Error('Missing conversation identifier')
        }

        const params = new URLSearchParams({
          conversation_id: convId,
          namespace_id: namespace.id,
          q: text,
        })

        const res = await fetch(`/api/chat/stream?${params.toString()}`, {
          method: 'GET',
          headers: {
            Accept: 'text/event-stream',
          },
          credentials: 'include',
        })

        if (!res.ok || !res.body) {
          throw new Error(`Chat request failed (${res.status})`)
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        setMessages((m) => [...m, { sender: 'bot', text: '' }])

        let answer = ''
        let buffer = ''
        let live = true
        let citations: Citation[] = []
        let hadError = false

        while (live) {
          const { value, done } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          let idx: number
          while ((idx = buffer.indexOf('\n\n')) !== -1) {
            const frame = buffer.slice(0, idx).trim()
            buffer = buffer.slice(idx + 2)
            if (!frame.startsWith('data:')) continue
            const raw = frame.slice(5).trim()
            if (!raw) continue
            let payload: any
            try {
              payload = JSON.parse(raw)
            } catch (error) {
              console.warn('Failed to parse chat frame', error)
              continue
            }

            if (typeof payload.token === 'string') {
              answer += payload.token
              setMessages((m) => {
                const arr = [...m]
                const last = arr[arr.length - 1]
                if (last && last.sender === 'bot') {
                  arr[arr.length - 1] = { ...last, text: answer }
                }
                return arr
              })
            }

            if (Array.isArray(payload.citations)) {
              citations = payload.citations
                .map((c: any): Citation | null => {
                  if (!c || typeof c.doc_id !== 'string') return null
                  return {
                    docId: c.doc_id,
                    ord: Number(c.ord) || 0,
                    title: typeof c.title === 'string' ? c.title : null,
                    chunkId: typeof c.chunk_id === 'string' ? c.chunk_id : null,
                    text: typeof c.text === 'string' ? c.text : null,
                  }
                })
                .filter((c: Citation | null): c is Citation => Boolean(c))
              setMessages((m) => {
                const arr = [...m]
                const last = arr[arr.length - 1]
                if (last && last.sender === 'bot') {
                  arr[arr.length - 1] = { ...last, citations }
                }
                return arr
              })
            }

            if (payload.error) {
              live = false
              citations = []
              hadError = true
              setMessages((m) => {
                const arr = [...m]
                const last = arr[arr.length - 1]
                if (last && last.sender === 'bot') {
                  arr[arr.length - 1] = {
                    ...last,
                    text: 'The assistant could not generate a response.',
                    citations: [],
                  }
                }
                return arr
              })
              break
            }

            if (payload.done) {
              live = false
              break
            }
          }
        }

        try {
          await reader.cancel()
        } catch (error) {
          console.warn('Failed to cancel reader', error)
        }

        if (!hadError) {
          setMessages((m) => {
            const arr = [...m]
            const last = arr[arr.length - 1]
            if (last && last.sender === 'bot') {
              arr[arr.length - 1] = { ...last, text: answer, citations }
            }
            return arr
          })
        }
      } catch (e) {
        console.error(e)
        setMessages((m) => {
          const arr = [...m]
          const last = arr[arr.length - 1]
          if (last && last.sender === 'bot') {
            arr[arr.length - 1] = {
              ...last,
              text: 'Error contacting server.',
              citations: [],
            }
          } else {
            arr.push({ sender: 'bot', text: 'Error contacting server.' })
          }
          return arr
        })
      } finally {
        setLoading(false)
      }
    },
    [ensureConversation, namespace],
  )

  const handleDelete = useCallback(
    async (id: string) => {
      if (!csrfToken) {
        console.warn('Missing CSRF token for deletion')
        return
      }
      try {
        const res = await fetch(`/api/docs/${id}`, {
          method: 'DELETE',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken,
          },
          body: '{}',
        })
        if (!res.ok) {
          throw new Error(`Failed to delete document (${res.status})`)
        }
        await fetchDocuments()
      } catch (error) {
        console.error('Failed to delete document', error)
      }
    },
    [csrfToken, fetchDocuments],
  )

  const handleRefresh = useCallback(() => {
    void fetchDocuments()
  }, [fetchDocuments])

  const handleUploadComplete = useCallback(() => {
    void fetchDocuments()
  }, [fetchDocuments])

  const hasConversation = activeTab === 'chat' && messages.length > 0
  const sidebarActive =
    (THINKING_ENABLED && showThinking && activeTab === 'chat') || selectedSource !== null

  return (
    <div className="flex min-h-screen flex-col items-center pt-8 text-gray-800">
      <Navbar
        selectedNamespaceId={namespaceId}
        onNamespaceChange={(id) => {
          setNamespaceId(id || null)
        }}
      />
      <header className="mb-6 flex flex-col items-center gap-2 rounded bg-white px-6 py-4 shadow">
        <div className="flex items-center gap-4">
          <img src={logo} alt="Heidelberg University" className="h-20" />
          <img src={chatbotLogo} alt="Chatbot Logo" className="h-20" />
        </div>
        <h1 className="text-center text-2xl font-semibold">
          IT Chatbot of the Computing Centre of Heidelberg University
        </h1>
      </header>

      <div className="mb-6 flex gap-3">
        <button
          type="button"
          onClick={() => setActiveTab('chat')}
          className={`rounded-full px-5 py-2 text-sm font-medium transition ${
            activeTab === 'chat'
              ? 'bg-[#b52230] text-white shadow'
              : 'bg-white/80 text-gray-600 shadow hover:bg-white'
          }`}
        >
          Chat
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('library')}
          className={`rounded-full px-5 py-2 text-sm font-medium transition ${
            activeTab === 'library'
              ? 'bg-[#b52230] text-white shadow'
              : 'bg-white/80 text-gray-600 shadow hover:bg-white'
          }`}
        >
          Library
        </button>
      </div>

      {activeTab === 'chat' ? (
        <div
          className={`chat-container ${
            sidebarActive ? 'sidebar-open' : ''
          } w-full sm:max-w-xl md:max-w-3xl lg:max-w-4xl xl:max-w-5xl 2xl:max-w-6xl mx-auto px-4`}
        >
          {hasConversation && (
            <div className="chat-panel mb-4 flex h-[70vh] w-full flex-col rounded-xl bg-white shadow-lg">
              <ErrorBoundary>
                <ResponseDisplay
                  messages={messages}
                  loading={loading}
                  onSelectThinking={(t) => {
                    if (THINKING_ENABLED) {
                      setThink(t)
                      setShowThinking(true)
                    }
                  }}
                  thinkingEnabled={THINKING_ENABLED}
                  onSelectCitation={(citation) => {
                    setSelectedSource(citation)
                  }}
                />
              </ErrorBoundary>
            </div>
          )}

          {!hasConversation && (
            <section className="mb-4 w-full">
              <div className="mx-auto max-w-2xl rounded-2xl bg-white/85 p-6 shadow-lg backdrop-blur">
                <div className="mb-4 text-center text-lg font-bold text-gray-600">Modell: gpt-oss-20b</div>
                <div className="mb-3 flex items-center gap-2 text-gray-500">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5 text-yellow-500">
                    <path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" />
                  </svg>
                  <span className="font-medium">Vorgeschlagen</span>
                </div>
                <div className="space-y-3">
                  {EXAMPLE_PROMPTS.map((p) => (
                    <button
                      key={p}
                      onClick={() => handleSend(p)}
                      className="w-full rounded-xl bg-[#b52230] p-4 text-left text-white shadow ring-1 ring-[#b52230]/30 transition hover:bg-[#9f1e2a]"
                    >
                      {p}
                    </button>
                  ))}
                </div>
                <div className="mt-4">
                  <QueryInterface onSend={handleSend} placeholder="Wie kann ich Dir helfen?" autoFocus />
                </div>
              </div>
            </section>
          )}

          {hasConversation && (
            <QueryInterface onSend={handleSend} placeholder="Weiter fragen …" autoFocus={false} />
          )}

          {selectedSource ? (
            <SourceSidebar
              citation={selectedSource}
              onClose={() => setSelectedSource(null)}
            />
          ) : (
            THINKING_ENABLED && showThinking && <ThinkingSidebar think={think} />
          )}
        </div>
      ) : (
        <div className="w-full sm:max-w-xl md:max-w-3xl lg:max-w-4xl xl:max-w-5xl 2xl:max-w-6xl px-4">
          {namespace ? (
            <div className="mx-auto flex flex-col gap-6">
              <Upload namespaceId={namespace.id} csrfToken={csrfToken} onUploaded={handleUploadComplete} />
              <CrawlJobs namespaceId={namespace.id} csrfToken={csrfToken} />
              <Library documents={documents} loading={docsLoading} onRefresh={handleRefresh} onDelete={handleDelete} />
            </div>
          ) : (
            <div className="rounded-2xl bg-white/90 p-6 text-center text-sm text-gray-600 shadow">
              You do not have access to a namespace yet. Contact your administrator to get started.
            </div>
          )}
        </div>
      )}

      {THINKING_ENABLED && activeTab === 'chat' && (
        <button
          onClick={() => setShowThinking(!showThinking)}
          className="mt-4 rounded-full bg-blue-600 px-6 py-2 text-white hover:bg-blue-700"
        >
          {showThinking ? 'Hide Thinking' : 'Show Thinking'}
        </button>
      )}
    </div>
  )
}
