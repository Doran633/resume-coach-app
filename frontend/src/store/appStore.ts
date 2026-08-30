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
  currentAttemptId?: string;
  setStep: (step: number) => void;
  setLastRequest: (request: GenerateRequestDraft) => void;
  setCurrentAttemptId: (attemptId: string) => void;
  markCurrentAttemptComplete: () => void;
  setGeneration: (generation: GenerateResponse) => void;
}

const currentAttemptKey = "resume_coach_current_attempt_id";
const currentAttemptCreatedAtKey = "resume_coach_current_attempt_created_at";
const currentAttemptMaxAgeMs = 20 * 60 * 1000;

const restoreCurrentAttemptId = () => {
  const attemptId = localStorage.getItem(currentAttemptKey) || "";
  const createdAt = Number(localStorage.getItem(currentAttemptCreatedAtKey) || 0);
  if (attemptId && createdAt > 0 && Date.now() - createdAt <= currentAttemptMaxAgeMs) {
    return attemptId;
  }
  localStorage.removeItem(currentAttemptKey);
  localStorage.removeItem(currentAttemptCreatedAtKey);
  return undefined;
};

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
  currentAttemptId: restoreCurrentAttemptId(),
  setStep: (step) => set({ step }),
  setLastRequest: (lastRequest) => set({ lastRequest }),
  setCurrentAttemptId: (currentAttemptId) => {
    if (currentAttemptId) {
      localStorage.setItem(currentAttemptKey, currentAttemptId);
      localStorage.setItem(currentAttemptCreatedAtKey, String(Date.now()));
    } else {
      localStorage.removeItem(currentAttemptKey);
      localStorage.removeItem(currentAttemptCreatedAtKey);
    }
    set({ currentAttemptId: currentAttemptId || undefined });
  },
  markCurrentAttemptComplete: () => {
    localStorage.removeItem(currentAttemptKey);
    localStorage.removeItem(currentAttemptCreatedAtKey);
  },
  setGeneration: (generation) => set({ generation, step: 1 })
}));
