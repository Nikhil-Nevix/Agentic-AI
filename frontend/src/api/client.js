import axios from 'axios'

// Use relative path to leverage Vite proxy in dev, or full URL in production
const API_BASE_URL = import.meta.env.VITE_API_URL || (
  import.meta.env.DEV ? '' : 'http://localhost:2027'
)

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000, // 60 seconds for triaging
  headers: {
    'Content-Type': 'application/json',
  }
})

// Request interceptor for logging
api.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method.toUpperCase()} ${config.url}`)
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => {
    console.log(`API Response: ${response.status} ${response.config.url}`)
    return response
  },
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

// API Methods

export const getHealth = async () => {
  const response = await api.get('/api/v1/health')
  return response.data
}

export const getQueues = async () => {
  const response = await api.get('/api/v1/queues')
  return response.data
}

export const getStats = async () => {
  const response = await api.get('/api/v1/stats')
  return response.data
}

export const triageTicket = async (ticketData) => {
  const response = await api.post('/api/v1/triage', ticketData)
  return response.data
}

export const startAsyncTriage = async (ticketData) => {
  const response = await api.post('/api/v1/tickets/triage', ticketData)
  return response.data
}

export const getAsyncTriageStatus = async (jobId) => {
  const response = await api.get(`/api/v1/tickets/triage/${jobId}`)
  return response.data
}

export const getTickets = async ({ page = 1, limit = 20, queue = '', category = '', search = '' } = {}) => {
  const response = await api.get('/api/v1/tickets', {
    params: { page, limit, queue, category, search },
  })
  return response.data
}

export const getQueueAnalytics = async ({ startDate, endDate }) => {
  const response = await api.get('/api/v1/queues/analytics', {
    params: { start_date: startDate, end_date: endDate },
  })
  return response.data
}

export const signupUser = async ({ email, password, full_name = null, role = 'Service Desk User' }) => {
  const response = await api.post('/api/v1/auth/signup', {
    email,
    password,
    full_name,
    role,
  })
  return response.data
}

export const loginUser = async ({ email, password }) => {
  const response = await api.post('/api/v1/auth/login', {
    email,
    password,
  })
  return response.data
}

export const sendChatbotMessage = async ({ userId, sessionId = 'portal', message, action }) => {
  const response = await api.post('/api/v1/chatbot/message', {
    user_id: userId,
    session_id: sessionId,
    message,
    action,
  })
  return response.data
}

export const clearChatbotHistory = async ({ userId, sessionId = 'portal' }) => {
  const response = await api.post('/api/v1/chatbot/history/clear', {
    user_id: userId,
    session_id: sessionId,
  })
  return response.data
}

export default api
