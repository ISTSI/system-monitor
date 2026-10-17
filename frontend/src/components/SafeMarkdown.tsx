import type { ReactNode } from 'react';

function inline(text: string): ReactNode[] {
  // Deliberately small Markdown subset: React text nodes escape raw HTML; assets
  // and links are rendered as text and cannot initiate remote network requests.
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g).map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith('*') && part.endsWith('*')) return <em key={index}>{part.slice(1, -1)}</em>;
    return part;
  });
}

export default function SafeMarkdown({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const blocks: ReactNode[] = [];
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];
    if (line.startsWith('```')) {
      const code = [];
      while (++index < lines.length && !lines[index].startsWith('```')) code.push(lines[index]);
      blocks.push(<pre key={index}><code>{code.join('\n')}</code></pre>);
    } else if (line.startsWith('### ')) blocks.push(<h4 key={index}>{inline(line.slice(4))}</h4>);
    else if (line.startsWith('## ')) blocks.push(<h3 key={index}>{inline(line.slice(3))}</h3>);
    else if (line.startsWith('# ')) blocks.push(<h2 key={index}>{inline(line.slice(2))}</h2>);
    else if (/^[-*] /.test(line)) {
      const items = [line.slice(2)];
      while (index + 1 < lines.length && /^[-*] /.test(lines[index + 1])) items.push(lines[++index].slice(2));
      blocks.push(<ul key={index}>{items.map((item, itemIndex) => <li key={itemIndex}>{inline(item)}</li>)}</ul>);
    } else if (line.startsWith('> ')) blocks.push(<blockquote key={index}>{inline(line.slice(2))}</blockquote>);
    else if (line.trim()) blocks.push(<p key={index}>{inline(line)}</p>);
  }
  return <div className="safe-markdown">{blocks.length ? blocks : <p className="muted">No documentation supplied.</p>}</div>;
}
