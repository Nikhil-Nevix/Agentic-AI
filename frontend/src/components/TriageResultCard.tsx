import { Bot, ChevronDown, ChevronUp, CircleCheck, Clock3, ExternalLink, ListChecks } from 'lucide-react'
import { useMemo, useState } from 'react'
import { cn } from '../lib/utils'
import ConfidenceGauge from './ConfidenceGauge'
import type { TriageResult, TriageResultCardProps, TriageRoutingDecision } from '../types'

const getRoutingFromScore = (score: number): TriageRoutingDecision => {
  if (score >= 0.85) return 'auto-resolved'
  if (score >= 0.6) return 'routed'
  return 'escalated'
}

const routingBadgeClasses: Record<TriageRoutingDecision, string> = {
  'auto-resolved':
    'bg-brand-jade-muted text-brand-jade border border-brand-jade/30 dark:bg-brand-jade/15 dark:text-brand-jade-light dark:border-brand-jade/30',
  routed:
    'bg-amber-50 text-amber-700 border border-amber-200 dark:bg-warning-amber/15 dark:text-amber-300 dark:border-warning-amber/30',
  escalated:
    'bg-red-50 text-red-700 border border-red-200 dark:bg-danger-red/15 dark:text-red-300 dark:border-danger-red/30',
}

const queueBadgeClass = (queue: string) => {
  if (/stack/i.test(queue)) return 'bg-brand-jade-muted text-brand-jade dark:bg-brand-jade/15 dark:text-brand-jade-light'
  if (/enterprise|apps/i.test(queue)) return 'bg-blue-50 text-blue-700 dark:bg-brand-accent/15 dark:text-blue-300'
  if (/infra|network/i.test(queue)) return 'bg-amber-50 text-amber-700 dark:bg-warning-amber/15 dark:text-amber-300'
  return 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200'
}

export const TriageResultCard = ({
  result,
  onAccept,
  onOverride,
  onEscalate,
}: TriageResultCardProps) => {
  const [showAllSteps, setShowAllSteps] = useState(false)
  const [showReasoning, setShowReasoning] = useState(true)
  const [showAISolution, setShowAISolution] = useState(false)
  const routingDecision = result.routing ?? getRoutingFromScore(result.confidence)
  const visibleSteps = showAllSteps ? result.resolution_steps : result.resolution_steps.slice(0, 3)
  const hasMoreSteps = result.resolution_steps.length > 3
  const timestamp = useMemo(
    () => (result.timestamp ? new Date(result.timestamp) : new Date()),
    [result.timestamp],
  )

  return (
    <article className="rounded-xl border border-slate-200 border-l-4 border-l-brand-jade bg-white p-6 shadow-sm dark:border-slate-700 dark:border-l-brand-jade dark:bg-slate-800 dark:shadow-none">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-brand-jade-muted text-brand-jade dark:bg-brand-jade/15 dark:text-brand-jade-light">
            <Bot className="h-4.5 w-4.5" />
          </span>
          <div>
            <h3 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-100">
              Triage Result
            </h3>
            <p className="inline-flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
              <Clock3 className="h-3.5 w-3.5" />
              {timestamp.toLocaleString()}
            </p>
          </div>
        </div>

        <span className={cn('inline-flex rounded-full px-3 py-1 text-xs font-medium', routingBadgeClasses[routingDecision])}>
          {routingDecision}
        </span>
      </header>

      <div className="mb-5 flex flex-col justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/40 sm:flex-row sm:items-center">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Assigned Queue</p>
          <span className={cn('mt-2 inline-flex rounded-full px-4 py-1.5 text-sm font-semibold', queueBadgeClass(result.queue))}>
            {result.queue}
          </span>
        </div>
        <div className="sm:pr-2">
          <ConfidenceGauge score={result.confidence} />
        </div>
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium text-slate-600 dark:text-slate-300">SOP Reference</span>
        <a
          href="#"
          onClick={(event) => event.preventDefault()}
          className="inline-flex items-center gap-1 rounded-lg bg-brand-jade-muted px-3 py-1.5 font-mono text-xs text-brand-jade transition-all duration-200 hover:bg-brand-jade hover:text-white dark:bg-brand-jade/15 dark:text-brand-jade-light dark:hover:bg-brand-jade dark:hover:text-white"
        >
          {result.sop_reference}
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>

      <section className="mb-5 rounded-xl border border-slate-200 p-4 dark:border-slate-700">
        <div className="mb-3 flex items-center justify-between">
          <p className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
            <ListChecks className="h-4 w-4 text-brand-jade" />
            SOP Solution
          </p>
          {hasMoreSteps && (
            <button
              type="button"
              onClick={() => setShowAllSteps((prev) => !prev)}
              className="inline-flex items-center gap-1 text-xs font-medium text-brand-accent transition-all duration-200 hover:text-blue-700 dark:hover:text-blue-300"
            >
              {showAllSteps ? (
                <>
                  Show less <ChevronUp className="h-3.5 w-3.5" />
                </>
              ) : (
                <>
                  Show all <ChevronDown className="h-3.5 w-3.5" />
                </>
              )}
            </button>
          )}
        </div>

        <ol className="space-y-2">
          {visibleSteps.map((step, index) => (
            <li key={`${step}-${index}`} className="flex items-start gap-2.5 text-sm text-slate-700 dark:text-slate-200">
              <CircleCheck className="mt-0.5 h-4 w-4 shrink-0 text-brand-jade" />
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </section>

      {showAISolution && (
        <section className="mb-5 rounded-xl border border-slate-200 p-4 dark:border-slate-700">
          <button
            type="button"
            onClick={() => setShowReasoning((prev) => !prev)}
            className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-slate-900 transition-all duration-200 hover:text-brand-accent dark:text-slate-100"
          >
            AI solution:
            {showReasoning ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          {showReasoning && (
            <blockquote className="border-l-2 border-slate-300 pl-3 text-sm italic text-slate-500 dark:border-slate-600 dark:text-slate-400">
              {result.reasoning}
            </blockquote>
          )}
        </section>
      )}

      <footer className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => {
            setShowAISolution(true)
            onOverride()
          }}
          className="inline-flex items-center justify-center rounded-lg bg-brand-jade px-4 py-2 text-sm font-semibold text-white transition-all duration-200 hover:bg-brand-jade-light"
        >
          Get AI Solution
        </button>
        <button
          type="button"
          onClick={onAccept}
          className="inline-flex items-center justify-center rounded-lg border border-brand-accent px-4 py-2 text-sm font-semibold text-brand-accent transition-all duration-200 hover:bg-blue-50 dark:hover:bg-brand-accent/15"
        >
          Auto Resolve
        </button>
        <button
          type="button"
          onClick={onEscalate}
          className="inline-flex items-center justify-center rounded-lg border border-danger-red px-4 py-2 text-sm font-semibold text-danger-red transition-all duration-200 hover:bg-red-50 dark:hover:bg-danger-red/15"
        >
          Escalate to Human
        </button>
      </footer>
    </article>
  )
}

export default TriageResultCard
