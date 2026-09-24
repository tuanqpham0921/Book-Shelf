import { useState } from 'react'
import api from '@/api'
import { ThumbsUp, ThumbsDown, MessageCircle, Flag, Sparkles, ChevronDown } from 'lucide-react';
import Button from '@/design-system/Button'
import IconButton from '@/design-system/IconButton'
import Badge from '@/design-system/Badge'
import Modal from '@/design-system/Modal'
import Dropdown from '@/design-system/Dropdown'
import DropdownItem from '@/design-system/DropdownItem'
import { FEEDBACK_CATEGORIES } from '@/data/feedbackCategories'

// Keep in sync with AppConfig.FEEDBACK_MAX_COMMENTS / FEEDBACK_COMMENT_LENGTH.
const MAX_COMMENTS = 20
const MAX_COMMENT_LENGTH = 500

// Popup for adding {title, message, positive} comments to one response, the
// same shape the review page files. Each submit saves at once, and the list
// below it is what has been saved.
function FeedbackModal({ comments, isSaving, error, onAddComment, isOpen, onClose }) {
    const [category, setCategory] = useState('')
    const [positive, setPositive] = useState(false)
    const [message, setMessage] = useState('')
    const isFull = comments.length >= MAX_COMMENTS

    async function handleSubmit() {
        const trimmed = message.trim()
        if (!trimmed || isSaving || isFull) return
        if (await onAddComment({ title: category || null, message: trimmed, positive })) {
            setMessage('')
        }
    }

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Report on this response">
            <div className="flex gap-2 mb-3">
                <Button
                    variant="secondary"
                    tone="negative"
                    active={!positive}
                    onClick={() => setPositive(false)}
                    className="flex-1"
                >
                    <Flag size={14} /> Issue
                </Button>
                <Button
                    variant="secondary"
                    tone="positive"
                    active={positive}
                    onClick={() => setPositive(true)}
                    className="flex-1"
                >
                    <Sparkles size={14} /> Praise
                </Button>
            </div>

            <Dropdown
                className="w-full mb-3"
                panelClassName="w-full max-h-48 overflow-y-auto rounded-md"
                trigger={({ toggle }) => (
                    <button
                        type="button"
                        onClick={toggle}
                        style={{ fontSize: '0.875rem' }}
                        className="w-full flex items-center justify-between border border-[var(--border-light)] rounded-md p-2 bg-[var(--bg-primary)] text-left"
                    >
                        <span className={category ? 'text-[var(--text-active)]' : 'text-[var(--text-muted)]'}>
                            {category || 'Select a category (optional)'}
                        </span>
                        <ChevronDown size={16} className="text-[var(--text-muted)]" />
                    </button>
                )}
            >
                {({ close }) => FEEDBACK_CATEGORIES.map((c) => (
                    <DropdownItem
                        key={c}
                        selected={c === category}
                        onClick={() => { setCategory(c); close() }}
                    >
                        {c}
                    </DropdownItem>
                ))}
            </Dropdown>

            <textarea
                value={message}
                onChange={(e) => {
                    if (e.target.value.length <= MAX_COMMENT_LENGTH) {
                        setMessage(e.target.value)
                    }
                }}
                placeholder="What was good or bad about this response?"
                rows={3}
                maxLength={MAX_COMMENT_LENGTH}
                // Inline size needed to beat base.css's unlayered textarea font-size reset (mobile zoom guard)
                style={{ fontSize: '0.875rem' }}
                className="w-full text-sm border border-[var(--border-light)] rounded-md p-2 resize-none focus:outline-1 focus:outline-[var(--border-medium)]"
            />
            <div className="flex justify-end mb-2 px-2">
                <span className={`text-xs ${message.length >= MAX_COMMENT_LENGTH - 50 ? 'text-[var(--accent-negative)]' : 'text-[var(--text-inactive)]'}`}>
                    {message.length}/{MAX_COMMENT_LENGTH}
                </span>
            </div>

            <div className="flex items-center justify-between mb-4">
                {error && <span className="text-xs text-[var(--accent-negative)] italic">{error}</span>}
                <Button
                    variant="primary"
                    onClick={handleSubmit}
                    disabled={isSaving || !message.trim() || isFull}
                    className="ml-auto"
                >
                    {isSaving ? 'Submitting...' : 'Submit'}
                </Button>
            </div>

            <div className="border-t border-[var(--border-light)] pt-3">
                <h3 className="text-xs font-semibold text-[var(--text-inactive)] uppercase mb-2">
                    Reports on this response
                </h3>
                {comments.length === 0 && (
                    <div className="text-xs text-[var(--text-muted)] italic">No reports yet.</div>
                )}
                <div className="flex flex-col gap-2">
                    {[...comments].reverse().map((comment, i) => (
                        <div
                            key={i}
                            className="border border-[var(--border-light)] rounded-md p-2 bg-[var(--bg-secondary)]"
                        >
                            {comment.title && (
                                <Badge tone={comment.positive ? 'positive' : 'negative'} className="mb-1">
                                    {comment.title}
                                </Badge>
                            )}
                            <div className="text-xs text-[var(--text-hover)] whitespace-pre-wrap break-words">{comment.message}</div>
                        </div>
                    ))}
                </div>
            </div>
        </Modal>
    )
}

