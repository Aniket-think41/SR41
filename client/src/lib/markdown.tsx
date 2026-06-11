/**
 * Minimal markdown renderer for Notes and SKILL.md content.
 * Deliberately dependency-free for v1; swap for TipTap's renderer or a
 * full parser when rich editing lands (frontend spec §1 names TipTap).
 * Renders React elements — no dangerouslySetInnerHTML.
 */

import React, { type ReactNode } from "react";

function inline(text: string, keyBase: string): ReactNode[] {
  // bold → code → links, applied by splitting progressively
  const out: ReactNode[] = [];
  // Tokenize `code`, **bold**, [text](url)
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    const key = `${keyBase}-${i++}`;
    if (tok.startsWith("`")) out.push(<code key={key}>{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("**")) out.push(<strong key={key}>{tok.slice(2, -2)}</strong>);
    else {
      const mm = /\[([^\]]+)\]\(([^)]+)\)/.exec(tok);
      if (mm)
        out.push(
          <a key={key} href={mm[2]} target="_blank" rel="noreferrer">
            {mm[1]}
          </a>
        );
    }
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ source }: { source: string }) {
  const lines = source.split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("```")) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      i++; // closing fence
      blocks.push(
        <pre key={key++}>
          <code>{buf.join("\n")}</code>
        </pre>
      );
      continue;
    }

    const h = /^(#{1,3})\s+(.*)/.exec(line);
    if (h) {
      const Tag = (["h1", "h2", "h3"] as const)[h[1].length - 1];
      blocks.push(<Tag key={key++}>{inline(h[2], `h${key}`)}</Tag>);
      i++;
      continue;
    }

    if (/^(-{3,}|\*{3,})\s*$/.test(line)) {
      blocks.push(<hr key={key++} />);
      i++;
      continue;
    }

    if (line.startsWith("> ")) {
      const buf: string[] = [];
      while (i < lines.length && lines[i].startsWith("> ")) buf.push(lines[i++].slice(2));
      blocks.push(<blockquote key={key++}>{inline(buf.join(" "), `q${key}`)}</blockquote>);
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^[-*]\s+/, ""));
      blocks.push(
        <ul key={key++}>
          {items.map((it, j) => (
            <li key={j}>{inline(it, `li${key}-${j}`)}</li>
          ))}
        </ul>
      );
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) items.push(lines[i++].replace(/^\d+\.\s+/, ""));
      blocks.push(
        <ol key={key++}>
          {items.map((it, j) => (
            <li key={j}>{inline(it, `oli${key}-${j}`)}</li>
          ))}
        </ol>
      );
      continue;
    }

    if (line.trim() === "") {
      i++;
      continue;
    }

    // paragraph: gather until blank line / block start
    const buf: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^(#{1,3})\s|^[-*]\s|^\d+\.\s|^>|^```/.test(lines[i])
    )
      buf.push(lines[i++]);
    blocks.push(<p key={key++}>{inline(buf.join(" "), `p${key}`)}</p>);
  }

  return <div className="prose-md">{blocks}</div>;
}
