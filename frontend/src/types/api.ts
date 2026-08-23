export type RiskLevel = "green" | "yellow" | "red" | "black";

export interface ClaimResult {
  claim: string;
  risk_level: RiskLevel;
  evidence: string;
  risk_reason: string;
  interview_questions: string[];
  knowledge_to_prepare: string[];
  downgrade_wording: string;
}

export interface ResumeSections {
  personal_info: Record<string, string>;
  summary: string[];
  skills: string[];
  projects: Array<Record<string, any>>;
  education: Record<string, string>;
  interview_preparation: string[];
}

export interface GenerationResult {
  completeness_score: number;
  confirmed_facts: string[];
  missing_questions: string[];
  normal_version: string;
  bold_version: string;
  boundary_version: string;
  recommended_version: string;
  claims: ClaimResult[];
  interview_plan: string[];
  knowledge_checklist: string[];
  resume_sections: ResumeSections;
}

export interface GenerateResponse {
  experience_input_id: number;
  generation_result_id: number;
  result: GenerationResult;
}

export interface Identity {
  anonymous_user_id: string;
  session_id: string;
}
