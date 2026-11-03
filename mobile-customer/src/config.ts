import Constants from "expo-constants";
import { Platform } from "react-native";

/**
 * Backend manzili.
 * 1) EXPO_PUBLIC_API_URL (masalan: http://192.168.1.10:8000) berilsa, shu ishlatiladi.
 * 2) Aks holda Expo dev server joylashgan kompyuterning IP manzili avtomatik olinadi
 *    (telefon va kompyuter bir Wi-Fi tarmog'ida bo'lishi kerak).
 */
function detectBaseUrl(): string {
  const env = process.env.EXPO_PUBLIC_API_URL;
  if (env) return env.replace(/\/+$/, "");

  const hostUri = Constants.expoConfig?.hostUri;
  const host = hostUri ? hostUri.split(":")[0] : undefined;
  if (host) return `http://${host}:8000`;

  return Platform.OS === "android" ? "http://10.0.2.2:8000" : "http://localhost:8000";
}

export const BASE_URL = detectBaseUrl();
export const API_URL = `${BASE_URL}/api/v1`;

export function mediaUrl(path: string): string {
  return /^https?:\/\//.test(path) ? path : `${BASE_URL}${path}`;
}
