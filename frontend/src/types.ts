// Shared domain types for Duuutah AI dashboard data.
// A "Call" is the core object: the call list, the call-detail drawer, and the
// Orders view (order-bearing calls) all render this same shape. Detail/order
// fields are optional because list responses omit them.

export interface OrderItem {
  name?: string;
  quantity?: number;
  subtotal?: number;
  unit_price?: number;
  modifiers?: string[];
  special_instructions?: string;
}

export interface OrderJson {
  items?: OrderItem[];
  total?: number;
  customer_name?: string;
  order_type?: string;
  state?: string;
  dispatch_failure_reason?: string;
  delivery_address?: string;
  special_instructions?: string;
}

export interface TranscriptEntry {
  role: string;
  text: string;
  timestamp?: string;
}

export interface CallAnalysis {
  analysis_available?: boolean;
  summary?: string;
  highlights?: string[];
  issues?: string[];
}

export interface Call {
  id: string;
  call_sid?: string;
  status: string;
  caller_name?: string;
  caller_number?: string;
  started_at?: string;
  duration_seconds?: number;
  quality_score?: number;
  order_total?: number;
  contained_by_ai?: boolean;
  escalated_to_human?: boolean;
  payment_status?: string;
  order_json?: OrderJson;
  analysis_json?: CallAnalysis;
  transcript?: TranscriptEntry[];
}

export interface ChartDatum {
  label?: string;
  calls?: number;
  revenue?: number;
}

export interface TopItem {
  name?: string;
  count?: number;
}

export interface HourlyDatum {
  hour?: number;
  calls?: number;
}

export interface DashboardStats {
  calls_this_week?: number;
  calls_this_month?: number;
  revenue_this_week?: number;
  revenue_this_month?: number;
  avg_quality_score?: number;
  ai_containment_rate?: number;
  escalated_calls?: number;
  daily_call_data?: ChartDatum[];
  monthly_call_data?: ChartDatum[];
  top_items?: TopItem[];
  hourly_distribution?: HourlyDatum[];
}

export interface Invoice {
  id: string;
  date?: number;
  description?: string;
  status?: string;
  amount?: number;
  pdf?: string;
}

// The restaurant/business object. Intentionally partial — fields are added as
// more pages are typed; AppSessionContext finalizes it in the last pass.
export interface Restaurant {
  id?: string;
  plan?: string;
  billing_status?: string;
  trial_ends_at?: string;
  monthly_call_count?: number;
  monthly_call_limit?: number;
  ai_containment_rate?: number;
  total_revenue?: number;
}

export interface AdminCostOverall {
  total_calls?: number;
  total_cost_dollars?: number;
  avg_cost_per_call_cents?: number;
  total_revenue_dollars?: number;
  gross_margin_pct?: number;
  total_sms_sent?: number;
}

export interface AdminCostPerRestaurant {
  restaurant_id?: string;
  restaurant_name?: string;
  sms_count?: number;
  total_calls?: number;
  voice_cost_dollars?: number;
  sms_cost_dollars?: number;
  gemini_cost_dollars?: number;
  cost_dollars?: number;
  revenue_dollars?: number;
  avg_duration_seconds?: number;
}

export interface AdminCostAnalytics {
  overall?: AdminCostOverall;
  per_restaurant?: AdminCostPerRestaurant[];
}
