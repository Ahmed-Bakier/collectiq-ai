import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { errorMessage } from "../../api/client";
import { useAgentRun } from "../../api/hooks";
import type { AgentRunResponse } from "../../api/types";

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  run?: AgentRunResponse;
  error?: string;
}

interface AssistantContextValue {
  messages: ChatMessage[];
  isRunning: boolean;
  send: (text: string) => void;
  clear: () => void;
}

const AssistantContext = createContext<AssistantContextValue | null>(null);

export function AssistantProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const { mutate, isPending } = useAgentRun();

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: "user", text: trimmed }]);
      mutate(trimmed, {
        onSuccess: (run) =>
          setMessages((previous) => [...previous, { id: run.run_id, role: "agent", text: run.summary, run }]),
        onError: (error) =>
          setMessages((previous) => [
            ...previous,
            { id: crypto.randomUUID(), role: "agent", text: "", error: errorMessage(error) },
          ]),
      });
    },
    [mutate],
  );

  const clear = useCallback(() => setMessages([]), []);
  const value = useMemo(() => ({ messages, isRunning: isPending, send, clear }), [messages, isPending, send, clear]);

  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
}

export function useAssistant(): AssistantContextValue {
  const context = useContext(AssistantContext);
  if (!context) throw new Error("useAssistant must be used inside AssistantProvider.");
  return context;
}
