import { Loader2, Maximize2, MessageSquare, Minimize2, Send, Trash2, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { clearChatbotHistory, sendChatbotMessage } from '../api/client'
import { cn } from '../lib/utils'

type ChatRole = 'user' | 'bot'

interface ChatOption {
  label: string
  action: string
}

interface ChatMessage {
  id: string
  role: ChatRole
  text: string
  options?: ChatOption[]
  createdAt: string
}

interface FloatingChatWidgetProps {
  userId: string
  visible: boolean
}

const buildHistoryKey = (userId: string) => `floating_chat_history_${userId}`

const createMessage = (role: ChatRole, text: string, options: ChatOption[] = []): ChatMessage => ({
  id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
  role,
  text,
  options,
  createdAt: new Date().toISOString(),
})

const FloatingChatWidget = ({ userId, visible }: FloatingChatWidgetProps) => {
  const [isOpen, setIsOpen] = useState(false)
  const [isMaximized, setIsMaximized] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const chatBodyRef = useRef<HTMLDivElement | null>(null)
  const textAreaRef = useRef<HTMLTextAreaElement | null>(null)

  const historyKey = useMemo(() => buildHistoryKey(userId), [userId])

  useEffect(() => {
    const saved = window.localStorage.getItem(historyKey)
    if (!saved) {
      setMessages([])
      return
    }

    try {
      const parsed = JSON.parse(saved) as ChatMessage[]
      setMessages(Array.isArray(parsed) ? parsed : [])
    } catch {
      setMessages([])
    }
  }, [historyKey])

  useEffect(() => {
    window.localStorage.setItem(historyKey, JSON.stringify(messages))
  }, [historyKey, messages])

  useEffect(() => {
    if (!chatBodyRef.current) return
    chatBodyRef.current.scrollTop = chatBodyRef.current.scrollHeight
  }, [messages, isOpen])

  useEffect(() => {
    const element = textAreaRef.current
    if (!element) return

    const maxHeight = 8 * 24
    element.style.height = 'auto'
    if (element.scrollHeight > maxHeight) {
      element.style.height = `${maxHeight}px`
      element.style.overflowY = 'auto'
    } else {
      element.style.height = `${element.scrollHeight}px`
      element.style.overflowY = 'hidden'
    }
  }, [inputValue, isOpen])

  const appendBotResponse = (message: string, options: ChatOption[] = []) => {
    setMessages((previous) => [...previous, createMessage('bot', message, options)])
  }

  const sendMessage = async ({ message, action, userEcho }: { message?: string; action?: string; userEcho?: string }) => {
    setIsLoading(true)
    if (userEcho) {
      setMessages((previous) => [...previous, createMessage('user', userEcho)])
    }

    try {
      const response = await sendChatbotMessage({
        userId,
        sessionId: 'frontend-widget',
        message,
        action,
      })
      appendBotResponse(response.message, response.options || [])
    } catch {
      appendBotResponse('I could not process that right now. Please try again in a moment.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleClearHistory = async () => {
    if (isLoading) {
      return
    }

    setIsLoading(true)
    try {
      await clearChatbotHistory({ userId, sessionId: 'frontend-widget' })
      setMessages([])
      window.localStorage.removeItem(historyKey)
      appendBotResponse('Chat history deleted. You can start a new conversation now.')
    } catch {
      appendBotResponse('I could not delete history right now. Please try again in a moment.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (!visible || !isOpen) return
    if (messages.length > 0) return
    void sendMessage({ message: '' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, isOpen])

  const submitCurrentMessage = async () => {
    if (isLoading || !inputValue.trim()) {
      return
    }

    const messageToSend = inputValue
    setInputValue('')
    await sendMessage({ message: messageToSend, userEcho: messageToSend })
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await submitCurrentMessage()
  }

  const handleComposerKeyDown = async (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      await submitCurrentMessage()
    }
  }

  if (!visible) {
    return null
  }

  return (
    <div className="fixed bottom-5 right-5 z-[70]">
      {isOpen && (
        <div
          className={cn(
            'mb-3 flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900',
            isMaximized
              ? 'h-[min(90vh,820px)] w-[min(50vw,760px)] max-w-[calc(100vw-2rem)]'
              : 'h-[640px] w-[420px] max-w-[calc(100vw-2rem)]',
          )}
        >
          <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-800">
            <div>
              <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Support Assistant</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">SOP, AI solutions, and ticket escalation</p>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={handleClearHistory}
                disabled={isLoading}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold text-slate-600 transition-colors hover:bg-slate-200 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-slate-100"
                aria-label="Delete chat history"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete History
              </button>
              <button
                type="button"
                onClick={() => setIsMaximized((previous) => !previous)}
                className="rounded-md p-1 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-900 dark:hover:bg-slate-700 dark:hover:text-slate-100"
                aria-label={isMaximized ? 'Minimize chat' : 'Maximize chat'}
              >
                {isMaximized ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </button>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="rounded-md p-1 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-900 dark:hover:bg-slate-700 dark:hover:text-slate-100"
                aria-label="Close chat"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div ref={chatBodyRef} className="flex-1 space-y-3 overflow-y-auto bg-slate-100/70 p-3 dark:bg-slate-950">
            {messages.map((message) => (
              <div key={message.id} className={cn('flex', message.role === 'user' ? 'justify-end' : 'justify-start')}>
                <div
                  className={cn(
                    'max-w-[86%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap',
                    message.role === 'user'
                      ? 'bg-brand-jade text-white'
                      : 'border border-slate-200 bg-white text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100',
                  )}
                >
                  {message.text}
                  {message.options && message.options.length > 0 && (
                    <div className="mt-2 space-y-1.5">
                      {message.options.map((option) => (
                        <button
                          key={`${message.id}_${option.action}_${option.label}`}
                          type="button"
                          disabled={isLoading}
                          onClick={() => {
                            if (isLoading) return
                            void sendMessage({ action: option.action, userEcho: option.label })
                          }}
                          className="w-full rounded-md border border-slate-300 bg-slate-50 px-2 py-1.5 text-left text-xs font-medium text-slate-700 transition-colors hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Thinking...
              </div>
            )}
          </div>

          <form onSubmit={handleSubmit} className="border-t border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
            <div className="flex items-end gap-2">
              <textarea
                ref={textAreaRef}
                value={inputValue}
                onChange={(event) => setInputValue(event.target.value)}
                onKeyDown={handleComposerKeyDown}
                placeholder="Describe your issue..."
                disabled={isLoading}
                rows={1}
                className="max-h-48 min-h-10 flex-1 resize-none rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-900 outline-none transition-colors focus:border-brand-jade dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
              <button
                type="submit"
                disabled={isLoading || !inputValue.trim()}
                className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-brand-jade text-white transition-colors hover:bg-brand-jade-light disabled:cursor-not-allowed disabled:opacity-60"
                aria-label="Send message"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </form>
        </div>
      )}

      <button
        type="button"
        onClick={() => setIsOpen((previous) => !previous)}
        className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-brand-jade text-white shadow-lg transition-transform hover:scale-105 hover:bg-brand-jade-light"
        aria-label="Open support chatbot"
      >
        {isOpen ? <X className="h-6 w-6" /> : <MessageSquare className="h-6 w-6" />}
      </button>
    </div>
  )
}

export default FloatingChatWidget
