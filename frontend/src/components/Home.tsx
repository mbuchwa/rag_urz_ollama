import { useState } from 'react'
import logo from '/imgs/logo.png'
import chatbotLogo from '/imgs/chatbot_logo.png'
import QueryInterface from './QueryInterface'
import ResponseDisplay from './ResponseDisplay'
import ThinkingSidebar from './ThinkingSidebar'
import { ErrorBoundary } from './ErrorBoundary'

const THINKING_ENABLED = import.meta.env.VITE_ENABLE_MODEL_THINKING === 'true'

const EXAMPLE_PROMPTS = [
  'How do I connect to Eduroam?',
  'Wie erhalte ich eine Microsoft-Lizenz?',
  'How to setup MFA Token?',
]

interface Message {
  sender: 'user' | 'bot'
  text: string
  think?: string
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [think, setThink] = useState('')
  const [showThinking, setShowThinking] = useState(false)

  const handleSend = async (text: string) => {
    if (!text) return
    setMessages((m) => [...m, { sender: 'user', text }])
    setLoading(true)
    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
      if (!res.body) throw new Error('No response body')

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      setMessages((m) => [...m, { sender: 'bot', text: '' }])

      let answer = ''
      let buffer = ''
      let live = true
      let lastTick = Date.now()
      const tick = () => Date.now() - lastTick < 30000

      while (live) {
        const { value, done } = await reader.read()
        if (done) break
        lastTick = Date.now()

        buffer += decoder.decode(value, { stream: true })
        let idx: number
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, idx).trim()
          buffer = buffer.slice(idx + 2)
          if (!frame.startsWith('data:')) continue
          const payload = JSON.parse(frame.slice(5).trim())

          if (payload.token) {
            answer += payload.token
            setMessages((m) => {
              const arr = [...m]
              arr[arr.length - 1] = { sender: 'bot', text: answer }
              return arr
            })
          }

          if (payload.think !== undefined) {
            const thinkText = payload.think || ''
            setMessages((m) => {
              const arr = [...m]
              const last = arr[arr.length - 1]
              if (last && last.sender === 'bot') {
                arr[arr.length - 1] = { ...last, think: thinkText }
              }
              return arr
            })
          }

          if (payload.done) {
            live = false
            try { await reader.cancel() } catch {}
            break
          }
        }

        if (!tick()) break
      }
    } catch (e) {
      console.error(e)
      setMessages((m) => [...m, { sender: 'bot', text: 'Error contacting server.' }])
    } finally {
      setLoading(false)
    }
  }

  const hasConversation = messages.length > 0

  return (
    <div className="flex flex-col items-center min-h-screen pt-8 text-gray-800">
      {/* Header */}
      <header className="flex flex-col items-center gap-2 mb-6 bg-white px-6 py-4 rounded shadow">
        <div className="flex items-center gap-4">
          <img src={logo} alt="Heidelberg University" className="h-20" />
          <img src={chatbotLogo} alt="Chatbot Logo" className="h-20" />
        </div>
        <h1 className="text-2xl font-semibold text-center">
          IT Chatbot of the Computing Centre of Heidelberg University
        </h1>
      </header>

      <div
        className={`chat-container ${THINKING_ENABLED && showThinking ? 'sidebar-open' : ''} w-full sm:max-w-xl md:max-w-3xl lg:max-w-4xl xl:max-w-5xl 2xl:max-w-6xl mx-auto px-4`}
      >
        {/* Chat panel after first prompt */}
        {hasConversation && (
          <div className="chat-panel flex flex-col h-[70vh] shadow-lg bg-white rounded-xl w-full mb-4">
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
              />
            </ErrorBoundary>
          </div>
        )}

        {/* PRE-CHAT • put everything on a soft card for contrast */}
        {!hasConversation && (
          <section className="w-full mb-4">
            <div className="mx-auto max-w-2xl rounded-2xl bg-white/85 backdrop-blur p-6 shadow-lg">
              {/* Model name */}
              <div className="text-center text-lg font-bold text-gray-600 mb-4">
                Modell: gpt-oss-20b
              </div>

              {/* Vorgeschlagen header */}
              <div className="flex items-center gap-2 text-gray-500 mb-3">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5 text-yellow-500">
                  <path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" />
                </svg>
                <span className="font-medium">Vorgeschlagen</span>
              </div>

              {/* Example prompts in brand red */}
              <div className="space-y-3">
                {EXAMPLE_PROMPTS.map((p) => (
                  <button
                    key={p}
                    onClick={() => handleSend(p)}
                    className="w-full p-4 text-left rounded-xl shadow ring-1 ring-[#b52230]/30 bg-[#b52230] text-white hover:bg-[#9f1e2a] transition"
                  >
                    {p}
                  </button>
                ))}
              </div>

              {/* Query bar INSIDE the card pre-chat for cohesion */}
              <div className="mt-4">
                <QueryInterface
                  onSend={handleSend}
                  placeholder="Wie kann ich Dir helfen?"
                  autoFocus
                />
              </div>
            </div>
          </section>
        )}

        {/* After chat starts, keep the query bar anchored under the chat panel */}
        {hasConversation && (
          <QueryInterface
            onSend={handleSend}
            placeholder="Weiter fragen …"
            autoFocus={false}
          />
        )}

        {THINKING_ENABLED && showThinking && <ThinkingSidebar think={think} />}
      </div>

      {THINKING_ENABLED && (
        <button
          onClick={() => setShowThinking(!showThinking)}
          className="mt-4 bg-blue-600 text-white px-6 py-2 rounded-full hover:bg-blue-700"
        >
          {showThinking ? 'Hide Thinking' : 'Show Thinking'}
        </button>
      )}
    </div>
  )
}
