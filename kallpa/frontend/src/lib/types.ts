export type Business = {
  id: number; name: string; owner_name: string | null; kind: string; description: string | null
  setup_state: string; setup_source: string | null; setup_proposal: Proposal | null; demo: boolean
  payment_methods: string[]; gemini_requests: number
}
export type Proposal = {
  kind: 'reventa' | 'comida' | 'servicios'; business_name?: string | null
  categories: { name: string; kind: string }[]
  products: { name: string; aliases: string[]; is_service?: boolean; is_input?: boolean; track_stock?: boolean; unit?: string }[]
  payment_methods: string[]; source: string; note?: string | null
}
export type Draft = { op_id: string; action: string; missing: string | null; options: unknown; data: Record<string, unknown>; status: string }
export type Movement = {
  id: number; op_id: string; kind: string; label: string; occurred_at: string; amount_cents: number; paid_cents: number
  pending_cents: number; method: string | null; to_method: string | null; product_id: number | null; product: string | null
  quantity: number | null; unit_price_ref_cents: number | null; reference_total_cents: number | null; discount_cents: number | null
  unit_cost_cents: number | null; margin_cents: number | null; units_pending: boolean; category: string | null
  counterparty: string | null; description: string | null; raw_text: string | null; channel: string | null
  origin: string; origin_label: string; check: string | null; check_label: string | null; status: string; revision: number
  demo: boolean; attachments: { id: number; kind: string; filename: string; demo: boolean }[]
  revisions?: { changed_at: string; before: Record<string, unknown>; after: Record<string, unknown>; reason: string | null }[]
  yape?: { payer: string; amount_cents: number; operation_code: string; demo: boolean }[]
}
export type ChatResponse = {
  reply: string; quick_replies: string[]; draft: Draft | null; movement: Movement | null; updated_at: string
  transcript?: string; duplicate?: boolean; message_id?: string; count?: CountT; setup?: Proposal
}
export type CountT = { id: number; kind: string; product_id: number | null; pocket: string | null; counted: number; expected: number | null
  difference: number | null; result: string; review_status: string; note: string | null; counted_at: string; text?: string; product?: string; hints?: string[] }
export type Goal = {
  id: number; kind: 'reposicion' | 'ahorro'; name: string; target_cents: number; deadline: string | null; status: string
  progress_pct: number | null; missing_cents: number | null; message: string; saved_cents?: number; per_week_cents?: number
  per_day_cents?: number; behind?: boolean; available_cents?: number | null; days_left?: number; expected_cents?: number
}
export type Period = {
  sales_cents: number; sales_count: number; collected_cents: number; collected_by_method: { efectivo: number; yape: number }
  sales_by_method: { efectivo: number; yape: number; fiado: number }; collections_cents: number; discounts_cents: number
  purchases_cents: number; expenses_cents: number; withdrawals_cents: number; contributions_cents: number; debt_payments_cents: number
  profit_cents: number; profit_estimated: boolean; business_cashflow_cents: number; net_cashflow_cents: number; inflow_cents: number
  outflow_cents: number; business_outflow_cents: number; cogs_cents: number; new_credit_cents: number; active_days: number
  expenses_by_category: Record<string, number>; fixed_expenses_cents: number; variable_expenses_cents: number; goal_savings_cents: number
  business_expenses_total_cents: number
}
export type Cash = {
  efectivo_cents: number; yape_cents: number; ahorro_metas_cents: number; known: { efectivo: boolean; yape: boolean }; complete: boolean
  total_cents: number; receivables_cents: number; upcoming_payments: { name: string; amount_cents: number; due: string; type: string }[]
  upcoming_total_cents: number; available_for_restock_cents: number | null; missing: string[]; missing_text?: string; updated_at: string
}
export type Margin = { product_id: number; name: string; units: number; revenue_cents: number; margin_cents: number | null
  margin_per_unit_cents: number | null; margin_pct: number | null; avg_price_cents: number | null; margin_pending: boolean; discount_cents: number }
export type InventoryItem = {
  id: number; name: string; aliases: string[]; unit: string; is_service: boolean; is_input: boolean; track_stock: boolean
  price_cents: number | null; cost_cents: number | null; initial_stock: number | null; expected_stock: number | null
  unit_margin_cents: number | null; stock_value_cents: number | null; sold_28d: number; daily_avg: number; days_left: number | null
  reorder_point: number | null; needs_restock: boolean; last_count: CountT | null; needs_review: string[]
}
export type Dashboard = {
  business: { id: number; name: string; kind: string; demo: boolean; owner_name: string | null }
  today: string; updated_at: string; day: Period; week: Period; month: Period; cash: Cash
  receivables: { sale_id: number; counterparty: string; pending_cents: number; occurred_at: string; product: string | null }[]
  series: { date: string; label: string; sales_cents: number; inflow_cents: number; outflow_cents: number; net_cents: number }[]
  weekday: { available: boolean; days: { weekday: number; name: string; avg_sales_cents: number; vs_avg_pct: number }[]; best?: { name: string }; worst?: { name: string } }
  trend: { current_sales_cents: number; previous_same_days_cents: number; pct: number | null; direction: string | null; days_compared: number }
  margins: Margin[]
  break_even: { available: boolean; reason?: string; fixed_cents: number; contribution_margin_pct?: number; break_even_monthly_cents?: number
    break_even_daily_cents?: number; last30_sales_cents?: number; coverage_pct?: number }
  rotation: { cash_days: number | null; cash_turnover: number | null; inventory_value_cents: number; inventory_turnover_30d: number | null
    inventory_days: number | null; receivable_days: number | null }
  goals: Goal[]; alerts: { product: string; pct: number }[]; advice: string[]; inventory_flags: InventoryItem[]
  daily_text: string; consent: { pending_month: string | null; pending_label: string | null }
}
export type Health = { transcription: { installed: boolean; model_on_disk: boolean; loaded: boolean; error: string | null }
  gemini: { enabled: boolean; model: string }; whatsapp: { connected: boolean; status: string }; templates: Record<string, string> }
