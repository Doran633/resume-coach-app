import { create } from "zustand";
import type { GenerateResponse, Identity } from "../types/api";

export interface GenerateRequestDraft {
  target_role: string;
  mode: string;
  packaging_level: string;
  experience_type: string;
  raw_input: string;
}

interface AppState {
  step: number;
  identity: Identity;
  generation?: GenerateResponse;
  lastRequest?: GenerateRequestDraft;
  setStep: (step: number) => void;
  setLastRequest: (request: GenerateRequestDraft) => void;
  setGeneration: (generation: GenerateResponse) => void;
}

const createClientId = () => {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
};

const getOrCreate = (key: string, prefix: string) => {
  const existing = localStorage.getItem(key);
  if (existing) return existing;
  const value = `${prefix}_${createClientId()}`;
  localStorage.setItem(key, value);
  return value;
};

export const useAppStore = create<AppState>((set) => ({
  step: 0,
  identity: {
    anonymous_user_id: getOrCreate("resume_coach_anonymous_user_id", "anon"),
    session_id: getOrCreate("resume_coach_session_id", "sess")
  },
  setStep: (step) => set({ step }),
  setLastRequest: (lastRequest) => set({ lastRequest }),
  setGeneration: (generation) => set({ generation, step: 1 })
}));
