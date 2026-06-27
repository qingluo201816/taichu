import type { JSONContent } from "@tiptap/react";

type InlineToken = {
  type: "text";
  text: string;
  marks?: { type: "bold" | "italic" }[];
};

export function markdownToTiptapContent(markdown: string): JSONContent {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const content: JSONContent[] = [];
  let paragraph: string[] = [];

  const flushParagraph = () => {
    const text = paragraph.join("\n").trim();
    if (text) {
      content.push({
        type: "paragraph",
        content: parseInline(text),
      });
    }
    paragraph = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    const quote = /^>\s?(.+)$/.exec(line);

    if (!line.trim()) {
      flushParagraph();
      continue;
    }

    if (/^---+$/.test(line.trim())) {
      flushParagraph();
      content.push({ type: "horizontalRule" });
      continue;
    }

    if (heading) {
      flushParagraph();
      content.push({
        type: "heading",
        attrs: { level: heading[1].length },
        content: parseInline(heading[2]),
      });
      continue;
    }

    if (quote) {
      flushParagraph();
      content.push({
        type: "blockquote",
        content: [
          {
            type: "paragraph",
            content: parseInline(quote[1]),
          },
        ],
      });
      continue;
    }

    paragraph.push(line);
  }

  flushParagraph();
  return {
    type: "doc",
    content: content.length ? content : [{ type: "paragraph" }],
  };
}

export function tiptapContentToMarkdown(content: JSONContent): string {
  const blocks = (content.content ?? []).map(nodeToMarkdown).filter(Boolean);
  return `${blocks.join("\n\n").trimEnd()}\n`;
}

function nodeToMarkdown(node: JSONContent): string {
  if (node.type === "heading") {
    const level = Number(node.attrs?.level ?? 1);
    return `${"#".repeat(Math.max(1, Math.min(level, 3)))} ${inlineToMarkdown(
      node.content,
    )}`;
  }

  if (node.type === "blockquote") {
    const text = (node.content ?? []).map(nodeToMarkdown).join("\n");
    return text
      .split("\n")
      .map(line => `> ${line}`)
      .join("\n");
  }

  if (node.type === "horizontalRule") {
    return "---";
  }

  if (node.type === "paragraph") {
    return inlineToMarkdown(node.content);
  }

  return inlineToMarkdown(node.content);
}

function inlineToMarkdown(content: JSONContent[] | undefined): string {
  return (content ?? [])
    .map(node => {
      if (node.type !== "text") {
        return inlineToMarkdown(node.content);
      }
      let text = node.text ?? "";
      for (const mark of node.marks ?? []) {
        if (mark.type === "bold") {
          text = `**${text}**`;
        }
        if (mark.type === "italic") {
          text = `*${text}*`;
        }
      }
      return text;
    })
    .join("");
}

function parseInline(text: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      tokens.push({ type: "text", text: text.slice(lastIndex, match.index) });
    }

    const raw = match[0];
    if (raw.startsWith("**")) {
      tokens.push({
        type: "text",
        text: raw.slice(2, -2),
        marks: [{ type: "bold" }],
      });
    } else {
      tokens.push({
        type: "text",
        text: raw.slice(1, -1),
        marks: [{ type: "italic" }],
      });
    }
    lastIndex = match.index + raw.length;
  }

  if (lastIndex < text.length) {
    tokens.push({ type: "text", text: text.slice(lastIndex) });
  }

  return tokens;
}
