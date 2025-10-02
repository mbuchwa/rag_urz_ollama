import { useState, FormEvent, useRef, useEffect } from 'react'

type Props = {
  onSend: (text: string) => void
  placeholder?: string
  autoFocus?: boolean
}

export default function QueryInterface({
  onSend,
  placeholder = 'Wie kann ich Dir helfen?',
  autoFocus = false,
}: Props) {
  const [value, setValue] = useState('')
  const inputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus()
  }, [autoFocus])

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const text = value.trim()
    if (text) {
      onSend(text)
      setValue('')
    }
  }

  const hasText = value.trim().length > 0

  return (
    <form
      onSubmit={submit}
      className="mt-auto flex w-full gap-2 rounded-b border-t bg-white p-4"
      aria-label="Query interface"
    >
      <div className="relative flex-1">
        {/* search icon */}
        <svg
          className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 pointer-events-none text-gray-400"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="M20 20l-3.5-3.5" />
        </svg>

        <input
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-full pl-10 pr-4 py-3 text-[15px] bg-white shadow-sm ring-1 ring-gray-200 focus:outline-none focus:ring-2 focus:ring-[#b52230] placeholder-gray-400"
        />
      </div>

      <button
        type="submit"
        disabled={!hasText}
        className="px-6 py-3 rounded-full text-white bg-[#b52230] hover:bg-[#9f1e2a] disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
      >
        Send
      </button>
    </form>
  )
}
