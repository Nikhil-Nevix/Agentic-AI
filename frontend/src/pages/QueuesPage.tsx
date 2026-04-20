import { Clock3, Gauge, Siren, Users } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getQueueAnalytics } from '../api/client'
import { cn } from '../lib/utils'
import type { QueueAnalyticsApiResponse, QueueCardData } from '../types'

interface QueuesPageProps {
  onViewQueue: (queueName: string) => void
}

type PresetRange = '7d' | '15d' | '30d' | '90d' | 'custom'

const formatDateInput = (value: Date) => value.toISOString().slice(0, 10)

const defaultRange = () => {
  const end = new Date()
  const start = new Date()
  start.setDate(end.getDate() - 6)
  return { startDate: formatDateInput(start), endDate: formatDateInput(end) }
}

const confidenceTone = (score: number) => {
  if (score >= 0.85) return 'text-brand-jade'
  if (score >= 0.6) return 'text-warning-amber'
  return 'text-danger-red'
}

const buildSampleQueueCards = (points: number): QueueCardData[] => {
  const baseCards: QueueCardData[] = [
    { name: 'STACK Service Desk', ticketCount: 4581, avgConfidence: 0.88, topCategory: 'Access Management', trend: [] },
    { name: 'Enterprise Apps', ticketCount: 3177, avgConfidence: 0.82, topCategory: 'Enterprise Platform', trend: [] },
    { name: 'Infra & Network', ticketCount: 1304, avgConfidence: 0.74, topCategory: 'Network Services', trend: [] },
    { name: 'End User Computing', ticketCount: 185, avgConfidence: 0.69, topCategory: 'Endpoint Support', trend: [] },
    { name: 'Other Queues', ticketCount: 195, avgConfidence: 0.63, topCategory: 'General Incident', trend: [] },
  ]
  return baseCards.map((card, cardIndex) => {
    const trend = Array.from({ length: points }, (_, idx) => {
      const wave = (idx % 5) - 2
      const scale = Math.max(6, Math.round(card.ticketCount / 25))
      const value = Math.max(1, scale + wave * Math.max(1, Math.round(scale * 0.12)) + cardIndex * 2)
      return value
    })
    return {
      ...card,
      trend,
    }
  })
}

