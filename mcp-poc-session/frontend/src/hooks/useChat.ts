import { useState, useRef } from "react";

export interface ContentBlock {
  kind: "text" | "chart";
  text?: string;
  // conv-assist-answer embed URL. For live answers it comes from the stream;
  // for history it's rebuilt server-side via loadAnswer. Either way it renders
  // through the same startAutoMCPFrameRenderer iframe path.
  url?: string;
  answerTitle?: string;
}

// A reasoning step: the heading (e.g. "Fetching dataset context") plus the
// reasoning text streamed under it, grouped like the Spotter UI shows them.
export interface ThinkingStep {
  heading: string;
  text: string;
}

export interface Message {
  id: string;
  role: "user" | "bot";
  text: string;            // plain text for history saving / loading dots check
  blocks?: ContentBlock[]; // ordered content for bot messages
  source?: "thoughtspot";
  thinkingStep?: string;
  thinkingText?: string;
  streaming?: boolean;
  streamingDone?: boolean;
  fromHistory?: boolean;   // loaded from a past conversation (charts default collapsed)
  thinkingSteps?: ThinkingStep[]; // steps, each with its own heading + reasoning
}

// One entry per saved conversation in the history list (GET /history). The full
// transcript is fetched separately via GET /history/{conversation_id}.
export interface HistoryItem {
  id: string;
  query: string;
  source: "thoughtspot";
  conversation_id?: string;
  created_at: string;
  turn_count?: number;
}

// Shape returned by GET /history/{conversation_id} — rebuilt server-side from
// getConversation + loadAnswer. Faithful to the original response: full thinking
// trace + every chart (intermediate + final), in order.
export interface TurnBlock {
  kind: "text" | "chart";
  text?: string;
  frame_url?: string;
  title?: string;
}
export interface ConversationTurn {
  query: string;
  thinking_text: string;
  blocks: TurnBlock[];
}

export type ChatMode = "mcp" | "api" | "claude_mcp";

export function useChat(mode: ChatMode = "mcp", modelId?: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  // True while the user is viewing a past conversation — drives the
  // "data may have changed" banner, since re-rendered charts reflect live data.
  const [viewingHistory, setViewingHistory] = useState(false);
  const conversationIdRef = useRef<string | undefined>(undefined);

  const sendMessage = async (query: string) => {
    setViewingHistory(false);
    const userMsg: Message = { id: crypto.randomUUID(), role: "user", text: query };
    const botId = crypto.randomUUID();
    const botMsg: Message = {
      id: botId,
      role: "bot",
      text: "",
      blocks: [],
      streaming: true,
      streamingDone: false,
    };

    setMessages((prev) => [...prev, userMsg, botMsg]);
    setLoading(true);

    try {
      const res = await fetch("/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, conversation_id: conversationIdRef.current, mode, data_source_id: modelId }),
      });

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const raw = line.slice(5).trim();
          if (!raw || raw === "[DONE]") continue;

          try {
            const event = JSON.parse(raw);

            if (event.type === "conversation_id") {
              conversationIdRef.current = event.conversation_id;
            }

            if (event.type === "thinking") {
              // New step heading — start a new step.
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === botId
                    ? {
                        ...m,
                        thinkingStep: event.text,
                        thinkingSteps: [...(m.thinkingSteps ?? []), { heading: event.text, text: "" }],
                      }
                    : m
                )
              );
            }

            if (event.type === "thinking_text") {
              // Reasoning text — append it to the current (last) step.
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== botId) return m;
                  const steps = [...(m.thinkingSteps ?? [])];
                  if (steps.length === 0) steps.push({ heading: "Thinking", text: "" });
                  const last = steps[steps.length - 1];
                  steps[steps.length - 1] = { ...last, text: last.text + (event.text ?? "") };
                  return { ...m, thinkingSteps: steps, thinkingText: (m.thinkingText ?? "") + (event.text ?? "") };
                })
              );
            }

            if (event.type === "token") {
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== botId) return m;
                  const blocks = [...(m.blocks ?? [])];
                  const last = blocks[blocks.length - 1];
                  if (last?.kind === "text") {
                    blocks[blocks.length - 1] = { ...last, text: (last.text ?? "") + (event.text ?? "") };
                  } else {
                    blocks.push({ kind: "text", text: event.text ?? "" });
                  }
                  return { ...m, text: m.text + (event.text ?? ""), blocks };
                })
              );
            }

            if (event.type === "frame_url") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === botId
                    ? {
                        ...m,
                        blocks: [
                          ...(m.blocks ?? []),
                          { kind: "chart", url: event.frame_url, answerTitle: event.answer_title },
                        ],
                      }
                    : m
                )
              );
            }

            if (event.type === "done") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === botId
                    ? { ...m, streaming: false, streamingDone: true, thinkingStep: undefined }
                    : m
                )
              );
            }
          } catch {
            // non-JSON line
          }
        }
      }
    } catch (err) {
      console.error("Chat error:", err);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === botId
            ? { ...m, text: "Error — check console.", streaming: false }
            : m
        )
      );
    } finally {
      setLoading(false);
    }
  };

  const _turnToMessages = (turn: ConversationTurn): Message[] => {
    // Preserve original order: interleaved text + intermediate/final charts.
    const blocks: ContentBlock[] = (turn.blocks ?? []).map((b) =>
      b.kind === "chart"
        ? { kind: "chart", url: b.frame_url, answerTitle: b.title }
        : { kind: "text", text: b.text }
    );
    const plainText = blocks.filter((b) => b.kind === "text").map((b) => b.text ?? "").join("");
    return [
      { id: crypto.randomUUID(), role: "user", text: turn.query },
      {
        id: crypto.randomUUID(),
        role: "bot",
        source: "thoughtspot",
        text: plainText,
        blocks,
        thinkingText: turn.thinking_text || undefined,
        streaming: false,
        streamingDone: true,
        fromHistory: true,
      },
    ];
  };

  const loadConversation = async (item: HistoryItem) => {
    setViewingHistory(true);
    // Rebuild the whole conversation from the server: getConversation for the
    // transcript + reasoning, loadAnswer per answer for a renderable frame_url.
    const convId = item.conversation_id ?? item.id;
    conversationIdRef.current = convId;
    const res = await fetch(`/history/${convId}`);
    const data = await res.json();
    const msgs: Message[] = (data.turns as ConversationTurn[]).flatMap(_turnToMessages);
    setMessages((prev) => [...prev, ...msgs]);
  };

  const clearMessages = () => {
    setMessages([]);
    conversationIdRef.current = undefined;
    setViewingHistory(false);
  };

  return {
    messages,
    loading,
    viewingHistory,
    sendMessage,
    loadConversation,
    clearMessages,
    dismissHistoryBanner: () => setViewingHistory(false),
  };
}
