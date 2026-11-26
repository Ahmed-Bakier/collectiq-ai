import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import Markdown from "react-markdown";
import { ArrowUp, CircleAlert, CircleCheck, LoaderCircle, Sparkles } from "lucide-react";
import type { AgentRunResponse, ToolCallRecord } from "../api/types";
import { useAssistant, type ChatMessage } from "../components/agent/AssistantContext";
import { ActionCardById } from "../components/approvals/ActionCard";
import { ErrorState, PageHeader } from "../components/common/ui";

const SUGGESTED_PROMPTS = [
  "Which invoices need my attention this week? Propose actions.",
  "Which clients are overdue and what should I do?",
  "Summarize my outstanding balance.",
];

const TOOL_LABELS: Record<string, string> = {
  get_invoice_analysis: "Read invoices from PayPal and ran the deterministic analysis",
  get_invoice_details: "Looked up an invoice",
  propose_action: "Proposed an action for your approval",
};

const RUN_STATUS_LABELS: Record<AgentRunResponse["status"], string> = {
  awaiting_approval: "Actions awaiting your approval",
  completed: "Completed",
  incomplete: "Stopped early",
};

export function AssistantPage() {
  const { messages, isRunning, send, clear } = useAssistant();
  const [input, setInput] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const handledQuery = useRef<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // A question typed on the dashboard arrives as ?q=... and is sent once.
  useEffect(() => {
    const query = searchParams.get("q");
    if (query && handledQuery.current !== query) {
      handledQuery.current = query;
      send(query);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, send, setSearchParams]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, isRunning]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isRunning || !input.trim()) return;
    send(input);
    setInput("");
  }

  return (
    <div className="flex flex-col">
      <PageHeader
        title="AI Assistant"
        description="Ask about your PayPal invoices. The agent analyzes, explains and proposes actions — you approve before anything is sent."
        actions={
          messages.length > 0 ? (
            <button
              type="button"
              onClick={clear}
              disabled={isRunning}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-muted hover:text-ink disabled:opacity-60"
            >
              Clear conversation
            </button>
          ) : undefined
        }
      />

      <div className="space-y-6 pb-4">
        {messages.length === 0 && !isRunning && <EmptyChat onPick={send} />}
        {messages.map((message) =>
          message.role === "user" ? (
            <UserBubble key={message.id} text={message.text} />
          ) : (
            <AgentMessage key={message.id} message={message} />
          ),
        )}
        {isRunning && (
          <div role="status" aria-live="polite" className="flex items-center gap-2 text-sm text-muted">
            <LoaderCircle className="size-4 animate-spin text-accent" aria-hidden />
            Reading your PayPal invoices and analyzing…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="sticky bottom-0 mt-2 border-t border-slate-200 bg-surface/95 py-4 backdrop-blur">
        <label htmlFor="assistant-input" className="sr-only">
          Message the collection agent
        </label>
        <div className="flex gap-2">
          <input
            id="assistant-input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            disabled={isRunning}
            maxLength={2000}
            placeholder="Ask about overdue invoices, priorities or next steps…"
            className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={isRunning || !input.trim()}
            aria-label="Send message"
            className="grid size-10 place-items-center rounded-lg bg-brand text-white hover:bg-brand/90 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
          >
            <ArrowUp className="size-4" aria-hidden />
          </button>
        </div>
      </form>
    </div>
  );
}

function EmptyChat({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
      <Sparkles className="mx-auto size-6 text-accent" aria-hidden />
      <p className="mt-3 font-medium text-ink">What would you like to know about your invoices?</p>
      <p className="mt-1 text-sm text-muted">Answers use live PayPal Sandbox data and CollectIQ's deterministic analysis.</p>
      <div className="mt-4 flex flex-wrap justify-center gap-2">
        {SUGGESTED_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onPick(prompt)}
            className="rounded-full border border-slate-200 px-3 py-1.5 text-xs text-ink hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[80%] rounded-2xl rounded-br-md bg-navy px-4 py-2.5 text-sm text-white">{text}</p>
    </div>
  );
}

function AgentMessage({ message }: { message: ChatMessage }) {
  if (message.error || !message.run) {
    return <ErrorState message={message.error ?? "The agent returned no result."} />;
  }
  const { run } = message;

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
          <Sparkles className="size-3.5 text-accent" aria-hidden />
          <span className="font-medium text-ink">CollectIQ</span>
          <span>· {run.model}</span>
          <span>· {RUN_STATUS_LABELS[run.status]}</span>
        </div>
        <div className="mt-3 space-y-2 text-sm leading-relaxed text-ink [&_h3]:mt-3 [&_h3]:font-semibold [&_li]:mt-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-5">
          <Markdown>{run.summary}</Markdown>
        </div>
        <ToolTrace calls={run.tool_calls} />
      </div>
      {run.proposed_actions.map((action) => (
        <ActionCardById key={action.id} actionId={action.id} />
      ))}
    </div>
  );
}

function ToolTrace({ calls }: { calls: ToolCallRecord[] }) {
  if (calls.length === 0) return null;
  return (
    <details className="mt-4 rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2">
      <summary className="cursor-pointer text-xs font-medium text-muted">
        How CollectIQ got this answer · {calls.length} tool call(s)
      </summary>
      <ol className="mt-2 space-y-1.5">
        {calls.map((call, index) => (
          <li key={`${call.name}-${index}`} className="flex items-start gap-2 text-xs">
            {call.status === "ok" ? (
              <CircleCheck className="mt-0.5 size-3.5 shrink-0 text-success" aria-label="Succeeded" />
            ) : (
              <CircleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" aria-label="Rejected by backend" />
            )}
            <span>
              <span className="font-medium text-ink">{TOOL_LABELS[call.name] ?? call.name}</span>
              <span className="text-muted"> — {call.detail}</span>
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}
