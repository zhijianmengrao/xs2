import { useEffect, useRef } from "react";

import type { SettingsCategoryStore } from "./types";
import { useSettingsWorkspace } from "./settings-workspace-context";

/**
 * Registers a settings category store with the enclosing SettingsWorkspace.
 *
 * Lives in its own module (not the provider file) so the component file stays
 * Fast-Refresh safe.
 */
export function useRegisterSettingsStore(store: SettingsCategoryStore): void {
  const { upsert, remove } = useSettingsWorkspace();
  const saveRef = useRef(store.save);
  const discardRef = useRef(store.discard);
  saveRef.current = store.save;
  discardRef.current = store.discard;

  useEffect(() => {
    upsert({
      id: store.id,
      title: store.title,
      dirty: store.dirty,
      requiresAdminToken: store.requiresAdminToken,
      save: () => saveRef.current(),
      discard: () => discardRef.current(),
    });
  }, [store.id, store.title, store.dirty, store.requiresAdminToken, upsert]);

  useEffect(() => () => remove(store.id), [remove, store.id]);
}