/** touch-interaction-pilot-v1: observation context, not a Jev decision or a diagnosis. */
export interface InteractionFeatures {
  schema_version: 'touch-interaction-pilot-v1';
  visit_id: string;
  window_sequence: number;
  outside_tap_ratio: number | null;
  outside_nearest_distance_mean_px: number | null;
  outside_nearest_distance_sample_count: number;
  pointer_cancel_count: number;
  pointer_interrupted_count: number;
  scroll_event_count: number;
  category_change_count: number;
  options_open_count: number;
  options_close_count: number;
  screen_transition_count: number;
  screen_revisit_count: number | null;
  cart_change_count: number;
  selection_change_count: number;
  ui_settings_change_count: number;
  voice_state_change_count: number;
  since_last_input_ms: number | null;
  order_busy_ms: number | null;
  options_open: boolean | null;
  order_busy: boolean;
  voice_enabled: boolean | null;
  microphone_active: boolean | null;
  voice_processing: boolean | null;
  voice_auto_off: 'silence' | 'idle' | null;
  ui_settings: {
    large_text: boolean; large_button: boolean; simple_screen: boolean;
    step_guide: boolean; low_screen: boolean; high_contrast: boolean;
  };
}
