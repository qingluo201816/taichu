import { apiRequest } from "@/lib/api-client";
import type {
  AIReferenceScope,
  AIWorkspaceConversationListResponse,
  AIWorkspaceConversationResponse,
  AIWorkspaceSubtaskType,
  AIWorkspaceTaskType,
  ConfirmPendingFactResponse,
  EditorPreferences,
  InboxTab,
  InboxPriority,
  InboxStatus,
  KnowledgeCardListResponse,
  KnowledgeCardResponse,
  KnowledgeSchemaResponse,
  KnowledgeSchemasResponse,
  KnowledgeTypeValue,
  KnowledgeTypesResponse,
  MVPInboxIdea,
  MVPInboxIdeaResponse,
  MVPInboxIssue,
  MVPInboxIssueResponse,
  MVPInboxListResponse,
  MVPInboxPendingFact,
  MVPInboxPendingFactResponse,
  OutlineResponse,
  PreferencesResponse,
} from "@/lib/types/mvp";

type InboxListParams = {
  page?: number;
  pageSize?: number;
  status?: InboxStatus | "all";
  priority?: InboxPriority | "all";
};

export async function readOutline(): Promise<OutlineResponse> {
  return apiRequest<OutlineResponse>("/api/outline");
}

export async function createVolume(name: string): Promise<OutlineResponse> {
  return apiRequest<OutlineResponse>("/api/outline/volumes", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function renameVolume(
  volumeId: string,
  name: string,
): Promise<OutlineResponse> {
  return apiRequest<OutlineResponse>(
    `/api/outline/volumes/${encodeURIComponent(volumeId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ name }),
    },
  );
}

export async function deleteVolume(volumeId: string): Promise<OutlineResponse> {
  return apiRequest<OutlineResponse>(
    `/api/outline/volumes/${encodeURIComponent(volumeId)}`,
    {
      method: "DELETE",
    },
  );
}

export async function createChapter(
  volumeId: string,
  displayTitle?: string | null,
  afterChapterId?: string | null,
): Promise<OutlineResponse> {
  return apiRequest<OutlineResponse>("/api/outline/chapters", {
    method: "POST",
    body: JSON.stringify({
      volume_id: volumeId,
      display_title: displayTitle ?? null,
      after_chapter_id: afterChapterId ?? null,
    }),
  });
}

export async function deleteChapter(
  chapterId: string,
): Promise<OutlineResponse> {
  return apiRequest<OutlineResponse>(
    `/api/outline/chapters/${encodeURIComponent(chapterId)}`,
    {
      method: "DELETE",
    },
  );
}

export async function renameChapter(
  chapterId: string,
  displayTitle: string,
): Promise<OutlineResponse> {
  return apiRequest<OutlineResponse>(
    `/api/outline/chapters/${encodeURIComponent(chapterId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ display_title: displayTitle }),
    },
  );
}

export async function listKnowledgeTypes(): Promise<KnowledgeTypesResponse> {
  return apiRequest<KnowledgeTypesResponse>("/api/knowledge/types");
}

export async function listKnowledgeSchemas(): Promise<KnowledgeSchemasResponse> {
  return apiRequest<KnowledgeSchemasResponse>("/api/knowledge/schemas");
}

export async function readKnowledgeSchema(
  type: KnowledgeTypeValue,
): Promise<KnowledgeSchemaResponse> {
  return apiRequest<KnowledgeSchemaResponse>(
    `/api/knowledge/schemas/${encodeURIComponent(type)}`,
  );
}

export async function listKnowledgeCards(params: {
  type: KnowledgeTypeValue;
  status: "all" | "draft" | "active" | "deprecated";
  q?: string;
  page?: number;
  pageSize?: number;
}): Promise<KnowledgeCardListResponse> {
  const search = new URLSearchParams({
    type: params.type,
    status: params.status,
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 10),
  });
  if (params.q?.trim()) {
    search.set("q", params.q.trim());
  }
  return apiRequest<KnowledgeCardListResponse>(
    `/api/knowledge/cards?${search.toString()}`,
  );
}

