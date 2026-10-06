import { useState, useEffect } from 'react';
import Markdown, { defaultUrlTransform } from 'react-markdown';
import remarkGfm from 'remark-gfm';

// One entry per about page; each file lives at public/about/<page>/README.md
const PAGES = {
    bookshelf: { title: "An AI System for Book Discovery", date: "November 5, 2025" },
    airglider: { title: "Airglider" },
    planjane: { title: "PlanJane" },
};

const BlogPost = ({ page }) => {
    const [post, setPost] = useState(null);
    const [content, setContent] = useState('');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const loadBlogPost = async () => {
            try {
                const postMeta = { ...PAGES[page], contentFile: `/about/${page}/README.md` };

                // Load markdown content from public folder
                const response = await fetch(postMeta.contentFile);
                if (!response.ok) {
                    throw new Error('Failed to load blog post content');
                }
                const markdownContent = await response.text();

                setPost(postMeta);
                setContent(markdownContent);
            } catch (err) {
                console.error('Error loading blog post:', err);
                setError(err.message);
            } finally {
                setLoading(false);
            }
        };

        loadBlogPost();
    }, [page]);

    if (loading) {
        return (
            <div className="blog-container">
                <div className="flex justify-center items-center h-64">
                    <p className="text-[var(--text-inactive)]">Loading blog post...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="blog-container">
                <div className="flex justify-center items-center h-64">
                    <p className="text-[var(--accent-negative)]">Error: {error}</p>
                </div>
            </div>
        );
    }

    return (
        <div className="blog-container">
            <article className="blog-article">
                <header className="blog-header">
                    <h1 className="blog-title">
                        {post.title}
                    </h1>

                    <div className="blog-meta">
                        <span>By Tuan Pham</span>
                        {post.date && <span>{post.date}</span>}
                    </div>
                </header>

                <div className="markdown-body">
                    {/* Image paths resolve against the .md file, as they do on GitHub */}
                    <Markdown
                        remarkPlugins={[remarkGfm]}
                        urlTransform={(url, key) => defaultUrlTransform(
                            key === 'src' ? new URL(url, new URL(post.contentFile, window.location.origin)).pathname : url
                        )}
                    >
                        {content}
                    </Markdown>
                </div>

                <footer className="blog-footer">
                    <p>Thank you for reading.</p>
                </footer>
            </article>
        </div>
    );
};

export default BlogPost;
