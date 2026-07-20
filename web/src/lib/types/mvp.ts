export type OutlineChapter = {
  chapter_id: string;
  display_title: string;
  order: number;
  markdown_path: string;
};

export type OutlineVolume = {
  volume_id: string;
  name: string;
  order: number;
  chapters: OutlineChapter[];
};

export type WritingOutline = {
  volumes: OutlineVolume[];
  current_volume_id?: string | null;
  current_chapter_id?: string | null;
  updated_at: string;
};

export type OutlineResponse = {
  outline: WritingOutline;
};

export type SourceReference = {
  source_type: "chapter" | "knowledge_card" | "author_note" | "external";
  source_id: string;
  display_name: string;
  excerpt: string;
  note: string;
  author_note_body?: string | null;
};

export type KnowledgeTypeValue =
  | "character"
  | "realm"
  | "technique"
  | "location"
  | "faction"
  | "item"
  | "rule"
  | "event";

export type StructuredKnowledgeLifecycle = "draft" | "confirmed" | "rejected";
export type StructuredKnowledgeSourceOrigin =
  | "inbox_fact"
  | "agent_extract"
  | "manual";
export type KnowledgeSchemaFieldType =
  | "short_text"
  | "long_text"
  | "enum"
  | "number"
  | "boolean"
  | "chapter_ref"
  | "knowledge_ref"
  | "string_array"
  | "record_array";

export type KnowledgeTypeInfo = {
  value: KnowledgeTypeValue;
  label: string;
};

export type KnowledgeFieldOption = {
  value: string;
  label: string;
};

export type KnowledgeFieldMergeStrategy =
  | "preserve_existing"
  | "replace"
  | "append_unique"
  | "union"
  | "sum"
  | "latest";

export type KnowledgeFieldSchema = {
  field_key: string;
  label: string;
  field_type: KnowledgeSchemaFieldType;
  required_when_confirmed: boolean;
  options: KnowledgeFieldOption[];
  placeholder: string;
  display_group: string;
  list_display: boolean;
  author_editable?: boolean;
  ai_usage: string;
  merge_strategy: KnowledgeFieldMergeStrategy;
};

export type KnowledgeTypeSchema = {
  type: KnowledgeTypeValue;
  label: string;
  fields: KnowledgeFieldSchema[];
};

export type StructuredKnowledgeCard = Partial<
  Record<
    | "role_type"
    | "identity"
    | "relationship_summary"
    | "death_chapter_id"
    | "current_realm_text"
    | "first_seen_chapter_id"
    | "last_seen_chapter_id"
    | "system"
    | "technique_type"
    | "grade"
    | "practice_condition"
    | "owner_faction_id"
    | "controlling_faction_id"
    | "faction_type"
    | "leader_id"
    | "item_type"
    | "current_holder_id"
    | "exceptions"
    | "chapter_id"
    | "description",
    string | null
  >
> & {
  id: string;
  type: KnowledgeTypeValue;
  name: string;
  aliases: string[];
  summary: string;
  appearance_chapter_count?: number | null;
  lifecycle: StructuredKnowledgeLifecycle;
  source_origin?: StructuredKnowledgeSourceOrigin | null;
  source_note: string;
  level_order?: number | null;
  created_at: string;
  updated_at: string;
};

export type KnowledgeTypesResponse = {
  types: KnowledgeTypeInfo[];
};

export type KnowledgeSchemasResponse = {
  schemas: KnowledgeTypeSchema[];
};

export type KnowledgeSchemaResponse = {
  schema: KnowledgeTypeSchema;
};

export type KnowledgeCardListResponse = {
  cards: StructuredKnowledgeCard[];
  page: number;
  page_size: number;
  total: number;
};

export type KnowledgeCardResponse = {
  card: StructuredKnowledgeCard;
};

export type InboxStatus = "todo" | "processed" | "deprecated";
export type InboxPriority = "low" | "normal" | "high";
export type MVPInboxEntryType = "idea" | "pending_fact" | "issue";

export type MVPInboxIdea = {
  id: string;
  entry_type?: "idea";
  title?: string;
  content: string;
  source_chapter_id?: string | null;
  priority: InboxPriority;
  status: InboxStatus;
  created_at: string;
  updated_at: string;
};

export type MVPInboxPendingFact = {
  id: string;
  entry_type?: "pending_fact";
  title: string;
  content: string;
  source_chapter_id?: string | null;
  origin: string;
  priority: InboxPriority;
  status: InboxStatus;
  confirmed_knowledge_card_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type MVPInboxIssue = {
  id: string;
  entry_type?: "issue";
  title: string;
  content: string;
  source_chapter_id?: string | null;
  priority: InboxPriority;
  status: InboxStatus;
  created_at: string;
  updated_at: string;
};

export type InboxTab = "all" | "ideas" | "pending-facts" | "issues";

export type MVPInboxListResponse<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
};

export type MVPInboxIdeaResponse = {
  item: MVPInboxIdea;
};

export type MVPInboxPendingFactResponse = {
  item: MVPInboxPendingFact;
};

export type MVPInboxIssueResponse = {
  item: MVPInboxIssue;
};

export type ConfirmPendingFactResponse = {
  pending_fact: MVPInboxPendingFact;
  knowledge_card: StructuredKnowledgeCard;
};

export type EditorPreferences = {
  font_size: number;
  font_style: "serif" | "sans";
  editor_background: "dark" | "soft";
  updated_at: string;
};

export type PreferencesResponse = {
  preferences: EditorPreferences;
};
