export type AgentInfo = {
  name: string;
  label: string;
  description: string;
  required_capabilities: string[];
  exposures: string[];
  supports_streaming: boolean;
};

export type AgentListResponse = {
  agents: AgentInfo[];
};
