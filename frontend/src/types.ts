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
