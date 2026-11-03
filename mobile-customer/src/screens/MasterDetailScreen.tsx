import React, { useState } from "react";
import { Alert, Image, ScrollView, Text, View } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { mastersApi, ordersApi } from "../api";
import { Button, Card, ErrorBox, Loading, Rating, Row, Screen, SectionTitle } from "../components/ui";
import { mediaUrl } from "../config";
import { useLoad } from "../hooks";
import type { MainStackParams } from "../navigation/types";
import { colors, formatDate, formatPrice } from "../theme";

const WEEKDAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"];

export function MasterDetailScreen({
  route,
  navigation,
}: NativeStackScreenProps<MainStackParams, "MasterDetail">) {
  const { masterId, selectForOrderId } = route.params;
  const master = useLoad(() => mastersApi.get(masterId), [masterId]);
  const reviews = useLoad(() => mastersApi.reviews(masterId), [masterId]);
  const favs = useLoad(() => mastersApi.favorites());
  const [busy, setBusy] = useState(false);

  if (master.loading) return <Loading />;
  if (master.error || !master.data) return <ErrorBox message={master.error ?? "Usta topilmadi"} onRetry={master.reload} />;
  const m = master.data;
  const isFav = (favs.data ?? []).some((f) => f.id === m.id);

  const toggleFav = async () => {
    try {
      if (isFav) await mastersApi.removeFavorite(m.id);
      else await mastersApi.addFavorite(m.id);
      await favs.reload();
    } catch (e) {
      Alert.alert("Xatolik", e instanceof Error ? e.message : "Xatolik");
    }
  };

  const choose = async () => {
    if (!selectForOrderId) return;
    setBusy(true);
    try {
      await ordersApi.selectMaster(selectForOrderId, m.id);
      Alert.alert("Yuborildi", "Ustaga so'rov yuborildi. Usta qabul qilishini kuting.", [
        { text: "OK", onPress: () => navigation.navigate("OrderDetail", { orderId: selectForOrderId }) },
      ]);
    } catch (e) {
      Alert.alert("Tanlab bo'lmadi", e instanceof Error ? e.message : "Xatolik");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen refreshing={master.refreshing} onRefresh={master.refresh}>
      <Card>
        <Text style={{ fontSize: 20, fontWeight: "800" }}>{m.full_name}</Text>
        <Text style={{ color: colors.muted, marginVertical: 4 }}>
          {m.city}, {m.district}
        </Text>
        <Rating value={m.rating_avg} count={m.rating_count} />
        <Text style={{ color: m.is_available ? colors.success : colors.danger, marginTop: 6, fontWeight: "600" }}>
          {m.is_available ? "Buyurtma qabul qiladi" : "Hozir band"}
        </Text>
        {m.bio ? <Text style={{ marginTop: 10, color: colors.text }}>{m.bio}</Text> : null}
      </Card>

      {selectForOrderId ? (
        <Button title="Shu ustani tanlash" onPress={choose} loading={busy} />
      ) : (
        <Button
          title="Shu ustaga buyurtma berish"
          onPress={() => navigation.navigate("CreateOrder", { masterId: m.id, masterName: m.full_name })}
        />
      )}
      <Button
        title={isFav ? "Sevimlilardan olib tashlash" : "♡ Sevimlilarga qo'shish"}
        variant="secondary"
        onPress={toggleFav}
      />

      <SectionTitle>Xizmatlar</SectionTitle>
      <Card>
        {m.services.length === 0 ? <Text style={{ color: colors.muted }}>Xizmatlar ko'rsatilmagan</Text> : null}
        {m.services.map((s) => (
          <Row
            key={s.category_id}
            label={s.category_name}
            value={s.pricing_type === "fixed" ? formatPrice(s.base_price) : "Narx taklif qilinadi"}
          />
        ))}
      </Card>

      {m.photos.length > 0 ? (
        <>
          <SectionTitle>Ishlar namunasi</SectionTitle>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12 }}>
            {m.photos.map((p) => (
              <Image
                key={p.id}
                source={{ uri: mediaUrl(p.url) }}
                style={{ width: 140, height: 140, borderRadius: 12, marginRight: 8, backgroundColor: colors.border }}
              />
            ))}
          </ScrollView>
        </>
      ) : null}

      {m.schedule.length > 0 ? (
        <>
          <SectionTitle>Ish jadvali</SectionTitle>
          <Card>
            {[...m.schedule]
              .sort((a, b) => a.weekday - b.weekday)
              .map((d) => (
                <Row
                  key={d.weekday}
                  label={WEEKDAYS[d.weekday] ?? String(d.weekday)}
                  value={d.is_working ? `${d.start_time ?? ""} – ${d.end_time ?? ""}` : "Dam olish"}
                />
              ))}
          </Card>
        </>
      ) : null}

      <SectionTitle>Sharhlar</SectionTitle>
      {reviews.data && reviews.data.reviews.length > 0 ? (
        reviews.data.reviews.map((r, i) => (
          <Card key={i}>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <Text style={{ fontWeight: "600" }}>{r.customer_first_name}</Text>
              <Text style={{ color: colors.star }}>{"★".repeat(r.rating)}</Text>
            </View>
            {r.comment ? <Text style={{ marginTop: 4 }}>{r.comment}</Text> : null}
            <Text style={{ color: colors.muted, fontSize: 12, marginTop: 4 }}>{formatDate(r.created_at)}</Text>
          </Card>
        ))
      ) : (
        <Text style={{ color: colors.muted }}>Hali sharhlar yo'q</Text>
      )}
    </Screen>
  );
}
