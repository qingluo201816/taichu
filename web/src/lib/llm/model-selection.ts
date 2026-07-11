import type { PublicLLMModel } from "@/lib/types/llm";

export function isSelectableModel(model: PublicLLMModel): boolean {
  return model.enabled && model.availability !== "unavailable";
}

export function selectInitialModelId(
  models: PublicLLMModel[],
  defaultModelId: string,
  rememberedModelId: string,
): string {
  const selectable = models.filter(isSelectableModel);
  if (selectable.some(model => model.id === rememberedModelId)) {
    return rememberedModelId;
  }
  if (selectable.some(model => model.id === defaultModelId)) {
    return defaultModelId;
  }
  return selectable[0]?.id ?? "";
}