export async function createKnowledgeCard(
  type: KnowledgeTypeValue,
  data: Record<string, unknown> = {},
): Promise<KnowledgeCardResponse> {
  return apiRequest<KnowledgeCardResponse>("/api/knowledge/cards", {
    method: "POST",
    body: JSON.stringify({ type, data }),
  });
}

export async function readKnowledgeCard(
  cardId: string,
): Promise<KnowledgeCardResponse> {
  return apiRequest<KnowledgeCardResponse>(
    `/api/knowledge/cards/${encodeURIComponent(cardId)}`,
  );
}

export async function patchKnowledgeCard(
  cardId: string,
  updates: Record<string, unknown>,
): Promise<KnowledgeCardResponse> {
  return apiRequest<KnowledgeCardResponse>(
    `/api/knowledge/cards/${encodeURIComponent(cardId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ updates }),
    },
  );
}

export async function markKnowledgeCardActive(
  cardId: string,
): Promise<KnowledgeCardResponse> {
  return apiRequest<KnowledgeCardResponse>(
    `/api/knowledge/cards/${encodeURIComponent(cardId)}/mark-active`,
    { method: "POST" },
  );
}

export async function markKnowledgeCardDeprecated(
  cardId: string,
): Promise<KnowledgeCardResponse> {
  return apiRequest<KnowledgeCardResponse>(
    `/api/knowledge/cards/${encodeURIComponent(cardId)}/mark-deprecated`,
    { method: "POST" },
  );
}

export async function listInboxItems(
  tab: "ideas",
  params?: InboxListParams,
): Promise<MVPInboxListResponse<MVPInboxIdea>>;
export async function listInboxItems(
  tab: "pending-facts",
  params?: InboxListParams,
): Promise<MVPInboxListResponse<MVPInboxPendingFact>>;
export async function listInboxItems(
  tab: "issues",
  params?: InboxListParams,
): Promise<MVPInboxListResponse<MVPInboxIssue>>;
export async function listInboxItems(tab: InboxTab, params: InboxListParams = {}) {
  const search = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 10),
  });
  if (params.status) {
    search.set("status", params.status);
  }
  if (params.priority && params.priority !== "all") {
    search.set("priority", params.priority);
  }
  if (tab === "pending-facts") {
    return apiRequest<MVPInboxListResponse<MVPInboxPendingFact>>(
      `/api/inbox/pending-facts?${search.toString()}`,
    );
  }
  if (tab === "issues") {
    return apiRequest<MVPInboxListResponse<MVPInboxIssue>>(
      `/api/inbox/issues?${search.toString()}`,
    );
  }
  search.set("tab", "ideas");
  return apiRequest<MVPInboxListResponse<MVPInboxIdea>>(
    `/api/inbox?${search.toString()}`,
  );
}

export async function createInboxIdea(
  data: Record<string, unknown>,
): Promise<MVPInboxIdeaResponse> {
  return apiRequest<MVPInboxIdeaResponse>("/api/inbox/ideas", {
    method: "POST",
    body: JSON.stringify({ data }),
  });
}

export async function patchInboxIdea(
  itemId: string,
  updates: Record<string, unknown>,
): Promise<MVPInboxIdeaResponse> {
  return apiRequest<MVPInboxIdeaResponse>(
    `/api/inbox/ideas/${encodeURIComponent(itemId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ updates }),
    },
  );
}

export async function createInboxPendingFact(
  data: Record<string, unknown>,
): Promise<MVPInboxPendingFactResponse> {
  return apiRequest<MVPInboxPendingFactResponse>("/api/inbox/pending-facts", {
    method: "POST",
    body: JSON.stringify({ data }),
  });
}

