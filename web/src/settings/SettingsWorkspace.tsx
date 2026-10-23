import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { dirtyStores, saveDirtyCategories, saveOutcomeCopy } from "./save-coordinator";
import {
  SettingsWorkspaceContext,
  type SettingsWorkspaceValue,
} from "./settings-workspace-context";
import type { CategorySaveResult, SettingsCategoryStore } from "./types";

export function SettingsWorkspace({ children }: { children: ReactNode }) {
  const [storeMap, setStoreMap] = useState<Record<string, SettingsCategoryStore>>({});
  const [adminToken, setAdminToken] = useState("");
  const [revealAdminToken, setRevealAdminToken] = useState(false);
  const [saving, setSaving] = useState(false);
  const [results, setResults] = useState<CategorySaveResult[]>([]);
  const storesRef = useRef<SettingsCategoryStore[]>([]);
  const stores = useMemo(
    () => Object.values(storeMap).sort((left, right) => left.id.localeCompare(right.id)),
    [storeMap],
  );
  storesRef.current = stores;

  const upsert = useCallback((store: SettingsCategoryStore) => {
    setStoreMap((current) => ({ ...current, [store.id]: store }));
  }, []);

  const remove = useCallback((id: string) => {
    setStoreMap((current) => {
      if (!(id in current)) return current;
      const next = { ...current };
      delete next[id];
      return next;
    });
  }, []);

  const saveAll = useCallback(async () => {
    setSaving(true);
    try {
      const nextResults = await saveDirtyCategories(storesRef.current);
      setResults(nextResults);
      return nextResults;
    } finally {
      setSaving(false);
    }
  }, []);

  const discardAll = useCallback(() => {
    for (const store of dirtyStores(storesRef.current)) store.discard();
    setResults([]);
  }, []);

  const categoryErrors = useMemo(() => (
    Object.fromEntries(
      results.filter((result) => !result.ok && result.error).map((result) => [result.id, result.error || ""]),
    )
  ), [results]);

  const value = useMemo<SettingsWorkspaceValue>(() => ({
    stores,
    upsert,
    remove,
    adminToken,
    setAdminToken,
    revealAdminToken,
    setRevealAdminToken,
    dirty: stores.some((store) => store.dirty),
    saving,
    outcome: saveOutcomeCopy(results),
    categoryErrors,
    saveAll,
    discardAll,
  }), [
    adminToken,
    categoryErrors,
    discardAll,
    revealAdminToken,
    results,
    saveAll,
    saving,
    stores,
    upsert,
    remove,
  ]);

  return (
    <SettingsWorkspaceContext.Provider value={value}>
      {children}
    </SettingsWorkspaceContext.Provider>
  );
}
