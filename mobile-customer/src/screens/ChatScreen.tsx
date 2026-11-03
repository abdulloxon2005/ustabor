import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  Text,
  TextInput,
  View,
} from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { ordersApi } from "../api";
import type { Message } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Empty, ErrorBox, Loading } from "../components/ui";
import type { MainStackParams } from "../navigation/types";
import { colors, formatDate } from "../theme";

const POLL_MS = 5000;

export function ChatScreen({ route }: NativeStackScreenProps<MainStackParams, "Chat">) {
  const { orderId } = route.params;
  const { user } = useAuth();
  const [messages, setMessages] = useState<Message[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const listRef = useRef<FlatList<Message>>(null);

  const load = useCallback(async () => {
    try {
      setMessages(await ordersApi.messages(orderId));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Xatolik");
    }
  }, [orderId]);

  // Websocket yo'q — yangi xabarlar uchun oddiy polling
  useEffect(() => {
    void load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  const send = async () => {
    const body = text.trim();
    if (!body || sending) return;
    setSending(true);
    try {
      const m = await ordersApi.sendMessage(orderId, body);
      setText("");
      setMessages((prev) => [...(prev ?? []), m]);
    } catch (e) {
      Alert.alert("Yuborilmadi", e instanceof Error ? e.message : "Xatolik");
    } finally {
      setSending(false);
    }
  };

  if (messages === null && !error) return <Loading />;
  if (messages === null) return <ErrorBox message={error!} onRetry={load} />;

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.bg }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={90}
    >
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(m) => String(m.id)}
        contentContainerStyle={{ padding: 16, flexGrow: 1 }}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
        ListEmptyComponent={<Empty text="Hali xabarlar yo'q. Birinchi bo'lib yozing." />}
        renderItem={({ item }) => {
          const mine = item.sender_id === user?.id;
          return (
            <View style={{ alignItems: mine ? "flex-end" : "flex-start", marginBottom: 8 }}>
              <View
                style={{
                  maxWidth: "80%",
                  backgroundColor: mine ? colors.primary : "#fff",
                  borderRadius: 14,
                  padding: 10,
                  borderWidth: mine ? 0 : 1,
                  borderColor: colors.border,
                }}
              >
                {!mine ? (
                  <Text style={{ fontSize: 11, color: colors.muted, marginBottom: 2 }}>{item.sender_name}</Text>
                ) : null}
                <Text style={{ color: mine ? "#fff" : colors.text }}>{item.body}</Text>
                <Text style={{ fontSize: 10, color: mine ? "#BFDBFE" : colors.muted, marginTop: 4 }}>
                  {formatDate(item.created_at)}
                </Text>
              </View>
            </View>
          );
        }}
      />
      <View style={{ flexDirection: "row", padding: 10, backgroundColor: "#fff", borderTopWidth: 1, borderColor: colors.border }}>
        <TextInput
          value={text}
          onChangeText={setText}
          placeholder="Xabar yozing…"
          maxLength={2000}
          style={{
            flex: 1,
            height: 44,
            borderRadius: 22,
            backgroundColor: colors.bg,
            paddingHorizontal: 16,
            fontSize: 15,
          }}
        />
        <Pressable
          onPress={send}
          disabled={sending || !text.trim()}
          style={{
            marginLeft: 8,
            width: 44,
            height: 44,
            borderRadius: 22,
            backgroundColor: colors.primary,
            alignItems: "center",
            justifyContent: "center",
            opacity: sending || !text.trim() ? 0.5 : 1,
          }}
        >
          <Text style={{ color: "#fff", fontSize: 18 }}>➤</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}
