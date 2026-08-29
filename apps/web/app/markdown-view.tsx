"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";

function DiagramBlock({ engine, source }: { engine: "mermaid" | "plantuml"; source: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      fetch("/api/v1/diagram-renders", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ engine, source }) })
        .then(async (response) => response.ok ? response.json() : Promise.reject(await response.json()))
        .then((result) => setUrl(result.url))
        .catch((reason) => setError(reason.detail || "図の描画に失敗しました"));
      observer.disconnect();
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [engine, source, attempt]);
  return <div className="diagram-block" ref={ref}>{url ? <img src={url} alt={`${engine} diagram`} loading="lazy" /> : error ? <details className="diagram-error"><summary>{error}</summary><pre>{source}</pre><button type="button" className="text-button" onClick={() => { setError(""); setAttempt((value) => value + 1); }}>再試行</button></details> : <span>図を読み込み中…</span>}</div>;
}

function AttachmentImage({ findingId, artifactId, alt }: { findingId?: string; artifactId: string; alt: string }) {
  const [expanded, setExpanded] = useState(false);
  if (!findingId) return <span className="blocked-embed">[画像: {alt || "説明なし"}]</span>;
  const src = `/api/v1/findings/${findingId}/artifacts/${artifactId}`;
  return <><button type="button" className="attachment-image" onClick={() => setExpanded(true)}><img src={src} alt={alt} loading="lazy" /></button>{expanded && <div className="image-lightbox" role="dialog" aria-modal="true" aria-label={alt || "添付画像"} onClick={() => setExpanded(false)}><img src={src} alt={alt} /></div>}</>;
}

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [html, setHtml] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => { let active = true; import("shiki").then(({ codeToHtml }) => codeToHtml(code, { lang: language || "text", themes: { light: "github-light", dark: "github-dark" } }).then((value) => active && setHtml(value)).catch(() => active && setHtml(null))); return () => { active = false; }; }, [code, language]);
  const copy = async () => { await navigator.clipboard.writeText(code); setCopied(true); window.setTimeout(() => setCopied(false), 1200); };
  return <div className="code-block"><div className="code-toolbar"><span>{language || "text"}</span><button type="button" className="text-button" onClick={copy}>{copied ? "コピー済み" : "コピー"}</button></div>{html ? <div className="shiki-output" dangerouslySetInnerHTML={{ __html: html }} /> : <pre><code>{code}</code></pre>}</div>;
}

export function MarkdownView({ value, findingId }: { value: string; findingId?: string }) {
  return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml urlTransform={(url) => /^attachment:\/\/ART-\d{6,}$/.test(url) ? url : defaultUrlTransform(url)} components={{
    code({ className, children, ...props }) { const match = /language-([\w-]+)/.exec(className || ""); const code = String(children).replace(/\n$/, ""); const language = match?.[1] || "text"; if (language === "mermaid" || language === "plantuml") return <DiagramBlock engine={language} source={code} />; if (match || code.includes("\n")) return <CodeBlock language={language} code={code} />; return <code className={className} {...props}>{children}</code>; },
    a({ href, children }) { const safe = href?.startsWith("http://") || href?.startsWith("https://"); return safe ? <a href={href} target="_blank" rel="noreferrer">{children}</a> : <span>{children}</span>; },
    img({ alt, src }) { const match = /^attachment:\/\/(ART-\d{6,})$/.exec(typeof src === "string" ? src : ""); return match ? <AttachmentImage findingId={findingId} artifactId={match[1]} alt={alt || ""} /> : <span className="blocked-embed">[画像: {alt || "説明なし"}]</span>; },
  }}>{value}</ReactMarkdown></div>;
}
