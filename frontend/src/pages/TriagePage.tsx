import { AlertCircle, Bot, Loader2, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { getAsyncTriageStatus, startAsyncTriage } from '../api/client'
import { cn } from '../lib/utils'
import TriageResultCard from '../components/TriageResultCard'
import type { TriagePageProps, TriageResult } from '../types'

interface TriageFormState {
  subject: string
  description: string
  manualQueue: string
  manualCategory: string
}

const initialFormState: TriageFormState = {
  subject: '',
  description: '',
  manualQueue: '',
  manualCategory: '',
}

const queueOptions = [
  'STACK Service Desk',
  'Enterprise Apps',
  'Infra & Network',
  'End User Computing',
  'Other Queues',
]

const categoryOptions = [
  'Access Management',
  'Enterprise Platform',
  'Network Services',
  'Endpoint Support',
  'General Incident',
]

const inferRouting = (confidence: number): TriageResult['routing'] => {
  if (confidence >= 0.85) return 'auto-resolved'
  if (confidence >= 0.6) return 'routed'
  return 'escalated'
}

const toResultModel = (payload: Record<string, unknown>, overrides: TriageFormState): TriageResult => {
  const confidence = typeof payload.confidence === 'number' ? payload.confidence : 0.7
  return {
    queue: overrides.manualQueue || String(payload.queue ?? 'STACK Service Desk'),
    category: overrides.manualCategory || String(payload.category ?? 'General Incident'),
    sub_category: String(payload.sub_category ?? 'General'),
    resolution_steps: Array.isArray(payload.resolution_steps)
      ? payload.resolution_steps.map((step) => String(step))
      : ['Validate incident details', 'Execute SOP workflow', 'Confirm resolution with requester'],
    confidence,
    sop_reference: String(payload.sop_reference ?? 'SOP-STACK-100'),
    reasoning: String(payload.reasoning ?? 'Routing selected based on issue pattern confidence.'),
    routing: inferRouting(confidence),
    timestamp: new Date().toISOString(),
  }
}

const TriageResultSkeleton = () => (
  <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:shadow-none">
    <div className="mb-4 h-6 w-40 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
    <div className="mb-4 h-28 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-700/60" />
    <div className="mb-4 grid gap-2">
      <div className="h-4 w-full animate-pulse rounded bg-slate-100 dark:bg-slate-700/60" />
      <div className="h-4 w-11/12 animate-pulse rounded bg-slate-100 dark:bg-slate-700/60" />
      <div className="h-4 w-4/5 animate-pulse rounded bg-slate-100 dark:bg-slate-700/60" />
    </div>
    <div className="h-10 w-44 animate-pulse rounded-lg bg-slate-200 dark:bg-slate-700" />
  </div>
)

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export const TriagePage = ({ onTriageSaved }: TriagePageProps) => {
  const [formState, setFormState] = useState<TriageFormState>(initialFormState)
  const [result, setResult] = useState<TriageResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [actionMessage, setActionMessage] = useState('')

  const handleAnalyze = async () => {
    if (!formState.subject.trim() || !formState.description.trim()) {
      setError('Subject and description are required before analysis.')
      return
    }

    setIsLoading(true)
    setError('')
    setActionMessage('')

    try {
      const startResponse = await startAsyncTriage({
        subject: formState.subject,
        description: formState.description,
      })
      const jobId = String(startResponse?.job_id ?? '')
      if (!jobId) {
        throw new Error('Invalid async triage job id.')
      }

      let finalPayload: Record<string, unknown> | null = null
      for (let attempt = 0; attempt < 60; attempt += 1) {
        const statusResponse = await getAsyncTriageStatus(jobId)
        const jobStatus = String(statusResponse?.status ?? '')
        if (jobStatus === 'completed') {
          finalPayload = (statusResponse?.result ?? null) as Record<string, unknown> | null
          break
        }
        if (jobStatus === 'failed') {
          throw new Error(String(statusResponse?.error ?? 'Async triage job failed.'))
        }
        await wait(1500)
      }

      if (!finalPayload) {
        throw new Error('Triage still processing. Please retry in a moment.')
      }

      const normalized = toResultModel(finalPayload, formState)
      setResult(normalized)
      onTriageSaved?.(normalized)
    } catch (analysisError) {
      setError(analysisError instanceof Error ? analysisError.message : 'Unable to analyze ticket.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <section className="grid grid-cols-1 gap-6 xl:grid-cols-5">
      <article className="xl:col-span-2 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:shadow-none">
        <header className="mb-5">
          <h2 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            Ticket Submission
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Enter ticket details to run real-time AI triage.
          </p>
        </header>

        <div className="space-y-4">
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-200">Subject</span>
            <input
              type="text"
              value={formState.subject}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, subject: event.target.value }))
              }
              placeholder="Brief incident summary"
              className="h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm text-slate-900 outline-none transition-all duration-200 focus:border-brand-jade focus:bg-white dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:bg-slate-900"
            />
          </label>

          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-200">
              Description
            </span>
            <textarea
              rows={6}
              value={formState.description}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, description: event.target.value }))
              }
              placeholder="Provide detailed context, impact, and observed errors."
              className="w-full resize-y rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 outline-none transition-all duration-200 focus:border-brand-jade focus:bg-white dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:bg-slate-900"
            />
          </label>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-200">
                Queue Override
              </span>
              <select
                value={formState.manualQueue}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, manualQueue: event.target.value }))
                }
                className="h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm text-slate-900 outline-none transition-all duration-200 focus:border-brand-jade focus:bg-white dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:bg-slate-900"
              >
                <option value="">AI Suggested</option>
                {queueOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-200">
                Category Override
              </span>
              <select
                value={formState.manualCategory}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, manualCategory: event.target.value }))
                }
                className="h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm text-slate-900 outline-none transition-all duration-200 focus:border-brand-jade focus:bg-white dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:bg-slate-900"
              >
                <option value="">AI Suggested</option>
                {categoryOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {error && (
            <div className="inline-flex w-full items-center gap-2 rounded-lg border border-danger-red/30 bg-danger-red/10 px-3 py-2 text-sm text-danger-red">
              <AlertCircle className="h-4 w-4" />
              {error}
            </div>
          )}

          <button
            type="button"
            onClick={handleAnalyze}
            disabled={isLoading}
            className={cn(
              'inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-brand-jade px-4 text-sm font-semibold text-white transition-all duration-200 hover:bg-brand-jade-light disabled:cursor-not-allowed disabled:opacity-70',
            )}
          >
            {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Analyze Ticket
          </button>
        </div>
      </article>

      <article className="xl:col-span-3 space-y-4">
        {isLoading && <TriageResultSkeleton />}

        {!isLoading && result && (
          <>
            <TriageResultCard
              result={result}
              onAccept={() => setActionMessage('Feature coming soon.')}
              onOverride={() => setActionMessage('AI-generated solution is now visible below.')}
              onEscalate={() => setActionMessage('Feature coming soon.')}
            />
            {actionMessage && (
              <div className="rounded-lg border border-brand-jade/30 bg-brand-jade-muted px-4 py-2 text-sm text-brand-jade dark:bg-brand-jade/15 dark:text-brand-jade-light">
                {actionMessage}
              </div>
            )}
          </>
        )}

        {!isLoading && !result && (
          <div className="flex min-h-[360px] flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center dark:border-slate-600 dark:bg-slate-800">
            <span className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-brand-jade-muted text-brand-jade dark:bg-brand-jade/15 dark:text-brand-jade-light">
              <Bot className="h-6 w-6" />
            </span>
            <h3 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-100">
              AI Result Panel
            </h3>
            <p className="mt-1 max-w-md text-sm text-slate-500 dark:text-slate-400">
              Submit a ticket to view confidence score, queue recommendation, SOP reference, and resolution steps.
            </p>
          </div>
        )}
      </article>
    </section>
  )
}

export default TriagePage
