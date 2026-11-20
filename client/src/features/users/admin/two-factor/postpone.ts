import { useSyncExternalStore } from "react";

/** "Plus tard" on the setup screen, kept until the browser is closed (only while the activation is optional). */
const KEY = "kwaba:two-factor-postponed";
const listeners = new Set<() => void>();

function read(): boolean {
  try {
    return sessionStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

function write(postponed: boolean) {
  try {
    if (postponed) sessionStorage.setItem(KEY, "1");
    else sessionStorage.removeItem(KEY);
  } catch {
    // Storage blocked: the setup screen simply shows again
  }
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function usePostponed(): boolean {
  return useSyncExternalStore(subscribe, read, () => false);
}

export const postponeSetup = () => write(true);
export const resumeSetup = () => write(false);
