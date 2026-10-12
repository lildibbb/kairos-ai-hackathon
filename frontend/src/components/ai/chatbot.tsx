import { useState, type FormEvent, type HTMLAttributes, type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ArrowUp, ArrowUpRight, LinkSimple } from '@phosphor-icons/react'
import { Message, MessageContent } from '@/components/ai/message'

export type ChatbotProps = HTMLAttributes<HTMLElement>

export const Chatbot = ({ className, ...props }: ChatbotProps) => (
  <section className={cn('chatbot', className)} {...props} />
)

export type ChatbotHeaderProps = HTMLAttributes<HTMLDivElement> & {
  label: string
  title: string
  titleId?: string
  context?: ReactNode
}

export const ChatbotHeader = ({ className, label, title, titleId, context, ...props }: ChatbotHeaderProps) => (
  <header className={cn('chatbot-header', className)} {...props}>
    <div>
      <p className="section-label">{label}</p>
      <h3 id={titleId}>{title}</h3>
    </div>
    {context}
  </header>
)

export type ChatbotMessageProps = HTMLAttributes<HTMLDivElement> & {
  from: 'user' | 'assistant'
  roleLabel: string
}

export const ChatbotMessage = ({ className, from, roleLabel, children, ...props }: ChatbotMessageProps) => (
  <Message from={from} className={cn('chat-message', from === 'user' ? 'chat-message-user' : 'chat-message-assistant', className)} {...props}>
    <MessageContent className="chat-body">
      <p className="chat-role">{roleLabel}</p>
      {children}
    </MessageContent>
  </Message>
)

export type ChatbotSuggestionsProps = Omit<HTMLAttributes<HTMLDivElement>, 'onSelect'> & {
  items: string[]
  onSelect: (item: string) => void
  disabled?: boolean
}

export const ChatbotSuggestions = ({ className, items, onSelect, disabled, ...props }: ChatbotSuggestionsProps) => (
  <div className={cn('assistant-starters', className)} role="group" aria-label="Suggested questions" {...props}>
    {items.map((item) => (
      <Button key={item} variant="secondary" type="button" disabled={disabled} onClick={() => onSelect(item)}>
        {item}
        <ArrowUpRight size={18} aria-hidden="true" />
      </Button>
    ))}
  </div>
)

export type ChatbotPromptInputProps = {
  className?: string
  onSubmit: (question: string) => void
  disabled: boolean
  isSearching?: boolean
}

export const ChatbotPromptInput = ({ className, onSubmit, disabled, isSearching = false }: ChatbotPromptInputProps) => {
  const [question, setQuestion] = useState('')

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed)
    setQuestion('')
  }

  return (
    <form className={cn('assistant-composer', className)} onSubmit={handleSubmit}>
      <div className="form-field">
        <Label htmlFor="assistant-question">Ask about this ticket</Label>
        <Textarea
          id="assistant-question"
          name="question"
          rows={2}
          maxLength={1000}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={disabled}
          aria-describedby="composer-hint"
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.metaKey || event.ctrlKey) && !event.nativeEvent.isComposing) {
              event.preventDefault()
              event.currentTarget.form?.requestSubmit()
            }
          }}
          placeholder="Describe what you see or ask for the next check…"
        />
      </div>
      <div className="composer-footer">
        <span className="composer-context"><LinkSimple size={16} aria-hidden="true" /> Ticket and service context</span>
        <p id="composer-hint">Enter adds a line. Ctrl or Cmd plus Enter sends{isSearching ? '. You can ask a follow-up while the assistant responds' : ''}</p>
        <Button className="process-button assistant-submit" type="submit" disabled={disabled || question.trim().length === 0}>
          {disabled ? 'Assistant unavailable' : 'Send question'}
          <ArrowUp size={18} weight="bold" aria-hidden="true" />
        </Button>
      </div>
    </form>
  )
}