export async function patchInboxPendingFact(
  itemId: string,
  updates: Record<string, unknown>,
): Promise<MVPInboxPendingFactResponse> {
  return apiRequest<MVPInboxPendingFactResponse>(
    `/api/inbox/pending-facts/${encodeURIComponent(itemId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ updates }),
    },
  );
}

export async function confirmInboxPendingFact(
  itemId: string,
  knowledgeType: KnowledgeTypeValue,
  cardPreview: Record<string, unknown>,
): Promise<ConfirmPendingFactResponse> {
  return apiRequest<ConfirmPendingFactResponse>(
    `/api/inbox/pending-facts/${encodeURIComponent(itemId)}/confirm`,
    {
      method: "POST",
      body: JSON.stringify({
        knowledge_type: knowledgeType,
        card_preview: cardPreview,
      }),
    },
  );
}

export async function createInboxIssue(
  data: Record<string, unknown>,
): Promise<MVPInboxIssueResponse> {
  return apiRequest<MVPInboxIssueResponse>("/api/inbox/issues", {
    method: "POST",
    body: JSON.stringify({ data }),
  });
}

export async function patchInboxIssue(
  itemId: string,
  updates: Record<string, unknown>,
): Promise<MVPInboxIssueResponse> {
  return apiRequest<MVPInboxIssueResponse>(
    `/api/inbox/issues/${encodeURIComponent(itemId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ updates }),
    },
  );
}

export async function createAIConversation(params: {
  chapterId: string;
  taskType: AIWorkspaceTaskType;
  referenceScope: AIReferenceScope;
  subtaskType?: AIWorkspaceSubtaskType | null;
  modelName?: string;
}): Promise<AIWorkspaceConversationResponse> {
  return apiRequest<AIWorkspaceConversationResponse>(
    "/api/ai-workspace-conversations",
    {
      method: "POST",
      body: JSON.stringify({
        chapter_id: params.chapterId,
        task_type: params.taskType,
        subtask_type: params.subtaskType ?? null,
        reference_scope: params.referenceScope,
        model_name: params.modelName ?? "mock-llm",
      }),
    },
  );
}

export async function sendAIMessage(params: {
  conversationId: string;
  userInput: string;
  reference: Record<string, unknown>;
}): Promise<AIWorkspaceConversationResponse> {
  return apiRequest<AIWorkspaceConversationResponse>(
    `/api/ai-workspace-conversations/${encodeURIComponent(
      params.conversationId,
    )}/messages`,
    {
      method: "POST",
      body: JSON.stringify({
        user_input: params.userInput,
        reference: params.reference,
      }),
    },
  );
}

export async function regenerateAIMessage(
  conversationId: string,
): Promise<AIWorkspaceConversationResponse> {
  return apiRequest<AIWorkspaceConversationResponse>(
    `/api/ai-workspace-conversations/${encodeURIComponent(
      conversationId,
    )}/regenerate`,
    { method: "POST" },
  );
}

export async function deleteAIConversation(
  conversationId: string,
): Promise<{ deleted: boolean }> {
  return apiRequest<{ deleted: boolean }>(
    `/api/ai-workspace-conversations/${encodeURIComponent(conversationId)}`,
    { method: "DELETE" },
  );
}

export async function listAIHistory(params: {
  chapterId?: string;
  chapterName?: string;
  taskType?: AIWorkspaceTaskType;
  page?: number;
  pageSize?: number;
} = {}): Promise<AIWorkspaceConversationListResponse> {
  const search = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 10),
  });
  if (params.chapterId) {
    search.set("chapter_id", params.chapterId);
  }
  if (params.chapterName?.trim()) {
    search.set("chapter_name", params.chapterName.trim());
  }
  if (params.taskType) {
    search.set("task_type", params.taskType);
  }
  return apiRequest<AIWorkspaceConversationListResponse>(
    `/api/ai-history?${search.toString()}`,
  );
}

export async function readAIHistory(
  conversationId: string,
): Promise<AIWorkspaceConversationResponse> {
  return apiRequest<AIWorkspaceConversationResponse>(
    `/api/ai-history/${encodeURIComponent(conversationId)}`,
  );
}

export async function readPreferences(): Promise<PreferencesResponse> {
  return apiRequest<PreferencesResponse>("/api/settings/preferences");
}

export async function patchPreferences(
  updates: Partial<EditorPreferences>,
): Promise<PreferencesResponse> {
  return apiRequest<PreferencesResponse>("/api/settings/preferences", {
    method: "PATCH",
    body: JSON.stringify({ updates }),
  });
}
