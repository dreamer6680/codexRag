import React, { type ReactNode } from "react";

export function DocumentMarkdown({ markdown }: { markdown: string }) {
  const nodes = renderBlocks(markdown);

  if (!nodes.length) {
    return <p className="text-sm text-zinc-500">暂无 Markdown 内容。</p>;
  }

  return <div className="space-y-4 text-sm leading-7">{nodes}</div>;
}

function renderBlocks(markdown: string): ReactNode[] {
  const lines = markdown.split(/\r?\n/);
  const nodes: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      nodes.push(
        <pre key={nodes.length} className="overflow-auto rounded-md bg-zinc-950 p-4 text-xs leading-6 text-zinc-100">
          <code>{code.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    if (isTableHeader(line, lines[index + 1])) {
      const tableLines = [line];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        tableLines.push(lines[index]);
        index += 1;
      }
      nodes.push(renderTable(tableLines, nodes.length));
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      const content = inlineMarkdown(heading[2]);
      const key = nodes.length;
      const level = heading[1].length;
      if (level === 1) nodes.push(<h1 key={key} className="text-2xl font-semibold tracking-tight">{content}</h1>);
      else if (level === 2) nodes.push(<h2 key={key} className="text-xl font-semibold tracking-tight">{content}</h2>);
      else if (level === 3) nodes.push(<h3 key={key} className="text-base font-semibold">{content}</h3>);
      else nodes.push(<h4 key={key} className="text-sm font-semibold">{content}</h4>);
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^[-*]\s+/, ""));
        index += 1;
      }
      nodes.push(
        <ul key={nodes.length} className="list-disc space-y-1 pl-5 text-zinc-700">
          {items.map((item, itemIndex) => <li key={itemIndex}>{inlineMarkdown(item)}</li>)}
        </ul>,
      );
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      nodes.push(
        <ol key={nodes.length} className="list-decimal space-y-1 pl-5 text-zinc-700">
          {items.map((item, itemIndex) => <li key={itemIndex}>{inlineMarkdown(item)}</li>)}
        </ol>,
      );
      continue;
    }

    if (line.startsWith(">")) {
      nodes.push(
        <blockquote key={nodes.length} className="border-l-2 border-amber-400 bg-amber-50 px-4 py-2 text-amber-950">
          {inlineMarkdown(line.replace(/^>\s?/, ""))}
        </blockquote>,
      );
      index += 1;
      continue;
    }

    if (/^---+$/.test(line.trim())) {
      nodes.push(<hr key={nodes.length} className="border-zinc-200" />);
      index += 1;
      continue;
    }

    nodes.push(<p key={nodes.length} className="text-zinc-700">{inlineMarkdown(line)}</p>);
    index += 1;
  }

  return nodes;
}

function isTableHeader(line: string, separator?: string) {
  if (!separator || !line.includes("|")) return false;
  const cells = separator.trim().replace(/^\||\|$/g, "").split("|");
  return cells.length > 0 && cells.every(cell => /^\s*:?-{3,}:?\s*$/.test(cell));
}

function renderTable(lines: string[], key: number) {
  const rows = lines.map(splitTableRow);
  const [head, ...body] = rows;

  return (
    <div key={key} className="overflow-x-auto rounded-md border border-zinc-200">
      <table className="w-full text-left text-sm">
        <thead className="bg-zinc-50">
          <tr>{head.map((cell, cellIndex) => <th key={cellIndex} className="border-b px-3 py-2 font-medium">{inlineMarkdown(cell)}</th>)}</tr>
        </thead>
        <tbody>
          {body.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-b last:border-0">
              {row.map((cell, cellIndex) => <td key={cellIndex} className="px-3 py-2 text-zinc-700">{inlineMarkdown(cell)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function splitTableRow(line: string) {
  return line.trim().replace(/^\||\|$/g, "").split("|").map(cell => cell.trim());
}

function inlineMarkdown(text: string): ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index} className="rounded bg-zinc-100 px-1 py-0.5 font-mono text-xs">{part.slice(1, -1)}</code>;
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return <span key={index}>{part}</span>;
  });
}