export const QueuesPage = ({ onViewQueue }: QueuesPageProps) => {
  const initial = useMemo(() => defaultRange(), [])
  const [preset, setPreset] = useState<PresetRange>('7d')
  const [startDate, setStartDate] = useState(initial.startDate)
  const [endDate, setEndDate] = useState(initial.endDate)
  const [labels, setLabels] = useState<string[]>([])
  const [queueCards, setQueueCards] = useState<QueueCardData[]>([])
  const [summaryData, setSummaryData] = useState({
    totalOpen: 0,
    slaBreached: 0,
    avgResolutionHours: 0,
  })
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [isSampleData, setIsSampleData] = useState(false)

  useEffect(() => {
    if (preset === 'custom') return
    const days = preset === '7d' ? 7 : preset === '15d' ? 15 : preset === '30d' ? 30 : 90
    const end = new Date()
    const start = new Date()
    start.setDate(end.getDate() - (days - 1))
    setStartDate(formatDateInput(start))
    setEndDate(formatDateInput(end))
  }, [preset])

  useEffect(() => {
    const fetchQueueAnalytics = async () => {
      if (!startDate || !endDate) return
      setIsLoading(true)
      setError('')
      try {
        const response = (await getQueueAnalytics({
          startDate,
          endDate,
        })) as QueueAnalyticsApiResponse

        const safeLabels = response.labels || []
        const transformedCards = (response.queues || []).map((queue) => ({
          name: queue.name,
          ticketCount: Number(queue.ticket_count || 0),
          avgConfidence: Number(queue.avg_confidence || 0),
          topCategory: queue.top_category || 'General Incident',
          trend: Array.isArray(queue.trend) ? queue.trend.map((value) => Number(value || 0)) : [],
        }))
        const liveTotal = Number(response.total_open || 0)
        const hasLiveVisualData =
          liveTotal > 0 &&
          transformedCards.length > 0 &&
          transformedCards.some((queue) => queue.ticketCount > 0 || queue.trend.some((point) => point > 0))

        setLabels(safeLabels)
        if (!hasLiveVisualData) {
          const points = Math.max(1, safeLabels.length || 7)
          const sampleCards = buildSampleQueueCards(points)
          setQueueCards(sampleCards)
          setSummaryData({
            totalOpen: sampleCards.reduce((sum, queue) => sum + queue.ticketCount, 0),
            slaBreached: Math.max(1, Math.round(sampleCards.reduce((sum, queue) => sum + queue.ticketCount, 0) * 0.013)),
            avgResolutionHours: 3.8,
          })
          setIsSampleData(true)
        } else {
          setQueueCards(transformedCards)
          setSummaryData({
            totalOpen: liveTotal,
            slaBreached: Number(response.sla_breached || 0),
            avgResolutionHours: Number(response.avg_resolution_hours || 0),
          })
          setIsSampleData(false)
        }
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : 'Unable to load queue analytics.')
        const fallbackLabels =
          labels.length > 0
            ? labels
            : Array.from({ length: 7 }, (_, idx) => `D${idx + 1}`)
        const sampleCards = buildSampleQueueCards(fallbackLabels.length)
        setQueueCards(sampleCards)
        setLabels(fallbackLabels)
        setSummaryData({
          totalOpen: sampleCards.reduce((sum, queue) => sum + queue.ticketCount, 0),
          slaBreached: Math.max(1, Math.round(sampleCards.reduce((sum, queue) => sum + queue.ticketCount, 0) * 0.013)),
          avgResolutionHours: 3.8,
        })
        setIsSampleData(true)
      } finally {
        setIsLoading(false)
      }
    }

    void fetchQueueAnalytics()
  }, [startDate, endDate])

  return (
    <section className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:shadow-none">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-12">
          <div className="lg:col-span-3">
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Preset
            </label>
            <select
              value={preset}
              onChange={(event) => setPreset(event.target.value as PresetRange)}
              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            >
              <option value="7d">Last 7 Days</option>
              <option value="15d">Last 15 Days</option>
              <option value="30d">Last 30 Days</option>
              <option value="90d">Last 90 Days</option>
              <option value="custom">Custom</option>
            </select>
          </div>

          <div className="lg:col-span-3">
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Start Date
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(event) => {
                setPreset('custom')
                setStartDate(event.target.value)
              }}
              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
          </div>

          <div className="lg:col-span-3">
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
              End Date
            </label>
            <input
              type="date"
              value={endDate}
              onChange={(event) => {
                setPreset('custom')
                setEndDate(event.target.value)
              }}
              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
          </div>

          <div className="flex items-end lg:col-span-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
              Range: {startDate} → {endDate}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:shadow-none">
          <p className="text-sm text-slate-500 dark:text-slate-400">Total Open</p>
          <p className="mt-2 text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            {summaryData.totalOpen.toLocaleString()}
          </p>
          <span className="mt-3 inline-flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
            <Users className="h-3.5 w-3.5 text-brand-accent" />
            Active queue load
          </span>
        </article>

        <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:shadow-none">
          <p className="text-sm text-slate-500 dark:text-slate-400">SLA Breached</p>
          <p className="mt-2 text-3xl font-semibold tracking-tight text-danger-red">
            {summaryData.slaBreached}
          </p>
          <span className="mt-3 inline-flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
            <Siren className="h-3.5 w-3.5 text-danger-red" />
            Needs urgent attention
          </span>
        </article>

        <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:shadow-none">
          <p className="text-sm text-slate-500 dark:text-slate-400">Avg Resolution Time</p>
          <p className="mt-2 text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            {summaryData.avgResolutionHours}h
          </p>
          <span className="mt-3 inline-flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
            <Clock3 className="h-3.5 w-3.5 text-brand-jade" />
            Selected range
          </span>
        </article>
      </div>

      {isSampleData && (
        <div className="inline-flex items-center rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300">
          Sample data
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-danger-red/30 bg-danger-red/10 px-4 py-2 text-sm text-danger-red">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        {queueCards.map((queue) => {
          const chartData = queue.trend.map((value, index) => ({ day: labels[index] || `D${index + 1}`, value }))
          return (
            <article
              key={queue.name}
              className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:shadow-none"
            >
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold tracking-tight text-slate-900 dark:text-slate-100">
                    {queue.name}
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">Top category: {queue.topCategory}</p>
                </div>
                <span className="inline-flex rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-200">
                  {queue.ticketCount.toLocaleString()} tickets
                </span>
              </div>

              <div className="mb-4 grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-900/50">
                  <p className="text-xs text-slate-500 dark:text-slate-400">Avg Confidence</p>
                  <p className={cn('mt-1 font-semibold', confidenceTone(queue.avgConfidence))}>
                    {Math.round(queue.avgConfidence * 100)}%
                  </p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-900/50">
                  <p className="text-xs text-slate-500 dark:text-slate-400">Top Category</p>
                  <p className="mt-1 font-semibold text-slate-700 dark:text-slate-200">{queue.topCategory}</p>
                </div>
              </div>

              <div className="mb-4 h-28 rounded-lg border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-900/50">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData}>
                    <XAxis dataKey="day" axisLine={false} tickLine={false} fontSize={10} stroke="#94A3B8" />
                    <YAxis hide />
                    <Tooltip
                      formatter={(value: number) => [`${value} tickets`, 'Volume']}
                      contentStyle={{
                        borderRadius: '10px',
                        border: '1px solid #E2E8F0',
                        backgroundColor: '#FFFFFF',
                      }}
                    />
                    <Bar dataKey="value" fill="#00A86B" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <button
                type="button"
                onClick={() => {
                  window.localStorage.setItem(
                    'tickets-page-state',
                    JSON.stringify({ queueFilter: queue.name, categoryFilter: '' }),
                  )
                  onViewQueue(queue.name)
                }}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-brand-jade bg-brand-jade px-4 py-2 text-sm font-semibold text-white transition-all duration-200 hover:bg-brand-jade-light"
              >
                <Gauge className="h-4 w-4" />
                View Queue
              </button>
            </article>
          )
        })}
      </div>

      {isLoading && (
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
          Loading queue analytics...
        </div>
      )}
    </section>
  )
}

export default QueuesPage
