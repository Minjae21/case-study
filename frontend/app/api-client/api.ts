const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export interface Message {
  role: "user" | "assistant";
  content: string;
  products?: Product[];
}

export interface Product {
  part_number: string;
  title: string;
  price: string;
  image_url: string;
  url: string;
  appliance_type: string;
}

function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return "";
  let id = sessionStorage.getItem("ps_session_id");
  if (!id) {
    id = Math.random().toString(36).slice(2);
    sessionStorage.setItem("ps_session_id", id);
  }
  return id;
}

export async function getAIMessage(messages: Message[]): Promise<Message> {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const response = await fetch(`${BACKEND_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: messages.map((m) => ({ role: m.role, content: m.content })),
          session_id: getOrCreateSessionId(),
        }),
      });

      if (response.status === 503 || response.status === 429) {
        if (attempt < 2) {
          await new Promise((r) => setTimeout(r, (attempt + 1) * 2000));
          continue;
        }
      }

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail || `Server error ${response.status}`);
      }

      const data = await response.json();
      return {
        role: "assistant",
        content: data.content,
        products: data.products || [],
      };
    } catch (error) {
      if (attempt < 2 && error instanceof TypeError) {
        await new Promise((r) => setTimeout(r, (attempt + 1) * 1000));
        continue;
      }
      console.error("Chat API error:", error);
      return {
        role: "assistant",
        content: "Sorry, I'm having trouble connecting right now. Please make sure the backend is running and try again.",
        products: [],
      };
    }
  }
  return { role: "assistant", content: "Something went wrong.", products: [] };
}
