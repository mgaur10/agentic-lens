export type OmnibarStatus = "idle" | "connecting" | "processing" | "error";

export interface OmnibarSuggestion {
  id: string;
  label: string;
  value: string;
}

export type ArmorLevel = "off" | "medium" | "high";

export interface SecuritySettings {
  armorEnabled: boolean;
  armorLevel: ArmorLevel;
}

export interface TelemetryEntry {
  timestamp: string;
  icon: string;
  type: string;
  message: string;
  // payload shape is backend-defined; treat as generic
  payload?: Record<string, unknown> | null;
  turn: number;
}

