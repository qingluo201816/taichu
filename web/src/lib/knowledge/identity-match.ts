export type KnowledgeIdentity = {
  name?: unknown;
  aliases?: unknown;
};

export function normalizeKnowledgeIdentity(value: unknown): string {
  if (typeof value !== "string") return "";
  return value.normalize("NFKC").replace(/\s+/gu, "").toLocaleLowerCase();
}

export function knowledgeIdentityKeys(identity: KnowledgeIdentity): Set<string> {
  const aliases = Array.isArray(identity.aliases) ? identity.aliases : [];
  return new Set(
    [identity.name, ...aliases]
      .map(normalizeKnowledgeIdentity)
      .filter(Boolean),
  );
}

export function hasExactKnowledgeIdentityOverlap(
  left: KnowledgeIdentity,
  right: KnowledgeIdentity,
): boolean {
  const leftKeys = knowledgeIdentityKeys(left);
  if (!leftKeys.size) return false;
  return [...knowledgeIdentityKeys(right)].some(key => leftKeys.has(key));
}