// Like / dislike / report controls under a finished reply, for this
// session's own chat run. The backend keeps one feedback row per run and
// session and replaces it whole on every save, so each save sends the thumb
// and the comments together. A change shows straight away and is put back
// if the save fails, including the 404 for a turn the backend hasn't
// finished recording yet, so trying again works.
function ChatFeedback({ chatId, sessionId }) {
    const [feedback, setFeedback] = useState({ liked: null, comments: [] })
    const [showModal, setShowModal] = useState(false)
    const [isSaving, setIsSaving] = useState(false)
    const [error, setError] = useState(null)

    async function save(next) {
        const previous = feedback
        setFeedback(next)
        setError(null)
        setIsSaving(true)
        try {
            await api.sendFeedback(sessionId, chatId, next)
            return true
        } catch (err) {
            console.error('Feedback not saved:', err)
            setFeedback(previous)
            setError('Could not save feedback')
            return false
        } finally {
            setIsSaving(false)
        }
    }

    function handleReaction(liked) {
        if (isSaving || feedback.liked === liked) return
        save({ ...feedback, liked })
    }

    // ml-6 starts the row where the reply's text and cards do: the bubble's
    // 12px margin plus its 12px padding (styles/chat.css)
    return (
        <div className="ml-6">
            <div className="flex items-center">
                <IconButton
                    onClick={() => handleReaction(true)}
                    disabled={isSaving}
                    title="Good response"
                    tone="positive"
                    active={feedback.liked === true}
                >
                    <ThumbsUp size={16}/>
                </IconButton>
                <IconButton
                    onClick={() => handleReaction(false)}
                    disabled={isSaving}
                    title="Bad response"
                    tone="negative"
                    active={feedback.liked === false}
                >
                    <ThumbsDown size={16}/>
                </IconButton>
                <IconButton
                    onClick={() => setShowModal(true)}
                    disabled={isSaving}
                    title="Report an issue"
                >
                    <MessageCircle size={16}/>
                </IconButton>
                {error && !showModal && (
                    <span className="text-xs text-[var(--accent-negative)] italic">{error}</span>
                )}
            </div>

            <FeedbackModal
                comments={feedback.comments}
                isSaving={isSaving}
                error={error}
                onAddComment={(comment) => save({ ...feedback, comments: [...feedback.comments, comment] })}
                isOpen={showModal}
                onClose={() => setShowModal(false)}
            />
        </div>
    )
}

export default ChatFeedback
