import { http, qs } from "./client";
import type {
  Category,
  Dispute,
  DispatchStatus,
  Master,
  MasterReviews,
  Message,
  NearbyMaster,
  NotificationItem,
  OrderCreateInput,
  OrderDetail,
  OrderListItem,
  OrderStatus,
  ReviewInput,
  TokenOut,
  User,
} from "./types";

export const authApi = {
  login: (phone: string, password: string) =>
    http.post<TokenOut>("/auth/login", { phone, password }, false),
  requestRegisterOtp: (phone: string) =>
    http.post<{ detail: string }>("/auth/register/request-otp", { phone }, false),
  register: (data: { phone: string; password: string; full_name: string; otp_code: string }) =>
    http.post<TokenOut>("/auth/register", { ...data, role: "customer" }, false),
  requestResetOtp: (phone: string) =>
    http.post<{ detail: string }>("/auth/forgot-password/request-otp", { phone }, false),
  confirmReset: (data: { phone: string; otp_code: string; new_password: string }) =>
    http.post<{ detail: string }>("/auth/forgot-password/confirm", data, false),
  me: () => http.get<User>("/auth/me"),
  changePassword: (current_password: string, new_password: string) =>
    http.post<{ detail: string }>("/auth/change-password", { current_password, new_password }),
};

export const categoriesApi = {
  list: () => http.get<Category[]>("/categories"),
};

export const mastersApi = {
  list: (p: { category_id?: number; city?: string; district?: string; q?: string } = {}) =>
    http.get<Master[]>(`/masters${qs(p)}`),
  nearby: (latitude: number, longitude: number, radius_km = 25) =>
    http.get<NearbyMaster[]>(`/masters/nearby${qs({ latitude, longitude, radius_km })}`),
  get: (id: number) => http.get<Master>(`/masters/${id}`),
  reviews: (id: number) => http.get<MasterReviews>(`/masters/${id}/reviews`),
  favorites: () => http.get<Master[]>("/masters/favorites"),
  addFavorite: (id: number) => http.post<unknown>(`/masters/${id}/favorite`),
  removeFavorite: (id: number) => http.delete<unknown>(`/masters/${id}/favorite`),
};

export const ordersApi = {
  list: (status?: OrderStatus) => http.get<OrderListItem[]>(`/orders${qs({ status_filter: status })}`),
  get: (id: number) => http.get<OrderDetail>(`/orders/${id}`),
  create: (data: OrderCreateInput) => http.post<{ id: number }>("/orders", data),
  cancel: (id: number) => http.post<unknown>(`/orders/${id}/cancel`),
  selectMaster: (id: number, master_id: number) =>
    http.post<unknown>(`/orders/${id}/select-master`, { master_id }),
  dispatch: (id: number) => http.post<DispatchStatus>(`/orders/${id}/dispatch`),
  dispatchStatus: (id: number) => http.get<DispatchStatus>(`/orders/${id}/dispatch-status`),
  acceptQuote: (id: number, quoteId: number) =>
    http.post<unknown>(`/orders/${id}/quotes/${quoteId}/accept`),
  rejectQuote: (id: number, quoteId: number) =>
    http.post<unknown>(`/orders/${id}/quotes/${quoteId}/reject`),
  review: (id: number, data: ReviewInput) => http.post<unknown>(`/orders/${id}/review`, data),
  uploadPhotos: (id: number, files: { uri: string; name: string; type: string }[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f as unknown as Blob));
    return http.upload<unknown>(`/orders/${id}/photos`, form);
  },
  messages: (id: number) => http.get<Message[]>(`/orders/${id}/messages`),
  sendMessage: (id: number, body: string) => http.post<Message>(`/orders/${id}/messages`, { body }),
  dispute: (id: number, reason: string) => http.post<unknown>(`/orders/${id}/dispute`, { reason }),
  myDisputes: () => http.get<Dispute[]>("/orders/my-disputes"),
};

export const notificationsApi = {
  list: () => http.get<NotificationItem[]>("/notifications"),
  unreadCount: () => http.get<{ unread_count: number }>("/notifications/unread-count"),
  read: (id: number) => http.post<unknown>(`/notifications/${id}/read`),
  readAll: () => http.post<unknown>("/notifications/read-all"),
};

export const geoApi = {
  search: (q: string) =>
    http.get<{ address: string; latitude: number; longitude: number }[]>(`/geo/search${qs({ q })}`),
};
