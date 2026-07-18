export type GeneralAgentComposerKey = {
  key: string;
  shiftKey: boolean;
  isComposing: boolean;
};

export function shouldSubmitGeneralAgentComposer(
  event: GeneralAgentComposerKey,
): boolean {
  return event.key === "Enter" && !event.shiftKey && !event.isComposing;
}
