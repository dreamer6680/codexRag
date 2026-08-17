"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export type AuthState = { error?: string; notice?: string };

function fields(formData: FormData) {
  return {
    email: String(formData.get("email") || "").trim(),
    password: String(formData.get("password") || ""),
  };
}

export async function signIn(_state: AuthState, formData: FormData): Promise<AuthState> {
  const { email, password } = fields(formData);
  if (!email || password.length < 6) return { error: "请输入有效邮箱和至少 6 位密码" };
  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) return { error: "邮箱或密码不正确" };
  redirect("/");
}

export async function signUp(_state: AuthState, formData: FormData): Promise<AuthState> {
  const { email, password } = fields(formData);
  if (!email || password.length < 6) return { error: "请输入有效邮箱和至少 6 位密码" };
  const supabase = await createClient();
  const { data, error } = await supabase.auth.signUp({ email, password });
  if (error) return { error: error.message };
  if (!data.session) return { notice: "注册成功，请查收验证邮件后登录" };
  redirect("/");
}

export async function signOut() {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect("/login");
}
