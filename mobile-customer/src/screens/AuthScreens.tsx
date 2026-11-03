import React, { useState } from "react";
import { Alert, Text, View } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { authApi } from "../api";
import { useAuth } from "../auth/AuthContext";
import { Button, Field, Screen } from "../components/ui";
import type { AuthStackParams } from "../navigation/types";
import { colors } from "../theme";

function Header({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <View style={{ marginTop: 32, marginBottom: 28 }}>
      <Text style={{ fontSize: 30, fontWeight: "800", color: colors.primary }}>UstaBor</Text>
      <Text style={{ fontSize: 22, fontWeight: "700", color: colors.text, marginTop: 18 }}>{title}</Text>
      <Text style={{ color: colors.muted, marginTop: 4 }}>{subtitle}</Text>
    </View>
  );
}

export function LoginScreen({ navigation }: NativeStackScreenProps<AuthStackParams, "Login">) {
  const { login } = useAuth();
  const [phone, setPhone] = useState("+998");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!password) return Alert.alert("Xatolik", "Parolni kiriting");
    setBusy(true);
    try {
      await login(phone, password);
    } catch (e) {
      Alert.alert("Kirib bo'lmadi", e instanceof Error ? e.message : "Xatolik");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Header title="Xush kelibsiz" subtitle="Hisobingizga kiring" />
      <Field label="Telefon raqam" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
      <Field label="Parol" value={password} onChangeText={setPassword} secureTextEntry />
      <Button title="Kirish" onPress={submit} loading={busy} />
      <Button title="Parolni unutdingizmi?" variant="ghost" onPress={() => navigation.navigate("ForgotPassword")} />
      <Button title="Ro'yxatdan o'tish" variant="secondary" onPress={() => navigation.navigate("Register")} />
    </Screen>
  );
}

export function RegisterScreen({ navigation }: NativeStackScreenProps<AuthStackParams, "Register">) {
  const { completeAuth } = useAuth();
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("+998");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const fail = (title: string, e: unknown) =>
    Alert.alert(title, e instanceof Error ? e.message : "Xatolik yuz berdi");

  const sendOtp = async () => {
    setBusy(true);
    try {
      await authApi.requestRegisterOtp(phone);
      setOtpSent(true);
      Alert.alert("Kod yuborildi", "Telefoningizga 6 xonali tasdiqlash kodi yuborildi.");
    } catch (e) {
      fail("Kod yuborilmadi", e);
    } finally {
      setBusy(false);
    }
  };

  const register = async () => {
    setBusy(true);
    try {
      const t = await authApi.register({ phone, password, full_name: fullName, otp_code: otp });
      await completeAuth(t);
    } catch (e) {
      fail("Ro'yxatdan o'tib bo'lmadi", e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Header title="Ro'yxatdan o'tish" subtitle="Mijoz hisobini yarating" />
      <Field label="Ism familiya" value={fullName} onChangeText={setFullName} editable={!otpSent} />
      <Field
        label="Telefon raqam"
        value={phone}
        onChangeText={setPhone}
        keyboardType="phone-pad"
        editable={!otpSent}
      />
      <Field
        label="Parol (kamida 8 belgi, harf va raqam)"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        editable={!otpSent}
      />
      {otpSent ? (
        <>
          <Field
            label="Tasdiqlash kodi"
            value={otp}
            onChangeText={setOtp}
            keyboardType="number-pad"
            maxLength={6}
          />
          <Button title="Ro'yxatdan o'tish" onPress={register} loading={busy} />
          <Button title="Kodni qayta yuborish" variant="ghost" onPress={sendOtp} disabled={busy} />
        </>
      ) : (
        <Button title="Kod olish" onPress={sendOtp} loading={busy} />
      )}
      <Button title="Hisobim bor" variant="ghost" onPress={() => navigation.goBack()} />
    </Screen>
  );
}

export function ForgotPasswordScreen({
  navigation,
}: NativeStackScreenProps<AuthStackParams, "ForgotPassword">) {
  const [phone, setPhone] = useState("+998");
  const [otp, setOtp] = useState("");
  const [password, setPassword] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const fail = (title: string, e: unknown) =>
    Alert.alert(title, e instanceof Error ? e.message : "Xatolik yuz berdi");

  const sendOtp = async () => {
    setBusy(true);
    try {
      await authApi.requestResetOtp(phone);
      setOtpSent(true);
    } catch (e) {
      fail("Kod yuborilmadi", e);
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    setBusy(true);
    try {
      await authApi.confirmReset({ phone, otp_code: otp, new_password: password });
      Alert.alert("Tayyor", "Parol yangilandi. Endi kirishingiz mumkin.", [
        { text: "OK", onPress: () => navigation.navigate("Login") },
      ]);
    } catch (e) {
      fail("Parolni tiklab bo'lmadi", e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Header title="Parolni tiklash" subtitle="Telefon raqamingizga kod yuboramiz" />
      <Field
        label="Telefon raqam"
        value={phone}
        onChangeText={setPhone}
        keyboardType="phone-pad"
        editable={!otpSent}
      />
      {otpSent ? (
        <>
          <Field label="Tasdiqlash kodi" value={otp} onChangeText={setOtp} keyboardType="number-pad" maxLength={6} />
          <Field label="Yangi parol" value={password} onChangeText={setPassword} secureTextEntry />
          <Button title="Parolni yangilash" onPress={confirm} loading={busy} />
        </>
      ) : (
        <Button title="Kod olish" onPress={sendOtp} loading={busy} />
      )}
      <Button title="Orqaga" variant="ghost" onPress={() => navigation.goBack()} />
    </Screen>
  );
}
