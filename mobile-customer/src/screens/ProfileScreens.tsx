import React, { useState } from "react";
import { Alert, FlatList, Text, View } from "react-native";
import type { CompositeScreenProps } from "@react-navigation/native";
import type { BottomTabScreenProps } from "@react-navigation/bottom-tabs";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { authApi, mastersApi, ordersApi } from "../api";
import { useAuth } from "../auth/AuthContext";
import { Button, Card, Empty, ErrorBox, Field, Loading, Row, Screen } from "../components/ui";
import { useLoad } from "../hooks";
import type { MainStackParams, TabParams } from "../navigation/types";
import { colors, formatDate } from "../theme";
import { MasterCard } from "./HomeScreens";

type ProfileProps = CompositeScreenProps<
  BottomTabScreenProps<TabParams, "Profile">,
  NativeStackScreenProps<MainStackParams>
>;

export function ProfileScreen({ navigation }: ProfileProps) {
  const { user, logout } = useAuth();
  return (
    <Screen>
      <Card>
        <Text style={{ fontSize: 20, fontWeight: "800" }}>{user?.full_name}</Text>
        <Text style={{ color: colors.muted, marginTop: 4 }}>{user?.phone}</Text>
      </Card>
      <Button title="♡ Sevimli ustalar" variant="secondary" onPress={() => navigation.navigate("Favorites")} />
      <Button title="Shikoyatlarim" variant="secondary" onPress={() => navigation.navigate("Disputes")} />
      <Button title="Parolni o'zgartirish" variant="secondary" onPress={() => navigation.navigate("ChangePassword")} />
      <Button
        title="Chiqish"
        variant="danger"
        onPress={() =>
          Alert.alert("Chiqish", "Hisobdan chiqmoqchimisiz?", [
            { text: "Yo'q", style: "cancel" },
            { text: "Ha", style: "destructive", onPress: () => void logout() },
          ])
        }
      />
    </Screen>
  );
}

export function FavoritesScreen({ navigation }: NativeStackScreenProps<MainStackParams, "Favorites">) {
  const favs = useLoad(() => mastersApi.favorites());
  if (favs.loading) return <Loading />;
  if (favs.error) return <ErrorBox message={favs.error} onRetry={favs.reload} />;
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <FlatList
        data={favs.data ?? []}
        keyExtractor={(m) => String(m.id)}
        contentContainerStyle={{ padding: 16 }}
        refreshing={favs.refreshing}
        onRefresh={favs.refresh}
        ListEmptyComponent={<Empty text="Sevimli ustalar yo'q" />}
        renderItem={({ item }) => (
          <MasterCard m={item} onPress={() => navigation.navigate("MasterDetail", { masterId: item.id })} />
        )}
      />
    </View>
  );
}

const DISPUTE_LABEL = { open: "Ko'rib chiqilmoqda", resolved: "Hal qilindi", rejected: "Rad etildi" } as const;

export function DisputesScreen({ navigation }: NativeStackScreenProps<MainStackParams, "Disputes">) {
  const list = useLoad(() => ordersApi.myDisputes());
  if (list.loading) return <Loading />;
  if (list.error) return <ErrorBox message={list.error} onRetry={list.reload} />;
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <FlatList
        data={list.data ?? []}
        keyExtractor={(d) => String(d.id)}
        contentContainerStyle={{ padding: 16 }}
        refreshing={list.refreshing}
        onRefresh={list.refresh}
        ListEmptyComponent={<Empty text="Shikoyatlar yo'q" />}
        renderItem={({ item: d }) => (
          <Card onPress={d.order_id ? () => navigation.navigate("OrderDetail", { orderId: d.order_id! }) : undefined}>
            <Text style={{ fontWeight: "700" }}>
              {d.order_id ? `#${d.order_id} · ` : ""}
              {d.category_name}
            </Text>
            <Text style={{ marginVertical: 4 }}>{d.reason}</Text>
            <Row label="Holat" value={DISPUTE_LABEL[d.status]} />
            {d.admin_note ? <Row label="Admin izohi" value={d.admin_note} /> : null}
            <Text style={{ color: colors.muted, fontSize: 12 }}>{formatDate(d.created_at)}</Text>
          </Card>
        )}
      />
    </View>
  );
}

export function ChangePasswordScreen({
  navigation,
}: NativeStackScreenProps<MainStackParams, "ChangePassword">) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await authApi.changePassword(current, next);
      Alert.alert("Tayyor", "Parol o'zgartirildi", [{ text: "OK", onPress: () => navigation.goBack() }]);
    } catch (e) {
      Alert.alert("Xatolik", e instanceof Error ? e.message : "Xatolik yuz berdi");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Field label="Joriy parol" value={current} onChangeText={setCurrent} secureTextEntry />
      <Field label="Yangi parol (kamida 8 belgi, harf va raqam)" value={next} onChangeText={setNext} secureTextEntry />
      <Button title="Saqlash" onPress={submit} loading={busy} />
    </Screen>
  );
}
