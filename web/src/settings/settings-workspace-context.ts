import { createContext, useContext } from "react";

import { saveOutcomeCopy } from "./save-coordinator";
import type { CategorySaveResult, SettingsCategoryStore } from "./types";

export interface SettingsWorkspaceValue {
  stores: SettingsCategoryStore[];
  upsert: (store: SettingsCategoryStore) => void;
  remove: (id: string) => void;
  adminToken: string;
  setAdminToken: (value: string) => void;
  revealAdminToken: boolean;
  setRevealAdminToken: (value: boolean) => void;
  dirty: boolean;
  saving: boolean;
  outcome: ReturnType<typeof saveOutcomeCopy>;
  categoryErrors: Record<string, string>;
  saveAll: () => Promise<CategorySaveResult[]>;
  discardAll: () => void;
}

export const SettingsWorkspaceContext = createContext<SettingsWorkspaceValue | null>(null);

export function useSettingsWorkspace(): SettingsWorkspaceValue {
  const value = useContext(SettingsWorkspaceContext);
  if (!value) throw new Error("useSettingsWorkspace requires SettingsWorkspace");
  return value;
}
