"use client";

import React, { useState, useEffect, useRef } from "react";
import "./ChatWindow.css";
import { getAIMessage, type Message, type Product } from "../api-client/api";
import { marked } from "marked";

const QUICK_PROMPTS = [
  "My ice maker isn't working",
  "Find dishwasher door latch parts",
  "Is PS11765620 compatible with model 10672002011?",
  "How do I install PS11765620?",
];

function ProductCard({ part }: { part: Product }) {
  return (
    <div className="product-card">
      {part.image_url && (
        <img
          className="product-card__img"
          src={part.image_url}
          alt={part.title}
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = "none";
          }}
        />
      )}
      <div className="product-card__body">
        <p className="product-card__pn">{part.part_number}</p>
        <p className="product-card__title">{part.title}</p>
        {part.price && <p className="product-card__price">{part.price}</p>}
        <div className="product-card__actions">
          {part.url && (
            <a
              className="product-card__link"
              href={part.url}
              target="_blank"
              rel="noreferrer"
            >
              View Part
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="assistant-message-container">
      <div className="typing-indicator">
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}

const DEFAULT_MESSAGES: Message[] = [
  {
    role: "assistant",
    content:
      "Hi! I'm the **PartSelect Parts Assistant**.\n\nI can help you find refrigerator and dishwasher parts, check compatibility, troubleshoot problems, and walk you through installations.\n\nWhat can I help you with today?",
    products: [],
  },
];

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>(DEFAULT_MESSAGES);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: trimmed, products: [] }]);
    setInput("");
    setLoading(true);

    const prior = messages.filter((m) => m.role === "user" || m.role === "assistant");
    const firstUserIdx = prior.findIndex((m) => m.role === "user");
    const trimmedPrior = firstUserIdx >= 0 ? prior.slice(firstUserIdx) : [];
    const history: Message[] = [...trimmedPrior, { role: "user", content: trimmed }];

    const reply = await getAIMessage(history);
    setMessages((prev) => [...prev, reply]);
    setLoading(false);
  };

  const showQuickPrompts = messages.length === 1;

  return (
    <div className="chat-wrapper">
      <div className="messages-container">
        {messages.map((message, index) => (
          <div key={index} className={`${message.role}-message-container`}>
            {message.content && (
              <div className={`message ${message.role}-message`}>
                <div
                  dangerouslySetInnerHTML={{
                    __html: (marked(message.content) as string).replace(/<p>|<\/p>/g, ""),
                  }}
                />
              </div>
            )}
            {message.products && message.products.length > 0 && (
              <div className="product-cards-row">
                {message.products.map((p) => (
                  <ProductCard key={p.part_number} part={p} />
                ))}
              </div>
            )}
          </div>
        ))}

        {loading && <TypingIndicator />}

        {showQuickPrompts && (
          <div className="quick-prompts">
            {QUICK_PROMPTS.map((p) => (
              <button key={p} className="quick-prompt-chip" onClick={() => sendMessage(p)}>
                {p}
              </button>
            ))}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="input-area">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about a part, model, or problem…"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              sendMessage(input);
              e.preventDefault();
            }
          }}
          disabled={loading}
        />
        <button
          className="send-button"
          onClick={() => sendMessage(input)}
          disabled={loading || !input.trim()}
        >
          {loading ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}
