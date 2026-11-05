import {
  TradingSession,
  SessionCreatePayload,
  SessionUpdatePayload,
  SessionStopPayload,
  RecommendationRequest,
  SessionRecommendationResponse,
  SessionPerformance,
  SessionStatus,
  SessionMarket,
} from "../types";

const BASE_URL = "/api/sessions";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorDetail = `HTTP ${res.status}: ${res.statusText}`;
    try {
      const data = await res.json();
      if (data.detail) {
        errorDetail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // ignore json parse errors on non-json error responses
    }
    throw new ApiError(res.status, errorDetail);
  }
  return res.json();
}

export const sessionApi = {
  /** Query current active session (RUNNING or PAUSED) */
  async fetchActiveSession(): Promise<TradingSession | null> {
    const data = await handleResponse<{ session: TradingSession | null }>(
      await fetch(`${BASE_URL}/active`, { method: "GET" })
    );
    return data.session;
  },

  /** Fetch session by unique ID */
  async fetchSessionById(sessionId: string): Promise<TradingSession> {
    const data = await handleResponse<{ session: TradingSession }>(
      await fetch(`${BASE_URL}/${encodeURIComponent(sessionId)}`, { method: "GET" })
    );
    return data.session;
  },

  /** Create a new session in CREATED state */
  async createSession(payload: SessionCreatePayload): Promise<TradingSession> {
    const data = await handleResponse<{ session: TradingSession; message: string }>(
      await fetch(BASE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
    );
    return data.session;
  },

  /** Update mutable fields of a session (CREATED or PAUSED) */
  async updateSession(sessionId: string, payload: SessionUpdatePayload): Promise<TradingSession> {
    const data = await handleResponse<{ session: TradingSession; message: string }>(
      await fetch(`${BASE_URL}/${encodeURIComponent(sessionId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
    );
    return data.session;
  },

  /** Start a CREATED session, arming the bot and dynamically mapping parameters */
  async startSession(sessionId: string): Promise<TradingSession> {
    const data = await handleResponse<{ session: TradingSession; message: string }>(
      await fetch(`${BASE_URL}/${encodeURIComponent(sessionId)}/start`, { method: "POST" })
    );
    return data.session;
  },

  /** Pause an active RUNNING session, freezing countdown and halting new trade entries */
  async pauseSession(sessionId: string): Promise<TradingSession> {
    const data = await handleResponse<{ session: TradingSession; message: string }>(
      await fetch(`${BASE_URL}/${encodeURIComponent(sessionId)}/pause`, { method: "POST" })
    );
    return data.session;
  },

  /** Resume a PAUSED session, pushing expiry timestamp forward by elapsed pause time */
  async resumeSession(sessionId: string): Promise<TradingSession> {
    const data = await handleResponse<{ session: TradingSession; message: string }>(
      await fetch(`${BASE_URL}/${encodeURIComponent(sessionId)}/resume`, { method: "POST" })
    );
    return data.session;
  },

  /** Stop a session, terminating execution and executing session_end_policy */
  async stopSession(sessionId: string, reason = "MANUAL_STOP"): Promise<TradingSession> {
    const payload: SessionStopPayload = { reason };
    const data = await handleResponse<{ session: TradingSession; message: string }>(
      await fetch(`${BASE_URL}/${encodeURIComponent(sessionId)}/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
    );
    return data.session;
  },

  /** Request quantitative bounded basket recommendations via UniverseSelector */
  async fetchRecommendations(req: RecommendationRequest): Promise<SessionRecommendationResponse> {
    return handleResponse<SessionRecommendationResponse>(
      await fetch(`${BASE_URL}/recommendations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      })
    );
  },

  /** Fetch comprehensive session financial KPIs and P&L metrics */
  async fetchSessionPerformance(sessionId: string): Promise<SessionPerformance> {
    const data = await handleResponse<{ session_id: string; performance: SessionPerformance }>(
      await fetch(`${BASE_URL}/${encodeURIComponent(sessionId)}/performance`, { method: "GET" })
    );
    return data.performance;
  },

  /** List historical sessions with pagination */
  async listSessions(params?: {
    status?: SessionStatus;
    market?: SessionMarket;
    limit?: number;
    offset?: number;
  }): Promise<{ total: number; sessions: TradingSession[] }> {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.market) query.set("market", params.market);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    const url = query.toString() ? `${BASE_URL}?${query.toString()}` : BASE_URL;
    return handleResponse<{ total: number; sessions: TradingSession[] }>(await fetch(url));
  },
};
