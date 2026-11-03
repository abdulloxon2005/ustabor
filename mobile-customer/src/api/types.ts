export type Role = "customer" | "master" | "admin";
export type OrderStatus = "searching" | "assigned" | "in_progress" | "completed" | "cancelled";
export type SelectionMode = "manual" | "automatic";

export interface User {
  id: number;
  phone: string;
  full_name: string;
  role: Role;
  is_active: boolean;
}

export interface TokenOut {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  is_active: boolean;
}

export interface ScheduleDay {
  weekday: number;
  is_working: boolean;
  start_time: string | null;
  end_time: string | null;
}

export interface MasterService {
  category_id: number;
  category_name: string;
  pricing_type: "fixed" | "quote";
  base_price: number | null;
}

export interface Photo {
  id: number;
  url: string;
  created_at: string;
}

export interface Master {
  id: number;
  full_name: string;
  bio: string;
  city: string;
  district: string;
  latitude: number | null;
  longitude: number | null;
  is_available: boolean;
  rating_avg: number;
  rating_count: number;
  services: MasterService[];
  photos: Photo[];
  schedule: ScheduleDay[];
}

export interface NearbyMaster {
  id: number;
  full_name: string;
  city: string;
  district: string;
  rating_avg: number;
  rating_count: number;
  distance_km: number | null;
}

export interface ReviewItem {
  rating: number;
  comment: string | null;
  quality_rating: number | null;
  timeliness_rating: number | null;
  price_rating: number | null;
  created_at: string;
  customer_first_name: string;
}

export interface MasterReviews {
  rating_avg: number;
  rating_count: number;
  quality_avg: number | null;
  timeliness_avg: number | null;
  price_avg: number | null;
  reviews: ReviewItem[];
}

export interface Offer {
  id: number;
  master_id: number;
  master_name: string;
  master_full_name: string;
  status: string;
  expires_at: string | null;
}

export interface Quote {
  id: number;
  order_id: number;
  master_id: number;
  price: number;
  note: string | null;
  status: "proposed" | "accepted" | "rejected";
  created_at: string;
}

export interface HistoryItem {
  id: number;
  from_status: OrderStatus | null;
  to_status: OrderStatus;
  changed_by: number | null;
  created_at: string;
}

export interface OrderListItem {
  id: number;
  category_id: number;
  category_name: string;
  description: string;
  city: string;
  district: string;
  status: OrderStatus;
  selection_mode: SelectionMode;
  agreed_price: number | null;
  master_id: number | null;
  master_full_name: string | null;
  created_at: string;
  offers: Offer[];
  quotes: Quote[];
}

export interface OrderReview {
  rating: number;
  comment: string | null;
  quality_rating: number | null;
  timeliness_rating: number | null;
  price_rating: number | null;
}

export interface OrderDetail {
  id: number;
  customer_id: number;
  category_id: number;
  category_name: string;
  master_id: number | null;
  master_full_name: string | null;
  description: string;
  city: string;
  district: string;
  address: string;
  latitude: number | null;
  longitude: number | null;
  status: OrderStatus;
  selection_mode: SelectionMode;
  agreed_price: number | null;
  final_price: number | null;
  commission_rate: number;
  quotes: Quote[];
  created_at: string;
  history: HistoryItem[];
  offers: Offer[];
  review: OrderReview | null;
  can_review: boolean;
  note: string | null;
  photos: string[];
}

export interface OrderCreateInput {
  category_id: number;
  description: string;
  city: string;
  district: string;
  address: string;
  selection_mode: SelectionMode;
  latitude?: number;
  longitude?: number;
}

export interface DispatchStatus {
  order_id: number;
  status: string;
  dispatch_radius_km: number;
  pending_offers: number;
  rejected_offers: number;
  expired_offers: number;
  accepted_master_id: number | null;
  message: string;
}

export interface Message {
  id: number;
  order_id: number;
  sender_id: number;
  sender_name: string;
  body: string;
  created_at: string;
}

export interface NotificationItem {
  id: number;
  type: string;
  title: string;
  body: string;
  related_order_id: number | null;
  is_read: boolean;
  created_at: string;
}

export interface Dispute {
  id: number;
  order_id: number | null;
  category_name: string;
  order_status: string | null;
  status: "open" | "resolved" | "rejected";
  reason: string;
  admin_note: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface ReviewInput {
  rating: number;
  comment?: string;
  quality_rating?: number;
  timeliness_rating?: number;
  price_rating?: number;
}
