import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/** Links in rendered markdown come from model output or user notes — treat
 * them as untrusted: open in a new tab, never hand the opener over. */
const COMPONENTS: Components = {
  a: ({ children, ...props }) => (
    <a {...props} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  ),
};

const PLUGINS = [remarkGfm];

interface MarkdownProps {
  children: string;
  /** Styling hook; every caller keeps `markdown-view` as the base. */
  className?: string;
}

/** Renders a markdown string as React elements. Raw HTML is deliberately not
 * enabled (no `rehype-raw`): assistant output and DM notes are *data*, not
 * markup, so nothing in a message can inject elements into the app. */
export function Markdown({ children, className = "markdown-view" }: MarkdownProps) {
  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={PLUGINS} components={COMPONENTS}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
