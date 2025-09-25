import { useMemo } from 'react'

export type DocumentRecord = {
  id: string
  title: string | null
  status: string
  contentType: string
  createdAt: string
  updatedAt: string | null
  error: string | null
  chunkCount: number
  metadata: Record<string, any> | null
}

type LibraryProps = {
  documents: DocumentRecord[]
  loading: boolean
  onRefresh: () => void
  onDelete: (id: string) => void
  onDeleteAll: () => void
}

const STATUS_LABELS: Record<string, string> = {
  uploading: 'Uploading',
  uploaded: 'Uploaded',
  processing: 'Processing',
  ingested: 'Ingested',
  failed: 'Failed',
  deleted: 'Deleted',
}

const STATUS_STYLES: Record<string, string> = {
  uploading: 'bg-blue-100 text-blue-700',
  uploaded: 'bg-amber-100 text-amber-700',
  processing: 'bg-indigo-100 text-indigo-700',
  ingested: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  deleted: 'bg-gray-200 text-gray-600',
}

export default function Library({ documents, loading, onRefresh, onDelete, onDeleteAll }: LibraryProps) {
  const formatter = useMemo(() => new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }), [])

  return (
    <section className="rounded-2xl bg-white/90 p-6 shadow">
      <header className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-800">Document library</h2>
          <p className="text-sm text-gray-500">Monitor ingestion status and manage uploaded documents.</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            onClick={onDeleteAll}
            className="self-start rounded-full border border-red-300 px-4 py-2 text-sm font-medium text-red-600 transition hover:bg-red-600 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
            disabled={loading || documents.length === 0}
          >
            Empty documents
          </button>
          <button
            type="button"
            onClick={onRefresh}
            className="self-start rounded-full border border-[#b52230] px-4 py-2 text-sm font-medium text-[#b52230] transition hover:bg-[#b52230] hover:text-white disabled:opacity-60"
            disabled={loading}
          >
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      {documents.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 bg-white px-4 py-10 text-center text-sm text-gray-500">
          <p>No documents uploaded yet. Use the uploader above to ingest your first document.</p>
          {loading && <p className="mt-3 text-xs text-gray-400">Refreshing…</p>}
        </div>
      )}

      {documents.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 text-sm text-gray-700">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Title</th>
                <th className="px-3 py-2 text-left font-medium">Status</th>
                <th className="px-3 py-2 text-left font-medium">Chunks</th>
                <th className="px-3 py-2 text-left font-medium">Updated</th>
                <th className="px-3 py-2 text-left font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {documents.map((doc) => {
                const status = doc.status.toLowerCase()
                const label = STATUS_LABELS[status] ?? doc.status
                const badgeClass = STATUS_STYLES[status] ?? 'bg-gray-100 text-gray-600'
                const filename = doc.title || doc.metadata?.original_filename || doc.id
                const updated = doc.updatedAt || doc.createdAt
                return (
                  <tr key={doc.id} className="hover:bg-gray-50">
                    <td className="px-3 py-3">
                      <div className="flex flex-col">
                        <span className="font-medium text-gray-800">{filename}</span>
                        <span className="text-xs text-gray-500">{doc.contentType}</span>
                        {doc.error && <span className="text-xs text-red-600">{doc.error}</span>}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${badgeClass}`}>
                        {label}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-sm text-gray-600">{doc.chunkCount}</td>
                    <td className="px-3 py-3 text-sm text-gray-600">{formatter.format(new Date(updated))}</td>
                    <td className="px-3 py-3">
                      <button
                        type="button"
                        className="rounded-full border border-red-300 px-3 py-1 text-xs font-medium text-red-600 transition hover:bg-red-600 hover:text-white disabled:opacity-50"
                        onClick={() => onDelete(doc.id)}
                        disabled={status === 'processing' || status === 'uploading'}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {loading && documents.length > 0 && (
        <div className="mt-4 text-center text-sm text-gray-500">Refreshing documents…</div>
      )}
    </section>
  )
}
