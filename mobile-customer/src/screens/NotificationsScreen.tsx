import React from "react";
import { FlatList, Text, View } from "react-native";
import type { CompositeScreenProps } from "@react-navigation/native";
import type { BottomTabScreenProps } from "@react-navigation/bottom-tabs";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { notificationsApi } from "../api";
import { Button, Card, Empty, ErrorBox, Loading } from "../components/ui";
import { useLoad } from "../hooks";
import type { MainStackParams, TabParams } from "../navigation/types";
import { colors, formatDate } from "../theme";

type Props = CompositeScreenProps<
  BottomTabScreenProps<TabParams, "Notifications">,
  NativeStackScreenProps<MainStackParams>
>;

export function NotificationsScreen({ navigation }: Props) {
  const list = useLoad(() => notificationsApi.list());

  if (list.loading) return <Loading />;
  if (list.error) return <ErrorBox message={list.error} onRetry={list.reload} />;
  const items = list.data ?? [];
  const hasUnread = items.some((n) => !n.is_read);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <FlatList
        data={items}
        keyExtractor={(n) => String(n.id)}
        contentContainerStyle={{ padding: 16 }}
        refreshing={list.refreshing}
        onRefresh={list.refresh}
        ListHeaderComponent={
          hasUnread ? (
            <Button
              title="Hammasini o'qilgan deb belgilash"
              variant="secondary"
              onPress={async () => {
                await notificationsApi.readAll();
                await list.reload();
              }}
            />
          ) : undefined
        }
        ListEmptyComponent={<Empty text="Bildirishnomalar yo'q" />}
        renderItem={({ item: n }) => (
          <Card
            style={!n.is_read ? { borderColor: colors.primary, backgroundColor: "#EFF6FF" } : undefined}
            onPress={async () => {
              if (!n.is_read) {
                try {
                  await notificationsApi.read(n.id);
                } catch {
                  /* e'tiborsiz */
                }
              }
              if (n.related_order_id) navigation.navigate("OrderDetail", { orderId: n.related_order_id });
              else await list.reload();
            }}
          >
            <Text style={{ fontWeight: "700" }}>{n.title}</Text>
            <Text style={{ marginTop: 2 }}>{n.body}</Text>
            <Text style={{ color: colors.muted, fontSize: 12, marginTop: 4 }}>{formatDate(n.created_at)}</Text>
          </Card>
        )}
      />
    </View>
  );
}
