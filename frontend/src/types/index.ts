export type ThemeMode = 'light' | 'dark'

export interface ThemeContextValue {
  theme: ThemeMode
  setTheme: (theme: ThemeMode) => void
  toggleTheme: () => void
}

export type SidebarRoute =
  | '/welcome'
  | '/dashboard'
  | '/triage'
  | '/tickets'
  | '/queues'
  | '/login'
  | '/signup'

export interface SidebarNavItem {
  label: string
  route: SidebarRoute
  badgeCount?: number
}

export interface SidebarProps {
  activeRoute: SidebarRoute
  onNavigate: (route: SidebarRoute) => void
  queueCount?: number
  collapsedByDefault?: boolean
  showDashboard?: boolean
}

export interface TopbarNotification {
  id: string
  title: string
  time: string
  unread?: boolean
}

export interface TopbarUser {
  name: string
  role: string
  initials: string
  email?: string
}

export interface TopbarProps {
  searchValue: string
  onSearchChange: (value: string) => void
  onLogout: () => void
  user?: TopbarUser
  notifications?: TopbarNotification[]
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface LoginPageProps {
  isLoading?: boolean
  onLogin: (credentials: LoginCredentials) => Promise<void> | void
}

export interface SignupPageProps {
  isLoading?: boolean
  onSignup: (credentials: LoginCredentials) => Promise<void> | void
}

export interface DashboardStats {
  totalTickets: number
  autoResolved: number
  avgConfidence: number
  escalated: number
}

export interface QueueDistributionItem {
  name: string
  value: number
  color: string
}

export type TicketRouting = 'auto-resolved' | 'routed' | 'escalated'

export interface RecentTicket {
  id: string
  subject: string
  queue: string
  category: string
  confidence: number
  routing: TicketRouting
  createdAt: string
}

export type TriageRoutingDecision = 'auto-resolved' | 'routed' | 'escalated'

export interface TriageResult {
  queue: string
  category: string
  sub_category: string
  resolution_steps: string[]
  confidence: number
  sop_reference: string
  reasoning: string
  routing?: TriageRoutingDecision
  timestamp?: string
}

export interface ConfidenceGaugeProps {
  score: number
  animated?: boolean
}

export interface TriageResultCardProps {
  result: TriageResult
  onAccept: () => void
  onOverride: () => void
  onEscalate: () => void
}

export interface TriagePageProps {
  onTriageSaved?: (result: TriageResult) => void
}

export interface TicketListItem {
  id: string
  subject: string
  queue: string
  category: string
  confidence: number
  routing: TicketRouting
  createdAt: string
  description?: string
  sub_category?: string
  sop_reference?: string
  reasoning?: string
  resolution_steps?: string[]
}

export interface TicketsApiResponse {
  tickets: TicketListItem[]
  total: number
  page: number
}

export interface TicketsPageProps {
  globalSearch?: string
}

export interface QueueCardData {
  name: string
  ticketCount: number
  avgConfidence: number
  topCategory: string
  trend: number[]
}

export interface QueueAnalyticsApiItem {
  name: string
  ticket_count: number
  avg_confidence: number
  top_category: string
  trend: number[]
}

export interface QueueAnalyticsApiResponse {
  start_date: string
  end_date: string
  labels: string[]
  total_open: number
  sla_breached: number
  avg_resolution_hours: number
  queues: QueueAnalyticsApiItem[]
}
