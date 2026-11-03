import React, { useState } from "react";
import { FlatList, ScrollView, Text, View } from "react-native";
import type { CompositeScreenProps } from "@react-navigation/native";
import type { BottomTabScreenProps } from "@react-navigation/bottom-tabs";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { ordersApi } from "../api";
import type { OrderStatus } from "../api/types";
import { Card, Chip, Empty, ErrorBox, Loading, StatusBadge } from "../components/ui";
import { useLoad } from "../hooks";
import type { MainStackParams, TabParams } from "../navigation/types";
import { colors, formatDate, formatPrice } from "../theme";

type Props = CompositeScreenProps<
  BottomTabScreenProps<TabParams, "Orders">,
  NativeStackScreenProps<MainStackParams>
>;

const FILTERS: { label: string; value: OrderStatus | undefined }[] = [
  { label: "Hammasi", value: undefined },
  { label: "Qidirilmoqda", value: "searching" },
  { label: "Biriktirildi", value: "assigned" },
  { label: "Jarayonda", value: "in_progress" },
  { label: "Yakunlangan", value: "completed" },
  { label: "Bekor", value: "cancelled" },
];

export function OrdersScreen({ navigation }: Props) {
  const [filter, setFilter] = useState<OrderStatus | undefined>(undefined);
  const orders = useLoad(() => ordersApi.list(filter), [filter]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={{ flexGrow: 0, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 4 }}
      >
        {FILTERS.map((f) => (
          <Chip key={f.label} label={f.label} active={filter === f.value} onPress={() => setFilter(f.value)} />
        ))}
      </ScrollView>
      {orders.loading ? (
        <Loading />
      ) : orders.error ? (
        <ErrorBox message={orders.error} onRetry={orders.reload} />
      ) : (
        <FlatList
          data={orders.data ?? []}
          keyExtractor={(o) => String(o.id)}
          contentContainerStyle={{ padding: 16 }}
          refreshing={orders.refreshing}
          onRefresh={orders.refresh}
          ListEmptyComponent={<Empty text="Buyurtmalar yo'q" />}
          renderItem={({ item: o }) => {
            const proposed = o.quotes.filter((q) => q.status === "proposed").length;
            return (
              <Card onPress={() => navigation.navigate("OrderDetail", { orderId: o.id })}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <Text style={{ fontWeight: "700", fontSize: 16 }}>
                    #{o.id} · {o.category_name}
                  </Text>
                  <StatusBadge status={o.status} />
                </View>
                <Text style={{ color: colors.text, marginTop: 6 }} numberOfLines={2}>
                  {o.description}
                </Text>
                <Text style={{ color: colors.muted, marginTop: 4, fontSize: 13 }}>
                  {o.city}, {o.district} · {formatDate(o.created_at)}
                </Text>
                {o.master_full_name ? (
                  <Text style={{ marginTop: 4, fontSize: 13 }}>Usta: {o.master_full_name}</Text>
                ) : null}
                {o.agreed_price !== null ? (
                  <Text style={{ marginTop: 2, fontSize: 13, fontWeight: "600" }}>{formatPrice(o.agreed_price)}</Text>
                ) : null}
                {proposed > 0 ? (
                  <Text style={{ marginTop: 6, color: colors.warning, fontWeight: "600" }}>
                    {proposed} ta narx taklifi kutmoqda
                  </Text>
                ) : null}
              </Card>
            );
          }}
        />
      )}
    </View>
  );
}
