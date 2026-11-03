import React, { useEffect, useState } from "react";
import { Alert, Image, Pressable, ScrollView, Text, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as Location from "expo-location";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { categoriesApi, ordersApi } from "../api";
import { Button, Chip, ErrorBox, Field, Loading, Screen, SectionTitle } from "../components/ui";
import { useLoad } from "../hooks";
import type { MainStackParams } from "../navigation/types";
import { colors } from "../theme";
import type { SelectionMode } from "../api/types";

const MAX_PHOTOS = 5;

export function CreateOrderScreen({
  route,
  navigation,
}: NativeStackScreenProps<MainStackParams, "CreateOrder">) {
  const params = route.params;
  const cats = useLoad(() => categoriesApi.list());
  const [categoryId, setCategoryId] = useState<number | undefined>(params?.categoryId);
  const [description, setDescription] = useState("");
  const [city, setCity] = useState("");
  const [district, setDistrict] = useState("");
  const [address, setAddress] = useState("");
  const [coords, setCoords] = useState<{ latitude: number; longitude: number } | null>(null);
  // Muayyan ustani tanlab kelgan bo'lsak, rejim har doim "manual"
  const [mode, setMode] = useState<SelectionMode>(params?.masterId ? "manual" : "automatic");
  const [photos, setPhotos] = useState<ImagePicker.ImagePickerAsset[]>([]);
  const [locating, setLocating] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (params?.categoryId) setCategoryId(params.categoryId);
  }, [params?.categoryId]);

  const locate = async () => {
    setLocating(true);
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (perm.status !== "granted") {
        Alert.alert("Ruxsat kerak", "Joylashuvni aniqlash uchun ruxsat bering yoki manzilni qo'lda kiriting.");
        return;
      }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const c = { latitude: pos.coords.latitude, longitude: pos.coords.longitude };
      setCoords(c);
      try {
        const [place] = await Location.reverseGeocodeAsync(c);
        if (place) {
          if (!city) setCity(place.city ?? place.region ?? "");
          if (!district) setDistrict(place.district ?? place.subregion ?? "");
          if (!address) setAddress([place.street, place.streetNumber].filter(Boolean).join(" "));
        }
      } catch {
        /* manzilni qo'lda to'ldirish mumkin */
      }
    } catch (e) {
      Alert.alert("Joylashuv aniqlanmadi", e instanceof Error ? e.message : "Xatolik");
    } finally {
      setLocating(false);
    }
  };

  const pickPhotos = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      allowsMultipleSelection: true,
      selectionLimit: MAX_PHOTOS - photos.length,
      quality: 0.7,
    });
    if (!res.canceled) setPhotos((p) => [...p, ...res.assets].slice(0, MAX_PHOTOS));
  };

  const submit = async () => {
    if (!categoryId) return Alert.alert("Xizmat turini tanlang");
    if (description.trim().length < 5) return Alert.alert("Muammoni kamida 5 ta belgi bilan tasvirlab bering");
    if (!city.trim() || !district.trim() || !address.trim())
      return Alert.alert("Shahar, tuman va manzilni to'ldiring");

    setBusy(true);
    try {
      const order = await ordersApi.create({
        category_id: categoryId,
        description: description.trim(),
        city: city.trim(),
        district: district.trim(),
        address: address.trim(),
        selection_mode: mode,
        ...(coords ?? {}),
      });

      const warnings: string[] = [];
      if (photos.length > 0) {
        try {
          await ordersApi.uploadPhotos(
            order.id,
            photos.map((p, i) => ({
              uri: p.uri,
              name: p.fileName ?? `photo_${i}.jpg`,
              type: p.mimeType ?? "image/jpeg",
            }))
          );
        } catch (e) {
          warnings.push(`Rasmlar yuklanmadi: ${e instanceof Error ? e.message : "xatolik"}`);
        }
      }
      if (params?.masterId) {
        try {
          await ordersApi.selectMaster(order.id, params.masterId);
        } catch (e) {
          warnings.push(`Usta tanlanmadi: ${e instanceof Error ? e.message : "xatolik"}`);
        }
      } else if (mode === "automatic") {
        try {
          await ordersApi.dispatch(order.id);
        } catch (e) {
          warnings.push(`Usta qidirish boshlanmadi: ${e instanceof Error ? e.message : "xatolik"}`);
        }
      }
      if (warnings.length) Alert.alert("Buyurtma yaratildi", warnings.join("\n"));
      navigation.replace("OrderDetail", { orderId: order.id });
    } catch (e) {
      Alert.alert("Buyurtma yaratilmadi", e instanceof Error ? e.message : "Xatolik");
    } finally {
      setBusy(false);
    }
  };

  if (cats.loading) return <Loading />;
  if (cats.error) return <ErrorBox message={cats.error} onRetry={cats.reload} />;

  return (
    <Screen>
      {params?.masterName ? (
        <View style={{ backgroundColor: colors.primarySoft, padding: 12, borderRadius: 12, marginBottom: 14 }}>
          <Text style={{ color: colors.primaryDark }}>
            Usta: <Text style={{ fontWeight: "700" }}>{params.masterName}</Text>
          </Text>
        </View>
      ) : null}

      <SectionTitle>Xizmat turi</SectionTitle>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 14 }}>
        {(cats.data ?? [])
          .filter((c) => c.is_active)
          .map((c) => (
            <Chip key={c.id} label={c.name} active={categoryId === c.id} onPress={() => setCategoryId(c.id)} />
          ))}
      </ScrollView>

      <Field
        label="Muammoni tasvirlab bering"
        value={description}
        onChangeText={setDescription}
        multiline
        placeholder="Masalan: oshxonadagi kran oqyapti"
        maxLength={2000}
      />

      <SectionTitle>Manzil</SectionTitle>
      <Button
        title={coords ? "✓ Joylashuv aniqlandi (qayta aniqlash)" : "📍 Joylashuvimni aniqlash"}
        variant="secondary"
        onPress={locate}
        loading={locating}
      />
      <Field label="Shahar" value={city} onChangeText={setCity} />
      <Field label="Tuman" value={district} onChangeText={setDistrict} />
      <Field label="Ko'cha, uy, xonadon" value={address} onChangeText={setAddress} />

      {!params?.masterId ? (
        <>
          <SectionTitle>Usta tanlash usuli</SectionTitle>
          <View style={{ flexDirection: "row", marginBottom: 14 }}>
            <Chip label="Avtomatik (tavsiya)" active={mode === "automatic"} onPress={() => setMode("automatic")} />
            <Chip label="O'zim tanlayman" active={mode === "manual"} onPress={() => setMode("manual")} />
          </View>
          <Text style={{ color: colors.muted, fontSize: 13, marginTop: -6, marginBottom: 14 }}>
            {mode === "automatic"
              ? "Yaqin atrofdagi ustalarga so'rov yuboriladi, birinchi qabul qilgani biriktiriladi."
              : "Buyurtmadan so'ng ustalar ro'yxatidan o'zingiz tanlaysiz."}
          </Text>
        </>
      ) : null}

      <SectionTitle>Rasmlar ({photos.length}/{MAX_PHOTOS})</SectionTitle>
      <View style={{ flexDirection: "row", flexWrap: "wrap", marginBottom: 10 }}>
        {photos.map((p, i) => (
          <Pressable
            key={p.uri + i}
            onPress={() => setPhotos((arr) => arr.filter((_, idx) => idx !== i))}
            style={{ marginRight: 8, marginBottom: 8 }}
          >
            <Image source={{ uri: p.uri }} style={{ width: 72, height: 72, borderRadius: 10 }} />
            <Text style={{ position: "absolute", right: 4, top: 2, color: "#fff", fontWeight: "800" }}>✕</Text>
          </Pressable>
        ))}
      </View>
      {photos.length < MAX_PHOTOS ? <Button title="+ Rasm qo'shish" variant="secondary" onPress={pickPhotos} /> : null}

      <Button title="Buyurtma berish" onPress={submit} loading={busy} style={{ marginTop: 8 }} />
    </Screen>
  );
}
