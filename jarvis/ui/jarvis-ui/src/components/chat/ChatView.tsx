"use client";

import { useEffect, useRef } from "react";
import { ChatMessage } from "@/lib/types";
import ChatInput from "@/components/shared/ChatInput";
import AgentBadge from "@/components/shared/AgentBadge";

interface ChatViewProps {
  messages: ChatMessage[];
  isProcessing: boolean;
  onSendMessage: (message: string) => void;
  onClearConversation: () => void;
  disabled: boolean;
  onBrowserMicState?: (recording: boolean) => void;
  authToken?: string | null;
}

export default function ChatView({
  messages,
  isProcessing,
  onSendMessage,
  onClearConversation,
  disabled,
  onBrowserMicState,
  authToken,
}: ChatViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages]);

  const visibleMessages = messages.filter(
    (msg) => msg.content || (msg.role === "assistant" && msg.isStreaming)
  );

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-5 py-2.5 border-b border-white/[0.04] bg-jarvis-surface/60 backdrop-blur-lg flex-shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-2xs font-medium text-jarvis-text-dim/55 uppercase tracking-[0.12em]">
            Conversation
          </h2>
          {visibleMessages.length > 0 && (
            <span className="text-3xs text-jarvis-text-dim/25 font-mono tabular-nums">
              {visibleMessages.length}
            </span>
          )}
        </div>
        <button
          onClick={onClearConversation}
          className="jarvis-btn-ghost text-3xs uppercase tracking-wider px-2 py-1 rounded-md"
          aria-label="Clear conversation"
        >
          Clear
        </button>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 sm:px-5 py-4 jarvis-scrollbar"
      >
        {visibleMessages.length === 0 ? (
          <div className="flex-1 flex items-center justify-center h-full">
            <div className="text-center animate-fade-in">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full flex items-center justify-center"
                   style={{
                     background: 'radial-gradient(circle, rgba(0,212,255,0.08) 0%, transparent 70%)',
                     boxShadow: '0 0 40px rgba(0,212,255,0.05)',
                   }}>
                <svg
                  width="28"
                  height="28"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1"
                  className="text-jarvis-cyan/20"
                >
                  <path
                    d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
              <p className="text-sm text-jarvis-text-dim/35 font-light">
                Start a conversation with JARVIS
              </p>
              <p className="text-2xs text-jarvis-text-dim/20 mt-1.5">
                Type below or switch to Voice mode
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-1 max-w-3xl mx-auto">
            {visibleMessages.map((msg, index) => {
              const isUser = msg.role === "user";
              const isLast = index === visibleMessages.length - 1;

              return (
                <div
                  key={msg.id}
                  className={`animate-fade-in py-2.5 ${isLast ? '' : ''}`}
                >
                  <div className="flex items-start gap-3">
                    <div className={`
                        w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0
                        text-3xs font-semibold mt-0.5
                        transition-colors duration-200
                        ${isUser
                          ? "bg-jarvis-cyan/8 text-jarvis-cyan/60 border border-jarvis-cyan/12"
                          : "bg-white/[0.03] text-jarvis-text-dim/50 border border-white/[0.06]"
                        }
                      `}>
                      {isUser ? "B" : "J"}
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-2xs font-medium text-jarvis-text-dim/55">
                          {isUser ? "Becs" : "JARVIS"}
                        </span>
                        {!isUser && (msg.agentType || msg.tierUsed) && (
                          <AgentBadge agentType={msg.agentType} tierUsed={msg.tierUsed} />
                        )}
                        <span className="text-3xs text-jarvis-text-dim/20 font-mono tabular-nums">
                          {new Date(msg.timestamp).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      </div>

                      <div className={`message-bubble ${isUser ? 'message-bubble-user' : 'message-bubble-assistant'}`}>
                        <div className="text-[13px] text-jarvis-text/80 leading-relaxed whitespace-pre-wrap">
                          {msg.content || (
                            <span className="text-jarvis-text-dim/40 italic text-xs">
                              Thinking...
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}

            {isProcessing && (
              <div className="flex items-center gap-2.5 text-jarvis-text-dim/50 text-xs pl-10 py-3 animate-fade-in">
                <div className="typing-dots flex items-center">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                <span className="text-2xs font-mono">Processing...</span>
              </div>
            )}
          </div>
        )}
      </div>

      <ChatInput
        onSubmit={onSendMessage}
        isProcessing={isProcessing}
        disabled={disabled}
        onBrowserMicState={onBrowserMicState}
        authToken={authToken}
      />
    </div>
  );
}
