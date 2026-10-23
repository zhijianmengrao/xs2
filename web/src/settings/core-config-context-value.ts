import { createContext, useContext } from "react";

import type { ConfigItemMeta } from "../types";
import type { SettingsScalar } from "./types";

export interface CoreConfigContextValue {
  config: Record<string, SettingsScalar>;
  meta: ConfigItemMeta[];
  edited: Record<string, SettingsScalar>;
  loading: boolean;
  error: string | null;
  load: () => Promise<void>;
  setValue: (key: string, value: SettingsScalar) => void;
  displayValue: (key: string) => SettingsScalar;
  groupDirty: (group: string) => boolean;
  saveGroup: (group: string) => Promise<void>;
  discardGroup: (group: string) => void;
}

export const CoreConfigContext = createContext<CoreConfigContextValue | null>(null);

export function useCoreConfig(): CoreConfigContextValue {
  const value = useContext(CoreConfigContext);
  if (!value) throw new Error("useCoreConfig requires CoreConfigProvider");
  return value;
}