import { type FormEvent, useCallback, useEffect, useMemo, useState } from 'react'

import { apiUrl } from '../utils/api'

type CrawlJobsProps = {
  namespaceId: string
  csrfToken: string | null
}

type CrawlJob = {
  id: string
  namespaceId: string
  status: string
  url: string
  depth: number
  totalCount: number
  harvestedCount: number
  failedCount: number
  blockedCount: number
  skippedCount: number
  createdAt: string
  updatedAt: string | null
  error: string | null
}

type CrawlResult = {
  id: string
  url: string
  depth: number
  status: string
  contentType: string | null
  documentId: string | null
  error: string | null
  createdAt: string
}

const STATUS_LABELS: Record<string, string> = {
  queued: 'Queued',
  running: 'Running',
  succeeded: 'Succeeded',
  failed: 'Failed',
}

const STATUS_STYLES: Record<string, string> = {
  queued: 'bg-amber-100 text-amber-700',
  running: 'bg-blue-100 text-blue-700',
  succeeded: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
}

const RESULT_STYLES: Record<string, string> = {
  harvested: 'text-green-700',
  failed: 'text-red-700',
  blocked: 'text-amber-700',
  skipped: 'text-gray-500',
}

export default function CrawlJobs({ namespaceId, csrfToken }: CrawlJobsProps) {
  const [rootUrl, setRootUrl] = useState('')
  const [depth, setDepth] = useState(2)
  const [jobs, setJobs] = useState<CrawlJob[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [results, setResults] = useState<Record<string, CrawlResult[]>>({})
  const [detailsLoading, setDetailsLoading] = useState(false)

  const formatter = useMemo(
    () => new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }),
    [],
  )

  const fetchJobs = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(apiUrl(`/api/crawl/jobs?namespace_id=${namespaceId}`), { credentials: 'include' })
      if (!res.ok) {
        throw new Error(`Failed to load crawl jobs (${res.status})`)
      }
      const data = await res.json()
      const mapped: CrawlJob[] = Array.isArray(data?.jobs)
        ? data.jobs
            .map((job: any) => ({
              id: String(job?.id ?? ''),
              namespaceId: String(job?.namespace_id ?? namespaceId),
              status: String(job?.status ?? 'queued'),
              url: String(job?.url ?? ''),
              depth: Number(job?.depth ?? 0),
              totalCount: Number(job?.total_count ?? 0),
              harvestedCount: Number(job?.harvested_count ?? 0),
              failedCount: Number(job?.failed_count ?? 0),
              blockedCount: Number(job?.blocked_count ?? 0),
              skippedCount: Number(job?.skipped_count ?? 0),
              createdAt: String(job?.created_at ?? new Date().toISOString()),
              updatedAt: job?.updated_at ? String(job.updated_at) : null,
              error: job?.error ? String(job.error) : null,
            }))
            .filter((job: CrawlJob) => Boolean(job.id))
        : []
      setJobs(mapped)
    } catch (err) {
      console.error(err)
      setJobs([])
    } finally {
      setLoading(false)
    }
  }, [namespaceId])

  const fetchDetails = useCallback(
    async (jobId: string) => {
      setDetailsLoading(true)
      try {
        const res = await fetch(apiUrl(`/api/crawl/${jobId}`), { credentials: 'include' })
        if (!res.ok) {
          throw new Error(`Failed to load crawl job details (${res.status})`)
        }
        const data = await res.json()
        const rawResults = Array.isArray(data?.results) ? data.results : []
        const mapped: CrawlResult[] = rawResults
          .map((item: any) => ({
            id: String(item?.id ?? ''),
            url: String(item?.url ?? ''),
            depth: Number(item?.depth ?? 0),
            status: String(item?.status ?? 'skipped'),
            contentType: item?.content_type ? String(item.content_type) : null,
            documentId: item?.document_id ? String(item.document_id) : null,
            error: item?.error ? String(item.error) : null,
            createdAt: String(item?.created_at ?? new Date().toISOString()),
          }))
          .filter((item: CrawlResult) => Boolean(item.id))
        setResults((prev) => ({ ...prev, [jobId]: mapped }))
      } catch (err) {
        console.error(err)
        setResults((prev) => ({ ...prev, [jobId]: [] }))
      } finally {
        setDetailsLoading(false)
      }
    },
    [],
  )

  useEffect(() => {
    void fetchJobs()
    const interval = window.setInterval(() => {
      void fetchJobs()
    }, 5000)
    return () => window.clearInterval(interval)
  }, [fetchJobs])

  useEffect(() => {
    if (selectedJobId && !results[selectedJobId]) {
      void fetchDetails(selectedJobId)
    }
  }, [selectedJobId, results, fetchDetails])

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      if (!csrfToken) {
        setError('Missing CSRF token, please refresh the page and try again.')
        return
      }
      if (!rootUrl.trim()) {
        setError('Please enter a valid URL.')
        return
      }
      setSubmitting(true)
      setError(null)
      try {
        const res = await fetch(apiUrl('/api/crawl/start'), {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken,
          },
          body: JSON.stringify({
            url: rootUrl.trim(),
            depth,
            namespace_id: namespaceId,
          }),
        })
        if (!res.ok) {
          const payload = await res.json().catch(() => ({}))
          const detail = typeof payload?.detail === 'string' ? payload.detail : `Failed to start crawl (${res.status})`
          throw new Error(detail)
        }
        setRootUrl('')
        setDepth(2)
        await fetchJobs()
      } catch (err: any) {
        const message = err?.message ?? 'Failed to start crawl'
        setError(message)
      } finally {
        setSubmitting(false)
      }
    },
    [csrfToken, rootUrl, depth, namespaceId, fetchJobs],
  )

  return (
    <section className="rounded-2xl bg-white/90 p-6 shadow">
      <header className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-800">Website crawler</h2>
          <p className="text-sm text-gray-500">Harvest documentation pages and ingest them automatically.</p>
        </div>
      </header>

      <form onSubmit={handleSubmit} className="mb-6 flex flex-col gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <label className="flex flex-col gap-1 text-sm text-gray-700">
          Start URL
          <input
            type="url"
            value={rootUrl}
            onChange={(event) => setRootUrl(event.target.value)}
            placeholder="https://example.com/docs"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#b52230] focus:outline-none focus:ring-2 focus:ring-[#b52230]/30"
            required
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-gray-700 sm:max-w-xs">
          Depth
          <select
            value={depth}
            onChange={(event) => setDepth(Number(event.target.value))}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#b52230] focus:outline-none focus:ring-2 focus:ring-[#b52230]/30"
          >
            {[0, 1, 2, 3].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div>
          <button
            type="submit"
            className="rounded-full bg-[#b52230] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#9f1e2a] disabled:opacity-60"
            disabled={submitting}
          >
            {submitting ? 'Starting…' : 'Start crawl'}
          </button>
        </div>
      </form>

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 text-sm text-gray-700">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium">URL</th>
              <th className="px-3 py-2 text-left font-medium">Status</th>
              <th className="px-3 py-2 text-left font-medium">Depth</th>
              <th className="px-3 py-2 text-left font-medium">Harvested</th>
              <th className="px-3 py-2 text-left font-medium">Failed</th>
              <th className="px-3 py-2 text-left font-medium">Blocked</th>
              <th className="px-3 py-2 text-left font-medium">Skipped</th>
              <th className="px-3 py-2 text-left font-medium">Updated</th>
              <th className="px-3 py-2 text-left font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {jobs.map((job) => {
              const statusKey = job.status.toLowerCase()
              const label = STATUS_LABELS[statusKey] ?? job.status
              const badgeClass = STATUS_STYLES[statusKey] ?? 'bg-gray-100 text-gray-600'
              const updated = job.updatedAt || job.createdAt
              return (
                <tr key={job.id} className="hover:bg-gray-50">
                  <td className="px-3 py-3">
                    <div className="flex flex-col">
                      <span className="font-medium text-gray-800 break-all">{job.url}</span>
                      <span className="text-xs text-gray-500">{formatter.format(new Date(job.createdAt))}</span>
                      {job.error && <span className="text-xs text-red-600">{job.error}</span>}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${badgeClass}`}>
                      {label}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-sm text-gray-600">{job.depth}</td>
                  <td className="px-3 py-3 text-sm text-gray-600">{job.harvestedCount} / {job.totalCount}</td>
                  <td className="px-3 py-3 text-sm text-gray-600">{job.failedCount}</td>
                  <td className="px-3 py-3 text-sm text-gray-600">{job.blockedCount}</td>
                  <td className="px-3 py-3 text-sm text-gray-600">{job.skippedCount}</td>
                  <td className="px-3 py-3 text-sm text-gray-600">{formatter.format(new Date(updated))}</td>
                  <td className="px-3 py-3">
                    <button
                      type="button"
                      className="rounded-full border border-blue-300 px-3 py-1 text-xs font-medium text-blue-600 transition hover:bg-blue-600 hover:text-white disabled:opacity-50"
                      onClick={() => {
                        setSelectedJobId(job.id)
                        if (!results[job.id]) {
                          void fetchDetails(job.id)
                        }
                      }}
                      disabled={detailsLoading && selectedJobId === job.id}
                    >
                      View
                    </button>
                  </td>
                </tr>
              )
            })}
            {jobs.length === 0 && !loading && (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center text-sm text-gray-500">
                  No crawl jobs yet. Start one above to ingest a documentation site.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {loading && <div className="mt-4 text-center text-sm text-gray-500">Loading crawl jobs…</div>}

      {selectedJobId && (
        <div className="mt-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-700">Harvested URLs</h3>
            <button
              type="button"
              className="text-xs font-medium text-[#b52230] hover:underline"
              onClick={() => setSelectedJobId(null)}
            >
              Close
            </button>
          </div>
          {detailsLoading && (!results[selectedJobId] || results[selectedJobId]!.length === 0) && (
            <div className="text-sm text-gray-500">Loading details…</div>
          )}
          {results[selectedJobId] && results[selectedJobId]!.length > 0 ? (
            <ul className="space-y-2 text-sm">
              {results[selectedJobId]!.map((item) => {
                const style = RESULT_STYLES[item.status.toLowerCase()] ?? 'text-gray-600'
                return (
                  <li key={item.id} className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                    <div className={`font-medium ${style} break-all`}>{item.url}</div>
                    <div className="mt-1 flex flex-wrap gap-3 text-xs text-gray-500">
                      <span>Depth: {item.depth}</span>
                      <span>Status: {item.status}</span>
                      {item.contentType && <span>{item.contentType}</span>}
                      <span>Captured: {formatter.format(new Date(item.createdAt))}</span>
                      {item.documentId && <span>Document ID: {item.documentId}</span>}
                      {item.error && <span className="text-red-600">{item.error}</span>}
                    </div>
                  </li>
                )
              })}
            </ul>
          ) : (
            !detailsLoading && (
              <div className="text-sm text-gray-500">No harvested URLs yet.</div>
            )
          )}
        </div>
      )}
    </section>
  )
}
