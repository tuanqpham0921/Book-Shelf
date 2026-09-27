import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import IconButton from './IconButton'

// Generic overlay dialog, centered on every screen — full width less a 16px
// gutter on phones, capped at `max-w-lg` from `sm:` up. Reused for anything
// that needs "more info than fits inline" (book details, issue reports, ...).
// Portaled to <body>: the chat list's fade (`mask-image`, chat.css) clips
// everything drawn inside it, `position: fixed` overlays included.
function Modal({ isOpen, onClose, title, children, className = '' }) {
    useEffect(() => {
        if (!isOpen) return
        const handleKeyDown = (event) => {
            if (event.key === 'Escape') onClose()
        }
        document.addEventListener('keydown', handleKeyDown)
        return () => document.removeEventListener('keydown', handleKeyDown)
    }, [isOpen, onClose])

    if (!isOpen) return null

    return createPortal(
        <div
            className="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 flex items-center justify-center p-4"
            onClick={onClose}
        >
            <div
                className={`bg-[var(--bg-primary)] w-full sm:max-w-lg rounded-2xl shadow-2xl max-h-[85vh] flex flex-col animate-slide-up ${className}`}
                onClick={(event) => event.stopPropagation()}
            >
                <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-[var(--border-light)] flex-shrink-0">
                    <h2 className="font-semibold text-[var(--text-active)] line-clamp-2">{title}</h2>
                    <IconButton onClick={onClose} className="flex-shrink-0">
                        <X size={18} />
                    </IconButton>
                </div>

                <div className="px-5 py-4 overflow-y-auto flex-1">
                    {children}
                </div>
            </div>
        </div>,
        document.body
    )
}

export default Modal
