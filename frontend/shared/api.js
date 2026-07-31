/*
  Minimal fetch wrapper for the RealtyAI API. Vanilla JS, no build step —
  drop this <script> into any page in /frontend/app or /frontend/admin,
  AFTER supabase-client.js (auth now comes from the Supabase session).

  Set window.REALTYAI_API_BASE before this script loads if the API isn't
  on the same origin (e.g. api.realty.indicationsmedia.com).
*/

const API_BASE = window.REALTYAI_API_BASE || "http://localhost:8000";

const auth = {
  // Reads the current Supabase session token — no manual token storage
  // needed, supabase-js persists the session itself.
  async getToken() {
    return supabaseAuth.getAccessToken();
  },
  async isLoggedIn() {
    return !!(await auth.getToken());
  },
  async requireAuth() {
    if (!(await auth.isLoggedIn())) {
      window.location.href = "/app/login.html";
    }
  },
  async clearToken() {
    await supabaseAuth.signOut();
  },
};

async function apiRequest(path, { method = "GET", body, auth: needsAuth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (needsAuth) {
    const token = await auth.getToken();
    if (!token) throw new Error("Not authenticated");
    headers["Authorization"] = `Bearer ${token}`;
  }

  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (resp.status === 401) {
    await auth.clearToken();
    window.location.href = "/app/login.html";
    throw new Error("Session expired");
  }

  if (!resp.ok) {
    const errBody = await resp.json().catch(() => ({}));
    throw new Error(errBody.detail || `Request failed: ${resp.status}`);
  }

  if (resp.status === 204) return null;
  return resp.json();
}

const api = {
  // Auth — signUp/signIn now go through supabaseAuth directly (see
  // supabase-client.js), not through this backend. completeSignup is the
  // one backend call left: redeem the invite code + create the org/profile
  // right after a Supabase account exists.
  completeSignup: (payload) => apiRequest("/auth/complete-signup", { method: "POST", body: payload }),
  createInviteCode: (payload) => apiRequest("/auth/admin/invite-codes", { method: "POST", body: payload }),

  // Inbox
  listMessages: () => apiRequest("/inbox"),
  receiveMessage: (payload) => apiRequest("/inbox/receive", { method: "POST", body: payload }),
  generateDraftsForMessage: (messageId) => apiRequest(`/inbox/${messageId}/generate-drafts`, { method: "POST" }),
  sendReply: (messageId, chosenBody, wasEdited) =>
    apiRequest(`/inbox/${messageId}/reply`, {
      method: "POST",
      body: { chosen_body: chosenBody, was_edited: wasEdited },
    }),
  sendNewMessage: (payload) => apiRequest("/inbox/send-new", { method: "POST", body: payload }),

  // Properties
  getPropertySources: () => apiRequest("/properties/sources"),
  listProperties: (city) => apiRequest(`/properties${city ? `?city=${encodeURIComponent(city)}` : ""}`),
  createProperty: (payload) => apiRequest("/properties", { method: "POST", body: payload }),
  updateProperty: (id, payload) => apiRequest(`/properties/${id}`, { method: "PATCH", body: payload }),
  deleteProperty: (id) => apiRequest(`/properties/${id}`, { method: "DELETE" }),
  ingestListings: (city, state, source, limit = 25) =>
    apiRequest("/properties/ingest", { method: "POST", body: { city, state, source, limit } }),
  importPropertyCsv: async (file) => {
    const token = await auth.getToken();
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch(`${API_BASE}/properties/import-csv`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    if (!resp.ok) {
      const errBody = await resp.json().catch(() => ({}));
      throw new Error(errBody.detail || `CSV import failed: ${resp.status}`);
    }
    return resp.json();
  },
  getComps: (propertyId) => apiRequest(`/properties/${propertyId}/comps`),
  propertyComplianceCheck: (propertyId) => apiRequest(`/properties/${propertyId}/compliance-check`, { method: "POST" }),
  draftAgentMessage: (propertyId, purpose, extraContext) =>
    apiRequest(`/properties/${propertyId}/draft-agent-message`, { method: "POST", body: { purpose, extra_context: extraContext } }),
  sendAgentMessage: (propertyId, body) =>
    apiRequest(`/properties/${propertyId}/send-agent-message`, { method: "POST", body: { body } }),

  // Analysis
  analyzeProperty: (propertyId, maxComps = 5) =>
    apiRequest("/analyze/property", { method: "POST", body: { property_id: propertyId, max_comps: maxComps } }),

  // Compliance
  screenListingText: (text) => apiRequest("/compliance/screen-listing", { method: "POST", body: { text } }),
  getDisclosureReference: (jurisdiction) => apiRequest(`/compliance/disclosure-reference/${jurisdiction}`),
  getAmlOverview: (country) => apiRequest(`/compliance/aml-overview/${country}`),

  // Chat — persistent, never resets except via startNewConversation
  chat: (message) => apiRequest("/chat", { method: "POST", body: { message } }),
  getActiveConversation: (context = "chat") => apiRequest(`/conversations/active?context=${context}`),
  getConversationMessages: (id) => apiRequest(`/conversations/${id}/messages`),
  listConversations: (context = "chat", search) =>
    apiRequest(`/conversations?context=${context}${search ? `&search=${encodeURIComponent(search)}` : ""}`),
  startNewConversation: (context = "chat") => apiRequest(`/conversations/new?context=${context}`, { method: "POST" }),
  activateConversation: (id) => apiRequest(`/conversations/${id}/activate`, { method: "POST" }),

  // Opportunities
  getOpportunities: (city, minScore = 50) =>
    apiRequest(`/opportunities?city=${encodeURIComponent(city)}&min_score=${minScore}`),

  // Portfolio simulator
  simulatePortfolio: (assumptions) => apiRequest("/portfolio/simulate", { method: "POST", body: assumptions }),
  interpretInvestment: (assumptions) => apiRequest("/portfolio/interpret", { method: "POST", body: assumptions }),

  // Negotiation
  negotiationStrategy: (propertyId) => apiRequest(`/negotiation/${propertyId}`, { method: "POST" }),

  // Voice
  converseVoice: async (audioBlob, clientId) => {
    const token = await auth.getToken();
    const form = new FormData();
    form.append("audio", audioBlob, "recording.webm");
    if (clientId) form.append("client_id", clientId);

    const resp = await fetch(`${API_BASE}/voice/converse`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    if (!resp.ok) {
      const errBody = await resp.json().catch(() => ({}));
      throw new Error(errBody.detail || `Voice request failed: ${resp.status}`);
    }
    return resp.json();
  },
  voiceAudioUrl: (audioId) => `${API_BASE}/voice/audio/${audioId}`,

  // Content generation
  getContentTypes: () => apiRequest("/content/types"),
  generateContent: (propertyId, contentTypes) =>
    apiRequest("/content/generate", { method: "POST", body: { property_id: propertyId, content_types: contentTypes } }),

  // Documents
  getDocumentTypes: () => apiRequest("/documents/types"),
  listDocuments: () => apiRequest("/documents"),
  getDocument: (id) => apiRequest(`/documents/${id}`),
  generateDocument: (payload) => apiRequest("/documents/generate", { method: "POST", body: payload }),
  scoreDocument: (id) => apiRequest(`/documents/${id}/score`, { method: "POST" }),
  reworkDocument: (id, instructions) =>
    apiRequest(`/documents/${id}/rework`, { method: "POST", body: { instructions } }),
  uploadDocument: async (file, docType) => {
    const token = await auth.getToken();
    const form = new FormData();
    form.append("file", file);
    form.append("doc_type", docType);
    const resp = await fetch(`${API_BASE}/documents/upload`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    if (!resp.ok) {
      const errBody = await resp.json().catch(() => ({}));
      throw new Error(errBody.detail || `Upload failed: ${resp.status}`);
    }
    return resp.json();
  },

  // Alerts
  listAlertEvents: (unreadOnly = false) => apiRequest(`/alerts/events${unreadOnly ? "?unread_only=true" : ""}`),
  unreadAlertCount: () => apiRequest("/alerts/events/unread-count"),
  markAlertRead: (eventId) => apiRequest(`/alerts/events/${eventId}/read`, { method: "POST" }),
  listAlertRules: () => apiRequest("/alerts/rules"),
  createAlertRule: (payload) => apiRequest("/alerts/rules", { method: "POST", body: payload }),

  // CRM integrations
  listCrmProviders: () => apiRequest("/crm/providers"),
  listCrmConnections: () => apiRequest("/crm/connections"),
  createCrmConnection: (payload) => apiRequest("/crm/connections", { method: "POST", body: payload }),
  deleteCrmConnection: (id) => apiRequest(`/crm/connections/${id}`, { method: "DELETE" }),
  triggerCrmSync: (id) => apiRequest(`/crm/connections/${id}/sync`, { method: "POST" }),
  getCrmSyncLogs: (id) => apiRequest(`/crm/connections/${id}/logs`),
  importCrmCsv: async (file) => {
    const token = await auth.getToken();
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch(`${API_BASE}/crm/import/csv`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    if (!resp.ok) {
      const errBody = await resp.json().catch(() => ({}));
      throw new Error(errBody.detail || `CSV import failed: ${resp.status}`);
    }
    return resp.json();
  },

  // CRM — clients
  clientsMeta: () => apiRequest("/clients/meta"),
  listClients: (filters = {}) => {
    const params = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
    return apiRequest(`/clients${params.toString() ? "?" + params : ""}`);
  },
  createClient: (payload) => apiRequest("/clients", { method: "POST", body: payload }),
  getClient: (id) => apiRequest(`/clients/${id}`),
  updateClient: (id, payload) => apiRequest(`/clients/${id}`, { method: "PATCH", body: payload }),
  changeClientStage: (id, newStage) => apiRequest(`/clients/${id}/stage`, { method: "POST", body: { new_stage: newStage } }),
  addClientTag: (id, tag) => apiRequest(`/clients/${id}/tags`, { method: "POST", body: { tag } }),
  removeClientTag: (id, tag) => apiRequest(`/clients/${id}/tags/${encodeURIComponent(tag)}`, { method: "DELETE" }),
  getClientTimeline: (id) => apiRequest(`/clients/${id}/timeline`),
  getClientDuplicates: () => apiRequest("/clients/duplicates"),
  mergeClients: (primaryId, duplicateId) => apiRequest("/clients/merge", { method: "POST", body: { primary_id: primaryId, duplicate_id: duplicateId } }),
  checkStaleLeads: () => apiRequest("/clients/check-stale-leads", { method: "POST" }),
  recomputeClientScore: (id) => apiRequest(`/clients/${id}/recompute-score`, { method: "POST" }),

  // CRM — notes
  addClientNote: (id, body) => apiRequest(`/clients/${id}/notes`, { method: "POST", body: { body } }),
  listClientNotes: (id) => apiRequest(`/clients/${id}/notes`),

  // CRM — tasks
  createClientTask: (id, title, dueAt) => apiRequest(`/clients/${id}/tasks`, { method: "POST", body: { title, due_at: dueAt } }),
  listClientTasks: (id, includeCompleted = false) => apiRequest(`/clients/${id}/tasks?include_completed=${includeCompleted}`),
  completeClientTask: (taskId) => apiRequest(`/clients/tasks/${taskId}/complete`, { method: "POST" }),

  // CRM — saved searches
  createSavedSearch: (id, payload) => apiRequest(`/clients/${id}/saved-searches`, { method: "POST", body: payload }),
  listSavedSearches: (id) => apiRequest(`/clients/${id}/saved-searches`),

  // CRM — AI differentiators
  getRelationshipBrief: (id) => apiRequest(`/clients/${id}/ai/brief`, { method: "POST" }),
  getNextAction: (id) => apiRequest(`/clients/${id}/ai/next-action`, { method: "POST" }),
  getSuggestedTags: (id) => apiRequest(`/clients/${id}/ai/suggest-tags`, { method: "POST" }),

  // Settings — org-level API keys
  listSettingKeys: () => apiRequest("/settings/keys"),
  setSettingKey: (key, value) => apiRequest("/settings/keys", { method: "POST", body: { key, value } }),
  deleteSettingKey: (key) => apiRequest(`/settings/keys/${key}`, { method: "DELETE" }),
  getTelephonyStatus: () => apiRequest("/settings/telephony-status"),

  // Admin — platform-level API keys
  listPlatformKeys: () => apiRequest("/admin/settings/keys"),
  setPlatformKey: (key, value) => apiRequest("/admin/settings/keys", { method: "POST", body: { key, value } }),
  deletePlatformKey: (key) => apiRequest(`/admin/settings/keys/${key}`, { method: "DELETE" }),

  // Deal Room
  getDealRoom: (clientId) => apiRequest(`/deal-room/${clientId}`),

  // Text optimizer ("lightning bolt" button)
  optimizeText: (text, tone) => apiRequest("/optimize", { method: "POST", body: { text, tone } }),

  // Docs
  listDocs: () => apiRequest("/docs"),
  searchDocs: (q) => apiRequest(`/docs/search?q=${encodeURIComponent(q)}`),
  getDoc: (id) => apiRequest(`/docs/${id}`),
  askDocs: (question) => apiRequest("/docs/ask", { method: "POST", body: { question } }),

  // Onboarding
  getOnboardingStatus: () => apiRequest("/me/onboarding-status"),
  completeOnboarding: () => apiRequest("/me/complete-onboarding", { method: "POST" }),
  getProfile: () => apiRequest("/me/profile"),
  setPreferences: (payload) => apiRequest("/me/preferences", { method: "POST", body: payload }),
  getBusinessProfile: () => apiRequest("/settings/business-profile"),
  setBusinessProfile: (payload) => apiRequest("/settings/business-profile", { method: "POST", body: payload }),

  // Universal search
  searchEverything: (q, includeWeb = true) => apiRequest(`/search?q=${encodeURIComponent(q)}&include_web=${includeWeb}`),
  summarizeSearch: (query, results) => apiRequest("/search/summarize", { method: "POST", body: { query, results } }),

  // Memories
  getMemoryCategories: () => apiRequest("/memory/categories"),
  listMemories: (filters = {}) => {
    const params = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
    return apiRequest(`/memory${params.toString() ? "?" + params : ""}`);
  },
  getMemory: (id) => apiRequest(`/memory/${id}`),
  deleteMemory: (id) => apiRequest(`/memory/${id}`, { method: "DELETE" }),

  // Calendar
  listCalendarEvents: (start, end) => apiRequest(`/calendar/events?start=${start}&end=${end}`),
  todaysCalendarEvents: () => apiRequest("/calendar/events/today"),
  createCalendarEvent: (payload) => apiRequest("/calendar/events", { method: "POST", body: payload }),
  updateCalendarEvent: (id, payload) => apiRequest(`/calendar/events/${id}`, { method: "PATCH", body: payload }),
  listReminders: (start, end) => apiRequest(`/calendar/reminders?start=${start}&end=${end}`),
  createReminder: (payload) => apiRequest("/calendar/reminders", { method: "POST", body: payload }),
  completeReminder: (id) => apiRequest(`/calendar/reminders/${id}/complete`, { method: "POST" }),
  deleteReminder: (id) => apiRequest(`/calendar/reminders/${id}`, { method: "DELETE" }),
  deleteCalendarEvent: (id) => apiRequest(`/calendar/events/${id}`, { method: "DELETE" }),

  // Daily briefing
  getDailyBriefing: () => apiRequest("/briefing"),

  // Integrations
  listIntegrationConnections: () => apiRequest("/integrations/connections"),
  googleAuthorizeUrl: () => apiRequest("/integrations/google/authorize"),
  microsoftAuthorizeUrl: () => apiRequest("/integrations/microsoft/authorize"),
  syncEmailConnection: (id) => apiRequest(`/integrations/email/${id}/sync`, { method: "POST" }),
  syncCalendarConnection: (id) => apiRequest(`/integrations/calendar/${id}/sync`, { method: "POST" }),
  connectSlack: (payload) => apiRequest("/integrations/slack/connect", { method: "POST", body: payload }),

  // Agent (Hermes delegation + approvals)
  hermesStatus: () => apiRequest("/agent/hermes-status"),
  delegateToAgent: (task, context) => apiRequest("/agent/delegate", { method: "POST", body: { task, context } }),
  getApprovals: () => apiRequest("/agent/approvals"),

  // Trust
  myTrustScores: () => apiRequest("/trust/me"),
  getTrustGamification: () => apiRequest("/trust/gamification"),

  // Admin — user CRUD, stats, audit log, admin agent
  adminMe: () => apiRequest("/admin/me"),
  adminListUsers: (search, status) => {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (status) params.set("status", status);
    return apiRequest(`/admin/users${params.toString() ? "?" + params : ""}`);
  },
  adminGetUser: (id) => apiRequest(`/admin/users/${id}`),
  adminUpdateUser: (id, payload) => apiRequest(`/admin/users/${id}`, { method: "PATCH", body: payload }),
  adminSetUserStatus: (id, status, reason) =>
    apiRequest(`/admin/users/${id}/status`, { method: "POST", body: { status, reason } }),
  adminStatsOverview: () => apiRequest("/admin/stats/overview"),
  adminStatsSignups: (days = 30) => apiRequest(`/admin/stats/signups?days=${days}`),
  adminStatsMessageVolume: (days = 30) => apiRequest(`/admin/stats/message-volume?days=${days}`),
  adminAuditLog: (limit = 100) => apiRequest(`/admin/audit-log?limit=${limit}`),
  adminChangePlanTier: (orgId, newTier) =>
    apiRequest(`/admin/organizations/${orgId}/plan-tier`, { method: "POST", body: { new_tier: newTier } }),
  adminActivateOrg: (orgId) => apiRequest(`/admin/organizations/${orgId}/activate`, { method: "POST" }),
  adminAgentChat: (message) => apiRequest("/admin/agent/chat", { method: "POST", body: { message } }),

  // Admin — org/invite codes (existing)
  listOrganizations: () => apiRequest("/admin/organizations"),
  listInviteCodes: () => apiRequest("/admin/invite-codes"),
  deactivateOrg: (orgId) => apiRequest(`/admin/organizations/${orgId}/deactivate`, { method: "POST" }),
};
