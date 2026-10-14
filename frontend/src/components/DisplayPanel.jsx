import { useState, useEffect, lazy, Suspense } from "react";

// Dynamic imports for code splitting
const ChatBot = lazy(() => import("@/components/ChatBot"));
const BlogPost = lazy(() => import("@/components/BlogPost"));
const ChatReviewPage = lazy(() => import("@/pages/ChatReviewPage"));

// Loading component
const LoadingSpinner = () => (
    <div className="absolute inset-0 flex items-center justify-center">
        <div className="loading-spinner"></div>
        <span className="ml-2 text-[var(--text-hover)]">Loading...</span>
    </div>
);

const DisplayPanel = ({ activeView }) => {
    // Once a view has been visited, keep it mounted (just hidden) instead of
    // unmounting it — switching tabs used to unmount ChatBot entirely,
    // losing the conversation and (since sessions are created on mount)
    // spawning a brand new session every time you switched back.
    //
    // The chat's own slide-up plays on each view as it is shown: an animation
    // restarts whenever its element comes back from display: none (`hidden`),
    // so switching to an already-loaded view replays it too.
    const [visited, setVisited] = useState(() => new Set([activeView]));

    useEffect(() => {
        setVisited(prev => (prev.has(activeView) ? prev : new Set(prev).add(activeView)));
    }, [activeView]);

    return (
        <div className="relative h-full w-full overflow-hidden">
            {visited.has('chat') && (
                <div className={`absolute inset-0 h-full w-full min-h-0 animate-slide-up-smooth ${activeView === 'chat' ? '' : 'hidden'}`}>
                    <Suspense fallback={<LoadingSpinner />}>
                        <ChatBot />
                    </Suspense>
                </div>
            )}
            {['bookshelf', 'airglider', 'planjane'].map(page => visited.has(page) && (
                <div key={page} className={`absolute inset-0 h-full w-full min-h-0 animate-slide-up-smooth overflow-y-auto ${activeView === page ? '' : 'hidden'}`}>
                    <Suspense fallback={<LoadingSpinner />}>
                        <BlogPost page={page} />
                    </Suspense>
                </div>
            ))}
            {visited.has('review') && (
                <div className={`absolute inset-0 h-full w-full min-h-0 animate-slide-up-smooth overflow-y-auto ${activeView === 'review' ? '' : 'hidden'}`}>
                    <Suspense fallback={<LoadingSpinner />}>
                        <ChatReviewPage />
                    </Suspense>
                </div>
            )}
        </div>
    );
};

export default DisplayPanel;
