import React, { useEffect, useState } from "react";
import { FlatList, Pressable, ScrollView, Text, View } from "react-native";
import * as Location from "expo-location";
import type { CompositeScreenProps } from "@react-navigation/native";
import type { BottomTabScreenProps } from "@react-navigation/bottom-tabs";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { categoriesApi, mastersApi } from "../api";
import type { Master, NearbyMaster } from "../api/types";
import { Button, Card, Chip, Empty, ErrorBox, Field, Loading, Rating, Screen, SectionTitle } from "../components/ui";
import { useAuth } from "../auth/AuthContext";
import { useDebounced, useLoad } from "../hooks";
import type { MainStackParams, TabParams } from "../navigation/types";
import { colors } from "../theme";

type HomeProps = CompositeScreenProps<
  BottomTabScreenProps<TabParams, "Home">,
  NativeStackScreenProps<MainStackParams>
>;

export function HomeScreen({ navigation }: HomeProps) {
  const { user } = useAuth();
  const cats = useLoad(() => categoriesApi.list());
  const [nearby, setNearby] = useState<NearbyMaster[] | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const perm = await Location.requestForegroundPermissionsAsync();
        if (perm.status !== "granted") return;
        const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
        setNearby(await mastersApi.nearby(pos.coords.latitude, pos.coords.longitude, 25));
      } catch {
        /* joylashuv ixtiyoriy */
      }
    })();
  }, []);

  if (cats.loading) return <Loading />;
  if (cats.error) return <ErrorBox message={cats.error} onRetry={cats.reload} />;

  return (
    <Screen refreshing={cats.refreshing} onRefresh={cats.refresh}>
      <Text style={{ fontSize: 22, fontWeight: "800", color: colors.text }}>
        Salom, {user?.full_name.split(" ")[0]} 👋
      </Text>
      <Text style={{ color: colors.muted, marginBottom: 16 }}>Qanday usta kerak?</Text>

      <Button title="+ Yangi buyurtma berish" onPress={() => navigation.navigate("CreateOrder")} />

      <SectionTitle>Xizmat turlari</SectionTitle>
      <View style={{ flexDirection: "row", flexWrap: "wrap", marginHorizontal: -4 }}>
        {(cats.data ?? [])
          .filter((c) => c.is_active)
          .map((c) => (
            <Pressable
              key={c.id}
              style={{ width: "50%", padding: 4 }}
              onPress={() => navigation.navigate("Masters", { categoryId: c.id, categoryName: c.name })}
            >
              <View
                style={{
                  backgroundColor: "#fff",
                  borderRadius: 12,
                  borderWidth: 1,
                  borderColor: colors.border,
                  padding: 14,
                  minHeight: 64,
                  justifyContent: "center",
                }}
              >
                <Text style={{ fontWeight: "600", color: colors.text }}>{c.name}</Text>
              </View>
            </Pressable>
          ))}
      </View>

      {nearby && nearby.length > 0 ? (
        <>
          <SectionTitle>Yaqin atrofdagi ustalar</SectionTitle>
          {nearby.slice(0, 5).map((m) => (
            <Card key={m.id} onPress={() => navigation.navigate("MasterDetail", { masterId: m.id })}>
              <Text style={{ fontWeight: "700", fontSize: 16 }}>{m.full_name}</Text>
              <Text style={{ color: colors.muted, marginVertical: 2 }}>
                {m.city}, {m.district}
                {m.distance_km !== null ? ` · ${m.distance_km.toFixed(1)} km` : ""}
              </Text>
              <Rating value={m.rating_avg} count={m.rating_count} />
            </Card>
          ))}
        </>
      ) : null}

      <Button
        title="Barcha ustalarni ko'rish"
        variant="secondary"
        style={{ marginTop: 12 }}
        onPress={() => navigation.navigate("Masters")}
      />
    </Screen>
  );
}

type MastersProps = NativeStackScreenProps<MainStackParams, "Masters">;

export function MasterCard({ m, onPress }: { m: Master; onPress: () => void }) {
  return (
    <Card onPress={onPress}>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Text style={{ fontWeight: "700", fontSize: 16, flexShrink: 1 }}>{m.full_name}</Text>
        <Rating value={m.rating_avg} count={m.rating_count} />
      </View>
      <Text style={{ color: colors.muted, marginVertical: 3 }}>
        {m.city}, {m.district}
      </Text>
      <Text style={{ color: colors.text, fontSize: 13 }} numberOfLines={2}>
        {m.services.map((s) => s.category_name).join(" · ")}
      </Text>
    </Card>
  );
}

export function MastersScreen({ route, navigation }: MastersProps) {
  const params = route.params;
  const [q, setQ] = useState("");
  const [categoryId, setCategoryId] = useState<number | undefined>(params?.categoryId);
  const dq = useDebounced(q);
  const cats = useLoad(() => categoriesApi.list());
  const list = useLoad(
    () => mastersApi.list({ category_id: categoryId, q: dq.trim() || undefined }),
    [categoryId, dq]
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={{ padding: 16, paddingBottom: 4 }}>
        <Field placeholder="Usta ismi bo'yicha qidirish" value={q} onChangeText={setQ} />
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
          <Chip label="Hammasi" active={categoryId === undefined} onPress={() => setCategoryId(undefined)} />
          {(cats.data ?? []).map((c) => (
            <Chip key={c.id} label={c.name} active={categoryId === c.id} onPress={() => setCategoryId(c.id)} />
          ))}
        </ScrollView>
      </View>
      {list.loading ? (
        <Loading />
      ) : list.error ? (
        <ErrorBox message={list.error} onRetry={list.reload} />
      ) : (
        <FlatList
          data={list.data ?? []}
          keyExtractor={(m) => String(m.id)}
          contentContainerStyle={{ padding: 16, paddingTop: 4 }}
          refreshing={list.refreshing}
          onRefresh={list.refresh}
          ListEmptyComponent={<Empty text="Ustalar topilmadi" />}
          renderItem={({ item }) => (
            <MasterCard
              m={item}
              onPress={() =>
                navigation.navigate("MasterDetail", {
                  masterId: item.id,
                  selectForOrderId: params?.selectForOrderId,
                })
              }
            />
          )}
        />
      )}
    </View>
  );
}
