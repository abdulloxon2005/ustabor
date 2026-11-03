import React from "react";
import { Text } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { notificationsApi } from "../api";
import { useAuth } from "../auth/AuthContext";
import { Loading } from "../components/ui";
import { useLoad } from "../hooks";
import { ForgotPasswordScreen, LoginScreen, RegisterScreen } from "../screens/AuthScreens";
import { ChatScreen } from "../screens/ChatScreen";
import { CreateOrderScreen } from "../screens/CreateOrderScreen";
import { HomeScreen, MastersScreen } from "../screens/HomeScreens";
import { MasterDetailScreen } from "../screens/MasterDetailScreen";
import { NotificationsScreen } from "../screens/NotificationsScreen";
import { OrderDetailScreen } from "../screens/OrderDetailScreen";
import { OrdersScreen } from "../screens/OrdersScreen";
import {
  ChangePasswordScreen,
  DisputesScreen,
  FavoritesScreen,
  ProfileScreen,
} from "../screens/ProfileScreens";
import { colors } from "../theme";
import type { AuthStackParams, MainStackParams, TabParams } from "./types";

const AuthStack = createNativeStackNavigator<AuthStackParams>();
const MainStack = createNativeStackNavigator<MainStackParams>();
const Tab = createBottomTabNavigator<TabParams>();

const TAB_ICONS: Record<keyof TabParams, string> = {
  Home: "🏠",
  Orders: "📋",
  Notifications: "🔔",
  Profile: "👤",
};

function Tabs() {
  const unread = useLoad(() => notificationsApi.unreadCount());
  const count = unread.data?.unread_count ?? 0;

  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarActiveTintColor: colors.primary,
        tabBarIcon: () => <Text style={{ fontSize: 20 }}>{TAB_ICONS[route.name]}</Text>,
        headerTitleAlign: "left",
      })}
    >
      <Tab.Screen name="Home" component={HomeScreen} options={{ title: "Bosh sahifa", headerTitle: "UstaBor" }} />
      <Tab.Screen name="Orders" component={OrdersScreen} options={{ title: "Buyurtmalar" }} />
      <Tab.Screen
        name="Notifications"
        component={NotificationsScreen}
        options={{
          title: "Bildirishnoma",
          tabBarBadge: count > 0 ? count : undefined,
        }}
      />
      <Tab.Screen name="Profile" component={ProfileScreen} options={{ title: "Profil" }} />
    </Tab.Navigator>
  );
}

export function RootNavigator() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;

  return (
    <NavigationContainer>
      {user ? (
        <MainStack.Navigator screenOptions={{ headerBackTitle: "Orqaga" }}>
          <MainStack.Screen name="Tabs" component={Tabs} options={{ headerShown: false }} />
          <MainStack.Screen name="Masters" component={MastersScreen} options={{ title: "Ustalar" }} />
          <MainStack.Screen name="MasterDetail" component={MasterDetailScreen} options={{ title: "Usta" }} />
          <MainStack.Screen name="CreateOrder" component={CreateOrderScreen} options={{ title: "Yangi buyurtma" }} />
          <MainStack.Screen name="OrderDetail" component={OrderDetailScreen} options={{ title: "Buyurtma" }} />
          <MainStack.Screen name="Chat" component={ChatScreen} options={{ title: "Chat" }} />
          <MainStack.Screen name="Favorites" component={FavoritesScreen} options={{ title: "Sevimli ustalar" }} />
          <MainStack.Screen name="Disputes" component={DisputesScreen} options={{ title: "Shikoyatlarim" }} />
          <MainStack.Screen
            name="ChangePassword"
            component={ChangePasswordScreen}
            options={{ title: "Parolni o'zgartirish" }}
          />
        </MainStack.Navigator>
      ) : (
        <AuthStack.Navigator screenOptions={{ headerShown: false }}>
          <AuthStack.Screen name="Login" component={LoginScreen} />
          <AuthStack.Screen name="Register" component={RegisterScreen} />
          <AuthStack.Screen name="ForgotPassword" component={ForgotPasswordScreen} />
        </AuthStack.Navigator>
      )}
    </NavigationContainer>
  );
}
