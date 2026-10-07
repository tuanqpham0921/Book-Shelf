import { useMemo } from 'react'
import hljs from 'highlight.js/lib/core'
import sql from 'highlight.js/lib/languages/sql'
import json from 'highlight.js/lib/languages/json'
import python from 'highlight.js/lib/languages/python'
import javascript from 'highlight.js/lib/languages/javascript'

// Only these grammars ship (~25 KB with the core). Add one here to highlight
// it anywhere — task details and reply code fences both come through here.
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('json', json)
hljs.registerLanguage('python', python)
hljs.registerLanguage('javascript', javascript)

// A highlighted <pre>. Colors come from the --code-* tokens, so they follow
// the app's color toggle like every other accent. An unknown or missing
// language renders as plain text rather than guessing.
function CodeBlock({ language, children, className = '' }) {
    const text = String(children ?? '').replace(/\n$/, '')
    // hljs escapes the text before wrapping tokens in spans, so the HTML is safe
    const html = useMemo(
        () => (language && hljs.getLanguage(language)
            ? hljs.highlight(text, { language }).value
            : null),
        [text, language]
    )

    return (
        <pre className={`code-block ${className}`}>
            {html != null
                ? <code dangerouslySetInnerHTML={{ __html: html }} />
                : <code>{text}</code>}
        </pre>
    )
}

// For react-markdown's `components`: a fenced block arrives as
// <pre><code class="language-x">, so swapping the <pre> catches blocks only and
// leaves inline `code` alone.
export function MarkdownPre({ children }) {
    const { className = '', children: text } = children?.props ?? {}
    const language = /language-(\w+)/.exec(className)?.[1]
    return <CodeBlock language={language}>{text}</CodeBlock>
}

export default CodeBlock
