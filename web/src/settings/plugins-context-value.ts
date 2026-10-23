import { createContext, useContext } from "react";

import type { PluginRecord } from "../extensions/plugin-types";

export interface SettingsPluginsContextValue {
  plugins: PluginRecord[];
  loading: boolean;
  error: string | null;
  load: () => Promise<void>;
  replacePlugin: (plugin: PluginRecord) => void;
}

export const SettingsPluginsContext = createContext<SettingsPluginsContextValue | null>(null);

export function useSettingsPlugins(): SettingsPluginsContextValue {
  const value = useContext(SettingsPluginsContext);
  if (!value) throw new Error("useSettingsPlugins requires SettingsPluginsProvider");
  return value;
}