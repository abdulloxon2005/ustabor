export type AuthStackParams = {
  Login: undefined;
  Register: undefined;
  ForgotPassword: undefined;
};

export type MainStackParams = {
  Tabs: undefined;
  Masters: { categoryId?: number; categoryName?: string; selectForOrderId?: number } | undefined;
  MasterDetail: { masterId: number; selectForOrderId?: number };
  CreateOrder: { categoryId?: number; masterId?: number; masterName?: string } | undefined;
  OrderDetail: { orderId: number };
  Chat: { orderId: number };
  Favorites: undefined;
  Disputes: undefined;
  ChangePassword: undefined;
};

export type TabParams = {
  Home: undefined;
  Orders: undefined;
  Notifications: undefined;
  Profile: undefined;
};
