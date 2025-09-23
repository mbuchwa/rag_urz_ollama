import { type DragEvent, useCallback, useRef, useState } from 'react'

type UploadProps = {
  namespaceId: string | null
  csrfToken: string | null
  onUploaded?: () => void
}

type UploadState = 'idle' | 'uploading' | 'success' | 'error'

function uploadFile(url: string, file: File, onProgress: (percentage: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url)
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      const percentage = Math.round((event.loaded / event.total) * 100)
      onProgress(percentage)
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(100)
        resolve()
      } else {
        reject(new Error(`Upload failed with status ${xhr.status}`))
      }
    }
    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream')
    xhr.send(file)
  })
}

export default function Upload({ namespaceId, csrfToken, onUploaded }: UploadProps) {
  const [uploadState, setUploadState] = useState<UploadState>('idle')
  const [progress, setProgress] = useState(0)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const reset = useCallback(() => {
    setUploadState('idle')
    setProgress(0)
    setMessage(null)
    setError(null)
    if (inputRef.current) {
      inputRef.current.value = ''
    }
  }, [])

  const handleUpload = useCallback(
    async (file: File) => {
      if (!namespaceId) {
        setError('No namespace available for upload.')
        return
      }
      if (!csrfToken) {
        setError('Missing CSRF token. Please refresh the page.')
        return
      }

      setUploadState('uploading')
      setProgress(0)
      setMessage(null)
      setError(null)

      try {
        const initRes = await fetch('/api/docs/upload-init', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken,
          },
          body: JSON.stringify({
            namespace_id: namespaceId,
            filename: file.name,
            content_type: file.type || undefined,
          }),
        })

        if (!initRes.ok) {
          throw new Error(`Failed to initialize upload (${initRes.status})`)
        }

        const initData = await initRes.json()
        const uploadUrl = initData.upload_url as string
        const documentId = initData.document_id as string
        if (!uploadUrl || !documentId) {
          throw new Error('Upload initialization missing required fields.')
        }

        await uploadFile(uploadUrl, file, setProgress)

        const completeRes = await fetch('/api/docs/complete', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken,
          },
          body: JSON.stringify({
            document_id: documentId,
            namespace_id: namespaceId,
            metadata: {
              original_filename: file.name,
            },
          }),
        })

        if (!completeRes.ok) {
          throw new Error(`Failed to finalize upload (${completeRes.status})`)
        }

        setUploadState('success')
        setMessage('Upload complete. The document is being processed.')
        if (onUploaded) onUploaded()
      } catch (err) {
        console.error(err)
        setUploadState('error')
        setError(err instanceof Error ? err.message : 'Unknown upload error')
      }
    },
    [csrfToken, namespaceId, onUploaded],
  )

  const handleFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0]
      if (!file) return
      void handleUpload(file)
    },
    [handleUpload],
  )

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault()
      handleFiles(event.dataTransfer.files)
    },
    [handleFiles],
  )

  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
  }, [])

  const disabled = uploadState === 'uploading'

  return (
    <section className="rounded-2xl bg-white/90 p-6 shadow">
      <header className="mb-4">
        <h2 className="text-lg font-semibold text-gray-800">Upload document</h2>
        <p className="text-sm text-gray-500">Drag & drop a PDF, DOCX, or HTML file, or click to browse.</p>
      </header>
      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center transition ${
          disabled ? 'cursor-not-allowed border-gray-300 bg-gray-100' : 'cursor-pointer border-[#b52230]/50 bg-white'
        }`}
        onClick={() => {
          if (disabled) return
          inputRef.current?.click()
        }}
      >
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          onChange={(event) => handleFiles(event.target.files)}
          accept=".pdf,.doc,.docx,.html,.htm,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/html"
          disabled={disabled}
        />
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          className="mb-3 h-12 w-12 text-[#b52230]"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5V19.5C3 20.8807 4.11929 22 5.5 22H18.5C19.8807 22 21 20.8807 21 19.5V16.5M7 10L12 5L17 10M12 5V16"
          />
        </svg>
        <p className="text-sm text-gray-600">
          <span className="font-medium text-[#b52230]">Click to upload</span> or drag and drop a file
        </p>
        <p className="text-xs text-gray-500">Supports PDF, DOCX, and HTML files up to 10MB.</p>
      </div>

      {uploadState === 'uploading' && (
        <div className="mt-4">
          <div className="flex items-center justify-between text-sm text-gray-600">
            <span>Uploading…</span>
            <span>{progress}%</span>
          </div>
          <div className="mt-2 h-2 w-full rounded-full bg-gray-200">
            <div className="h-2 rounded-full bg-[#b52230] transition-all" style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}

      {message && (
        <div className="mt-4 rounded-lg bg-green-50 px-4 py-3 text-sm text-green-700">{message}</div>
      )}

      {error && (
        <div className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {(uploadState === 'success' || uploadState === 'error') && (
        <button
          type="button"
          className="mt-4 rounded-full bg-[#b52230] px-4 py-2 text-sm font-medium text-white hover:bg-[#9f1e2a]"
          onClick={reset}
        >
          Upload another file
        </button>
      )}
    </section>
  )
}
