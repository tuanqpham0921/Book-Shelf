import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import { useRef, useEffect, useState, lazy, Suspense } from 'react'
import { Copy, Check } from 'lucide-react';
import { BookGridStack } from '@/components/book/BooksGrid';
import TaskSection from '@/components/chatbot/TaskSection';
import ChatFeedback from '@/components/chatbot/ChatFeedback';
import { MarkdownPre } from '@/design-system/CodeBlock';

// Fenced code in a reply gets the same highlighting as the task details
const MARKDOWN_COMPONENTS = { pre: MarkdownPre };

// Dynamic import for MermaidDiagram (large library)
const MermaidDiagram = lazy(() => import('@/components/MermaidDiagram'));

// Loading component for Mermaid
const MermaidLoading = () => (
    <div className="message-bubble response">
        <div className="flex items-center justify-center h-32">
            <div className="loading-spinner"></div>
            <span className="ml-2 text-[var(--text-hover)]">Loading diagram...</span>
        </div>
    </div>
);

/**
 * Render one section. Pulled out of the map so `task` sections can call it on
 * their own children — that nesting is the only recursion in the tree, and it
 * is one level deep: a task holds text and books, never another task.
 */
function renderSection(section, responseId, sectionIndex) {
    const key = section.id || `${responseId}-section-${sectionIndex}`;

    // Task section — a step in the plan, holding its own sections
    if (section.type === 'task') {
        return (
            <TaskSection key={key} section={section}>
                {(section.sections || []).map((child, childIndex) =>
                    renderSection(child, key, childIndex)
                )}
            </TaskSection>
        );
    }

    // Text section
    if (section.type === 'text' && section.content) {
        return (
            <div key={key} className="message-bubble response markdown-container">
                <Markdown remarkPlugins={[remarkGfm, remarkBreaks]} components={MARKDOWN_COMPONENTS}>{section.content}</Markdown>
            </div>
        );
    }

    // Books section
    if (section.type === 'books' && section.books && section.books.length > 0) {
        return (
            <div key={key} className="book-cards-container mb-2">
                <BookGridStack books={section.books} />
            </div>
        );
    }

    // Sources section — the docs a project answer came from
    if (section.type === 'sources' && section.sources && section.sources.length > 0) {
        return (
            <div key={key} className="message-bubble response text-sm text-[var(--text-hover)]">
                <span className="font-medium">Sources:</span>
                <ul className="list-disc pl-5 mt-1">
                    {section.sources.map(source => <li key={source}>{source}</li>)}
                </ul>
            </div>
        );
    }

    // Diagram section — the plan, framed as the first step of the task list
    if (section.type === 'diagram' && section.mermaid) {
        return (
            <TaskSection key={key} section={section}>
                <Suspense fallback={<MermaidLoading />}>
                    <MermaidDiagram chart={section.mermaid} />
                </Suspense>
            </TaskSection>
        );
    }

    // Error section
    if (section.type === 'error' && section.content) {
        return (
            <div key={key} className="message-bubble text-[var(--accent-negative)] italic mt-2 whitespace-pre-wrap">
                <span>{section.content}</span>
            </div>
        );
    }

    return null;
}

