import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import FloatingChatWidget from './components/FloatingChatWidget'
const Dashboard = lazy(() => import('./components/Dashboard'))
const WelcomePage = lazy(() => import('./pages/WelcomePage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const SignupPage = lazy(() => import('./pages/SignupPage'))
const TriagePage = lazy(() => import('./pages/TriagePage'))
const TicketsPage = lazy(() => import('./pages/TicketsPage'))
const QueuesPage = lazy(() => import('./pages/QueuesPage'))
import { getHealth, getStats, loginUser, signupUser } from './api/client'
import { cn } from './lib/utils'
import type { LoginCredentials, SidebarRoute, TriageResult as TriageResultData } from './types'

const JADE_DOMAIN = 'jadeglobal.com'

const isJadeUserEmail = (email: string): boolean => {
  const normalized = email.trim().toLowerCase()
  const domain = normalized.split('@')[1] || ''
  return domain === JADE_DOMAIN
}

const routeTitle: Record<SidebarRoute, string> = {
  '/welcome': 'Welcome to Service Desk Triage',
  '/login': 'Sign in to Service Desk Triage',
  '/signup': 'Create your Service Desk account',
  '/dashboard': 'Executive Dashboard',
  '/triage': 'Triage & AI Solution Provider',
  '/tickets': 'Ticket Operations Console',
  '/queues': 'Queue Management',
}

const toSidebarRoute = (pathname: string): SidebarRoute => {
  if (pathname.startsWith('/dashboard')) return '/dashboard'
  if (pathname.startsWith('/tickets')) return '/tickets'
  if (pathname.startsWith('/queues')) return '/queues'
  if (pathname.startsWith('/welcome')) return '/welcome'
  if (pathname.startsWith('/signup')) return '/signup'
  if (pathname.startsWith('/login')) return '/login'
  return '/triage'
}

const AppShell = ({
  isAuthenticated,
  isJadeUser,
  onLogout,
  children,
}: {
  isAuthenticated: boolean
  isJadeUser: boolean
  onLogout: () => void
  children: React.ReactNode
}) => {
  const navigate = useNavigate()
  const location = useLocation()
  const [health, setHealth] = useState<Record<string, unknown> | null>(null)
  const [stats, setStats] = useState<Record<string, unknown> | null>(null)
  const [searchValue, setSearchValue] = useState('')
  const signedInEmail = window.localStorage.getItem('jade-signup-email') || 'service.desk@jadeglobal.com'
  const signedInRole = window.localStorage.getItem('jade-user-role') || 'Service Desk User'
  const username = signedInEmail.split('@')[0]
  const initials = username
    .split(/[.\s_-]+/)
    .map((part) => part[0]?.toUpperCase() || '')
    .join('')
    .slice(0, 2) || 'SD'

  const activeRoute = useMemo(() => toSidebarRoute(location.pathname), [location.pathname])
  const effectiveRoute = !isJadeUser && activeRoute === '/dashboard' ? '/triage' : activeRoute

  useEffect(() => {
    const loadShellData = async () => {
      try {
        const [healthData, statsData] = await Promise.all([getHealth(), getStats()])
        setHealth(healthData)
        setStats(statsData)
      } catch (shellError) {
        console.error('Failed to load shell status:', shellError)
      }
    }
    void loadShellData()
  }, [])

  const handleNavigate = (route: SidebarRoute) => {
    if (route === '/login') {
      onLogout()
      navigate('/login')
      return
    }
    navigate(route)
  }

  return (
    <div className={cn('min-h-screen bg-slate-50 dark:bg-slate-900')}>
      {isAuthenticated && (
        <Sidebar
          activeRoute={effectiveRoute}
          onNavigate={handleNavigate}
          queueCount={5}
          showDashboard={isJadeUser}
        />
      )}
      <div className={cn('min-h-screen transition-all duration-200', isAuthenticated ? 'ml-64' : 'ml-0')}>
        <Topbar
          searchValue={searchValue}
          onSearchChange={setSearchValue}
          onLogout={() => {
            onLogout()
            navigate('/login')
          }}
          user={{
            name: username,
            role: signedInRole,
            initials,
            email: signedInEmail,
          }}
        />
        <header className="border-b border-slate-200 bg-white px-6 py-5 dark:border-slate-700 dark:bg-slate-900">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
                <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
                  {routeTitle[effectiveRoute]}
                </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                AI-Powered Service Intelligence
              </p>
            </div>
            {health && stats && (
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                Health active • {(stats as Record<string, unknown>).llm_provider as string}
              </div>
            )}
          </div>
        </header>
        <main className="p-6">{children}</main>
        <FloatingChatWidget userId={signedInEmail} visible={isAuthenticated && !isJadeUser} />
      </div>
    </div>
  )
}

const RequireAuth = ({
  isAuthenticated,
  children,
}: {
  isAuthenticated: boolean
  children: React.ReactNode
}) => {
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

function App() {
  const navigate = useNavigate()
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isJadeUser, setIsJadeUser] = useState(false)
  const [isAuthLoading, setIsAuthLoading] = useState(false)
  const [triageHistory, setTriageHistory] = useState<Record<string, unknown>[]>([])

  useEffect(() => {
    const authState = window.localStorage.getItem('jade-auth')
    const storedDomainFlag = window.localStorage.getItem('jade-is-company-user')
    setIsJadeUser(storedDomainFlag === 'true')
    if (authState === 'true') {
      setIsAuthenticated(true)
    }
    const savedHistory = window.localStorage.getItem('triage_history')
    if (savedHistory) {
      setTriageHistory(JSON.parse(savedHistory))
    }
  }, [])

  const handleLogin = async (credentials: LoginCredentials) => {
    setIsAuthLoading(true)
    try {
      const response = await loginUser({
        email: credentials.email,
        password: credentials.password,
      })
      const user = response?.user
      if (!user?.email) {
        throw new Error('Invalid login response from server.')
      }
      const companyUser = isJadeUserEmail(user.email)
      setIsAuthenticated(true)
      setIsJadeUser(companyUser)
      window.localStorage.setItem('jade-auth', 'true')
      window.localStorage.setItem('jade-signup-email', user.email)
      window.localStorage.setItem('jade-user-role', user.role || 'Service Desk User')
      window.localStorage.setItem('jade-is-company-user', companyUser ? 'true' : 'false')
      navigate(companyUser ? '/dashboard' : '/triage')
    } catch (error) {
      const message = (error as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail?.message
      throw new Error(message || 'Unable to sign in. Please try again.')
    } finally {
      setIsAuthLoading(false)
    }
  }

  const handleSignup = async (credentials: LoginCredentials) => {
    setIsAuthLoading(true)
    try {
      const response = await signupUser({
        email: credentials.email,
        password: credentials.password,
      })
      const user = response?.user
      if (!user?.email) {
        throw new Error('Invalid signup response from server.')
      }
      const companyUser = isJadeUserEmail(user.email)
      setIsAuthenticated(true)
      setIsJadeUser(companyUser)
      window.localStorage.setItem('jade-auth', 'true')
      window.localStorage.setItem('jade-signup-email', user.email)
      window.localStorage.setItem('jade-user-role', user.role || 'Service Desk User')
      window.localStorage.setItem('jade-is-company-user', companyUser ? 'true' : 'false')
      navigate(companyUser ? '/dashboard' : '/triage')
    } catch (error) {
      const message = (error as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail?.message
      throw new Error(message || 'Unable to sign up. Please try again.')
    } finally {
      setIsAuthLoading(false)
    }
  }

  const handleLogout = () => {
    setIsAuthenticated(false)
    setIsJadeUser(false)
    window.localStorage.removeItem('jade-auth')
    window.localStorage.removeItem('jade-signup-email')
    window.localStorage.removeItem('jade-user-role')
    window.localStorage.removeItem('jade-is-company-user')
  }

  const handleTriageSaved = (savedResult: TriageResultData) => {
    const resultWithMeta: Record<string, unknown> = {
      ...savedResult,
      id: Date.now().toString(),
      timestamp: savedResult.timestamp ?? new Date().toISOString(),
    }
    const updatedHistory = [resultWithMeta, ...triageHistory]
    setTriageHistory(updatedHistory)
    window.localStorage.setItem('triage_history', JSON.stringify(updatedHistory))
  }

  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-600 dark:bg-slate-900 dark:text-slate-300">
          Loading workspace...
        </div>
      }
    >
      <Routes>
        <Route
          path="/welcome"
          element={<WelcomePage />}
        />

        <Route
          path="/login"
          element={<LoginPage isLoading={isAuthLoading} onLogin={handleLogin} />}
        />

        <Route
          path="/signup"
          element={<SignupPage isLoading={isAuthLoading} onSignup={handleSignup} />}
        />

        <Route
          path="/dashboard"
          element={
            <RequireAuth isAuthenticated={isAuthenticated}>
              {isJadeUser ? (
                <AppShell isAuthenticated={isAuthenticated} isJadeUser={isJadeUser} onLogout={handleLogout}>
                  <Dashboard />
                </AppShell>
              ) : (
                <Navigate to="/triage" replace />
              )}
            </RequireAuth>
          }
        />

        <Route
          path="/triage"
          element={
            <RequireAuth isAuthenticated={isAuthenticated}>
              <AppShell isAuthenticated={isAuthenticated} isJadeUser={isJadeUser} onLogout={handleLogout}>
                <TriagePage onTriageSaved={handleTriageSaved} />
              </AppShell>
            </RequireAuth>
          }
        />

        <Route
          path="/tickets"
          element={
            <RequireAuth isAuthenticated={isAuthenticated}>
              <AppShell isAuthenticated={isAuthenticated} isJadeUser={isJadeUser} onLogout={handleLogout}>
                <TicketsPage />
              </AppShell>
            </RequireAuth>
          }
        />

        <Route
          path="/queues"
          element={
            <RequireAuth isAuthenticated={isAuthenticated}>
              <AppShell isAuthenticated={isAuthenticated} isJadeUser={isJadeUser} onLogout={handleLogout}>
                <QueuesPage onViewQueue={() => navigate('/tickets')} />
              </AppShell>
            </RequireAuth>
          }
        />

        <Route path="/" element={<Navigate to={isAuthenticated ? (isJadeUser ? '/dashboard' : '/triage') : '/welcome'} replace />} />
        <Route path="*" element={<Navigate to={isAuthenticated ? (isJadeUser ? '/dashboard' : '/triage') : '/welcome'} replace />} />
      </Routes>
    </Suspense>
  )
}

export default App
