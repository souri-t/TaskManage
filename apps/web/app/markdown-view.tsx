"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [html, setHtml] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    import("shiki").then(({ codeToHtml }) =>
      codeToHtml(code, {
        lang: language || "text",
        themes: { light: "github-light", dark: "github-dark" },
      })
        .then((value) => active && setHtml(value))
        .catch(() => active && setHtml(null)),
    );
    return () => {
      active = false;
    };
  }, [code, language]);

  const copy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };

  return (
    <div className="code-block">
      <div className="code-toolbar">
        <span>{language || "text"}</span>
        <button type="button" className="text-button" onClick={copy}>
          {copied ? "コピー済み" : "コピー"}
        </button>
      </div>
      {html ? (
        <div
          className="shiki-output"
          // Shiki escapes source text and produces only highlighted code markup.
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <pre>
          <code>{code}</code>
        </pre>
      )}
    </div>
  );
}

export function MarkdownView({ value }: { value: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          code({ className, children, ...props }) {
            const match = /language-([\w-]+)/.exec(className || "");
            const code = String(children).replace(/\n$/, "");
            if (match || code.includes("\n")) {
              return <CodeBlock language={match?.[1] || "text"} code={code} />;
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          a({ href, children }) {
            const safe = href?.startsWith("http://") || href?.startsWith("https://");
            return safe ? (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            ) : (
              <span>{children}</span>
            );
          },
          img({ alt }) {
            return <span className="blocked-embed">[画像: {alt || "説明なし"}]</span>;
          },
        }}
      >
        {value}
      </ReactMarkdown>
    </div>
  );
}
