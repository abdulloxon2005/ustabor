import React, { useState } from "react";
import { Alert, Image, ScrollView, Text, TextInput, View } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { ordersApi } from "../api";
import { Button, Card, ErrorBox, Field, Loading, Row, Screen, SectionTitle, StatusBadge } from "../components/ui";
import { mediaUrl } from "../config";
import { useLoad } from "../hooks";
import type { MainStackParams } from "../navigation/types";
import { colors, formatDate, formatPrice } from "../theme";

function Stars({ value, onChange }: { value: number; onChange?: (v: number) => void }) {
  return (
    <View style={{ flexDirection: "row" }}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Text
          key={n}
          onPress={onChange ? () => onChange(n) : undefined}
          style={{ fontSize: 32, color: n <= value ? colors.star : colors.border, marginRight: 4 }}
        >
          ★
        </Text>
      ))}
    </View>
  );
}

export function OrderDetailScreen({
  route,
  navigation,
}: NativeStackScreenProps<MainStackParams, "OrderDetail">) {
  const { orderId } = route.params;
  const order = useLoad(() => ordersApi.get(orderId), [orderId]);
  const [busy, setBusy] = useState(false);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const [disputeText, setDisputeText] = useState("");
  const [showDispute, setShowDispute] = useState(false);

  if (order.loading) return <Loading />;
  if (order.error || !order.data) return <ErrorBox message={order.error ?? "Buyurtma topilmadi"} onRetry={order.reload} />;
  const o = order.data;

  /** Harakatni bajarib, natijada buyurtmani yangilaydi. */
  const act = async (fn: () => Promise<unknown>, okMsg?: string) => {
    setBusy(true);
    try {
      await fn();
      if (okMsg) Alert.alert(okMsg);
      await order.reload();
    } catch (e) {
      Alert.alert("Xatolik", e instanceof Error ? e.message : "Xatolik yuz berdi");
    } finally {
      setBusy(false);
    }
  };

  const confirm = (title: string, msg: string, fn: () => Promise<unknown>) =>
    Alert.alert(title, msg, [
      { text: "Yo'q", style: "cancel" },
      { text: "Ha", style: "destructive", onPress: () => void act(fn) },
    ]);

  const proposedQuotes = o.quotes.filter((q) => q.status === "proposed");
  const pendingOffers = o.offers.filter((x) => x.status === "pending");
  const canCancel = o.status === "searching" || o.status === "assigned";
  const canDispute = ["assigned", "in_progress", "completed", "cancelled"].includes(o.status);

  return (
    <Screen refreshing={order.refreshing} onRefresh={order.refresh}>
      <Card>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={{ fontSize: 18, fontWeight: "800" }}>
            #{o.id} · {o.category_name}
          </Text>
          <StatusBadge status={o.status} />
        </View>
        <Text style={{ marginTop: 10 }}>{o.description}</Text>
        <View style={{ marginTop: 10 }}>
          <Row label="Manzil" value={`${o.city}, ${o.district}, ${o.address}`} />
          <Row label="Yaratilgan" value={formatDate(o.created_at)} />
          <Row label="Usta tanlash" value={o.selection_mode === "automatic" ? "Avtomatik" : "Qo'lda"} />
          {o.master_full_name ? <Row label="Usta" value={o.master_full_name} /> : null}
          {o.agreed_price !== null ? <Row label="Kelishilgan narx" value={formatPrice(o.agreed_price)} /> : null}
          {o.final_price !== null ? <Row label="Yakuniy narx" value={formatPrice(o.final_price)} /> : null}
        </View>
        {o.note ? <Text style={{ color: colors.muted, marginTop: 6 }}>{o.note}</Text> : null}
      </Card>

      {o.photos.length > 0 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12 }}>
          {o.photos.map((u) => (
            <Image
              key={u}
              source={{ uri: mediaUrl(u) }}
              style={{ width: 110, height: 110, borderRadius: 10, marginRight: 8, backgroundColor: colors.border }}
            />
          ))}
        </ScrollView>
      ) : null}

      {/* Usta qidirish bosqichi */}
      {o.status === "searching" ? (
        <>
          {pendingOffers.length > 0 ? (
            <Card style={{ backgroundColor: colors.warningSoft }}>
              <Text style={{ fontWeight: "600", color: colors.warning }}>
                {o.selection_mode === "automatic"
                  ? `${pendingOffers.length} ta ustaga so'rov yuborilgan. Javob kutilmoqda…`
                  : `${pendingOffers[0].master_full_name || pendingOffers[0].master_name} javobini kutmoqdamiz…`}
              </Text>
            </Card>
          ) : o.selection_mode === "manual" ? (
            <Button
              title="Usta tanlash"
              onPress={() => navigation.navigate("Masters", { categoryId: o.category_id, selectForOrderId: o.id })}
            />
          ) : (
            <Button title="Ustalarni qidirish" onPress={() => act(() => ordersApi.dispatch(o.id))} loading={busy} />
          )}
        </>
      ) : null}

      {/* Narx takliflari */}
      {proposedQuotes.length > 0 ? (
        <>
          <SectionTitle>Narx taklifi</SectionTitle>
          {proposedQuotes.map((q) => (
            <Card key={q.id}>
              <Text style={{ fontSize: 20, fontWeight: "800" }}>{formatPrice(q.price)}</Text>
              {q.note ? <Text style={{ color: colors.muted, marginVertical: 4 }}>{q.note}</Text> : null}
              <View style={{ flexDirection: "row", marginTop: 8 }}>
                <Button
                  title="Qabul qilish"
                  onPress={() => act(() => ordersApi.acceptQuote(o.id, q.id), "Narx qabul qilindi")}
                  disabled={busy}
                  style={{ flex: 1, marginRight: 8 }}
                />
                <Button
                  title="Rad etish"
                  variant="danger"
                  onPress={() => act(() => ordersApi.rejectQuote(o.id, q.id))}
                  disabled={busy}
                  style={{ flex: 1 }}
                />
              </View>
            </Card>
          ))}
        </>
      ) : null}

      {o.master_id ? (
        <Button title="💬 Usta bilan yozishish" variant="secondary" onPress={() => navigation.navigate("Chat", { orderId: o.id })} />
      ) : null}

      {/* Baholash */}
      {o.can_review ? (
        <>
          <SectionTitle>Ustani baholang</SectionTitle>
          <Card>
            <Stars value={rating} onChange={setRating} />
            <TextInput
              placeholder="Fikringiz (ixtiyoriy)"
              value={comment}
              onChangeText={setComment}
              multiline
              style={{
                borderWidth: 1,
                borderColor: colors.border,
                borderRadius: 12,
                padding: 12,
                height: 80,
                marginVertical: 12,
                textAlignVertical: "top",
              }}
            />
            <Button
              title="Yuborish"
              loading={busy}
              onPress={() =>
                act(
                  () => ordersApi.review(o.id, { rating, comment: comment.trim() || undefined }),
                  "Rahmat! Sharhingiz qabul qilindi"
                )
              }
            />
          </Card>
        </>
      ) : null}
      {o.review ? (
        <>
          <SectionTitle>Sizning bahoyingiz</SectionTitle>
          <Card>
            <Stars value={o.review.rating} />
            {o.review.comment ? <Text style={{ marginTop: 6 }}>{o.review.comment}</Text> : null}
          </Card>
        </>
      ) : null}

      {/* Shikoyat */}
      {canDispute ? (
        showDispute ? (
          <Card>
            <Field
              label="Shikoyat sababi"
              value={disputeText}
              onChangeText={setDisputeText}
              multiline
              maxLength={1000}
            />
            <Button
              title="Shikoyat yuborish"
              loading={busy}
              onPress={() =>
                act(async () => {
                  await ordersApi.dispute(o.id, disputeText.trim());
                  setShowDispute(false);
                  setDisputeText("");
                }, "Shikoyat yuborildi")
              }
            />
            <Button title="Bekor qilish" variant="ghost" onPress={() => setShowDispute(false)} />
          </Card>
        ) : (
          <Button title="Shikoyat qilish" variant="ghost" onPress={() => setShowDispute(true)} />
        )
      ) : null}

      {canCancel ? (
        <Button
          title="Buyurtmani bekor qilish"
          variant="danger"
          disabled={busy}
          onPress={() => confirm("Bekor qilish", "Buyurtmani bekor qilmoqchimisiz?", () => ordersApi.cancel(o.id))}
        />
      ) : null}

      <SectionTitle>Tarix</SectionTitle>
      <Card>
        {o.history.map((h) => (
          <View key={h.id} style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 }}>
            <StatusBadge status={h.to_status} />
            <Text style={{ color: colors.muted, fontSize: 12 }}>{formatDate(h.created_at)}</Text>
          </View>
        ))}
      </Card>
    </Screen>
  );
}
