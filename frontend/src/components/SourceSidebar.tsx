import type { Citation } from './ResponseDisplay'

type Props = {
  citation: Citation
  onClose: () => void
}

export default function SourceSidebar({ citation, onClose }: Props) {
  const ordinal = Number.isFinite(citation.ord) ? citation.ord + 1 : citation.ord
  return (
    <section
      className="mt-6 w-full"
      role="complementary"
      aria-label="Source details"
    >
      <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg font-semibold text-gray-800">Source Details</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full bg-gray-200 px-3 py-1 text-sm text-gray-700 transition hover:bg-gray-300"
          >
            Close
          </button>
        </div>
        <div className="space-y-3 text-sm text-gray-700">
          <div>
            <span className="font-semibold text-gray-900">Title:</span>{' '}
            <span>{citation.title || 'Untitled document'}</span>
          </div>
          <div className="break-all text-xs text-gray-500">
            <span className="font-semibold text-gray-700">Document ID:</span>{' '}
            {citation.docId}
          </div>
          {ordinal !== null && ordinal !== undefined && (
            <div className="text-xs text-gray-500">
              <span className="font-semibold text-gray-700">Section:</span>{' '}
              {ordinal}
            </div>
          )}
        </div>
        {citation.text && (
          <div className="mt-5 max-h-80 overflow-y-auto rounded-xl bg-gray-50 p-4 text-sm">
            <pre className="whitespace-pre-wrap font-sans text-gray-800">{citation.text}</pre>
          </div>
        )}
      </div>
    </section>
  )
}
