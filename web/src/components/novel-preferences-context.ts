import { createContext, useContext } from "react";

import { defaultNovelPreferences, type NovelPreferences } from "../lib/novel-workbench-preferences";

export const NovelPreferencesContext = createContext({
  preferences: defaultNovelPreferences,
  reduced: false,
  update: (patch: Partial<NovelPreferences>) => { void patch; },
});

export function useNovelPreferences() { return useContext(NovelPreferencesContext); }