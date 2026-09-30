/** contract/frontend-backend.openapi.yaml (0.1.0) */
export interface HealthResponse {
  status: 'ok';
  service: 'backend';
}

export interface ConnectivityResponse {
  backend: 'ok';
  ai_server: 'ok' | 'unreachable';
}

export interface SessionCreateResponse {
  session_id: string;
  started_at: string;
}

/** 모든 값은 0 이상의 정수. dwell_ms 단위는 밀리초. */
export interface TouchFeatures {
  tap_count: number;
  miss_tap_count: number;
  repeat_tap_count: number;
  back_count: number;
  dwell_ms: number;
}

export interface VisionFeatures {
  face_detected: boolean;
  face_size_ratio?: number | null;
  assistive_device?: boolean | null;
  confidence: number;
}

export interface FeatureWindowRequest {
  screen_id: string;
  /** ISO 8601 date-time */
  window_start: string;
  /** ISO 8601 date-time */
  window_end: string;
  touch: TouchFeatures;
  /** 카메라 측정이 없으면 null. */
  vision?: VisionFeatures | null;
}

/** 각 상태 점수의 범위는 0~1. 합계가 1일 필요는 없음. */
export interface StateScores {
  normal: number;
  touch_difficulty: number;
  navigation_difficulty: number;
  visual_difficulty: number;
  hesitation: number;
}

export type UIPreset =
  | 'none'
  | 'large_text'
  | 'large_button'
  | 'simple_screen'
  | 'step_guide'
  | 'voice_guide';

export interface SupportDecision {
  preset: UIPreset;
  requires_confirmation: boolean;
  decided_by: 'rule_placeholder' | 'jev';
}

export interface FeatureWindowResponse {
  session_id: string;
  ai_available: boolean;
  states?: StateScores | null;
  model_version?: string | null;
  support: SupportDecision;
}

export interface ErrorResponse {
  detail: string;
}
