"use client";

import { useActionState, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { signIn, signUp, type AuthState } from "@/app/login/actions";

const initialState: AuthState = {};

export function AuthForm() {
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [signInState, signInAction, signInPending] = useActionState(signIn, initialState);
  const [signUpState, signUpAction, signUpPending] = useActionState(signUp, initialState);
  const state = mode === "sign-in" ? signInState : signUpState;
  const pending = mode === "sign-in" ? signInPending : signUpPending;

  return <div>
    <div className="mb-7 flex rounded-lg bg-zinc-100 p-1 text-sm">
      <button type="button" onClick={() => setMode("sign-in")} className={`flex-1 rounded-md px-3 py-2 ${mode === "sign-in" ? "bg-white font-medium shadow-sm" : "text-zinc-500"}`}>登录</button>
      <button type="button" onClick={() => setMode("sign-up")} className={`flex-1 rounded-md px-3 py-2 ${mode === "sign-up" ? "bg-white font-medium shadow-sm" : "text-zinc-500"}`}>注册</button>
    </div>
    <form action={mode === "sign-in" ? signInAction : signUpAction} className="space-y-4">
      <label className="block text-sm font-medium">邮箱<Input name="email" type="email" autoComplete="email" required className="mt-2" placeholder="name@example.com" /></label>
      <label className="block text-sm font-medium">密码<Input name="password" type="password" autoComplete={mode === "sign-in" ? "current-password" : "new-password"} minLength={6} required className="mt-2" placeholder="至少 6 位" /></label>
      {state.error && <p role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{state.error}</p>}
      {state.notice && <p className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-800">{state.notice}</p>}
      <Button className="w-full" disabled={pending}>{pending ? "处理中…" : mode === "sign-in" ? "进入知识库" : "创建账户"}</Button>
    </form>
  </div>;
}