function ChatMessages({ messages, sessionId }) {
    const containerRef = useRef(null)
    const userMessageRefs = useRef({})
    const turnRefs = useRef({})
    const lastUserMessageId = useRef(null)
    const [copiedId, setCopiedId] = useState(null)

    const handleCopy = async (text, id) => {
        await navigator.clipboard.writeText(text)
        setCopiedId(id)
        setTimeout(() => setCopiedId(current => current === id ? null : current), 1500)
    }

    // Follow the reply as it streams, unless the reader scrolled up. A new
    // turn starts pinned to the top instead — and since the newest turn is at
    // least the list's height (`.newest`), "the bottom" is that same spot
    // until the reply outgrows the view, so following only starts then.
    const following = useRef(true)
    const lastScrollTop = useRef(0)
    const lastScrollHeight = useRef(0)

    const scrollToBottom = () => {
        const el = containerRef.current
        el?.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }

    const handleScroll = () => {
        const el = containerRef.current
        if (el.scrollHeight - el.scrollTop - el.clientHeight < 40) {
            following.current = true
        } else if (el.scrollTop < lastScrollTop.current) {
            // only the reader scrolls up — every scroll made here goes down
            following.current = false
        }
        lastScrollTop.current = el.scrollTop
    }

    useEffect(() => {
        const el = containerRef.current
        const newestTurn = messages.at(-1)
        if (!el || !newestTurn) return

        if (newestTurn.user && newestTurn.user.id !== lastUserMessageId.current) {
            lastUserMessageId.current = newestTurn.user.id
            following.current = true
            turnRefs.current[newestTurn.id]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        } else if (
            following.current &&
            // grown past the view; scrolling sooner would cut the smooth
            // scroll to the new turn short. Not only while streaming: the
            // feedback row and the disclaimer land as the reply ends
            el.scrollHeight > lastScrollHeight.current
        ) {
            scrollToBottom()
        }
        lastScrollHeight.current = el.scrollHeight
    }, [messages])

    return (
        <div ref={containerRef} onScroll={handleScroll} className="chat-messages-container">
            {messages.map(({ id, user, response }, index) => (
                <div
                    key={id}
                    data-turn-id={id}
                    ref={(el) => turnRefs.current[id] = el}
                    className={`turn-container ${index === messages.length - 1 ? 'newest' : ''}`}
                >
                    {/* User message */}
                    <div data-user-id={user.id}
                        className="message-wrapper user relative"
                        ref={user.isUser ? (el) => userMessageRefs.current[user.id] = el : null}
                    >
                        <div className="message-bubble user">
                            {user.text}
                        </div>
                        <button
                            type="button"
                            onClick={() => handleCopy(user.text, user.id)}
                            title="Copy message"
                            className="ml-2 self-end rounded-md text-[var(--text-muted)] hover:text-[var(--text-hover)] transition-colors"
                        >
                            {copiedId === user.id ? <Check size={16} /> : <Copy size={16} />}
                        </button>
                    </div>

                    <div data-response-id={response.id} className="flex flex-col message-wrapper response">

                        {/* SECTIONS-BASED RENDERING WITH STABLE IDs */}
                        {response.sections && response.sections.length > 0 && (
                            // Render sections in order using stable section IDs
                            response.sections.map((section, sectionIndex) =>
                                renderSection(section, response.id, sectionIndex)
                            )
                        )}

                        {/* Loading state */}
                        {response.isLoading && response.isStreaming && (
                            <div className="loading-wrapper">
                                <div className="loading-spinner" />
                                <span className="loading-text">{response.loadingText}</span>
                            </div>
                        )}

                        {/* Feedback — once the reply is done and the backend
                            has named its run (the chat.id event) */}
                        {response.chatId && !response.isStreaming && (
                            <ChatFeedback key={response.chatId} chatId={response.chatId} sessionId={sessionId} logRecord={response.logRecord} />
                        )}

                        {/* AI disclaimer - show on last message */}
                        {index === messages.length - 1 && !response.isLoading && !response.isStreaming && (
                            (response.sections?.length > 0 || response.text) && (
                                // The reply bubble's box at full width, so this ends where reply text does
                                <div className="message-bubble response w-full text-left">
                                    {/* opening it adds the list below the fold, so follow it down */}
                                    <details
                                        className="text-sm text-[var(--text-muted)]"
                                        onToggle={(e) => e.currentTarget.open && scrollToBottom()}
                                    >
                                        <summary className="list-none [&::-webkit-details-marker]:hidden italic cursor-pointer hover:text-[var(--text-hover)]">
                                            This assistant can make mistakes. Learn more
                                        </summary>
                                        <ul className="list-disc pl-5 mt-1 space-y-0.5">
                                            <li>Limited eval tests</li>
                                            <li>Basic data cleaning</li>
                                            <li>Simple algorithm implementations</li>
                                            <li>Ongoing improvements (no retry yet)</li>
                                        </ul>
                                    </details>
                                </div>
                            )
                        )}

                    </div>
                </div>
            ))}
        </div>
    )
}

export default ChatMessages
