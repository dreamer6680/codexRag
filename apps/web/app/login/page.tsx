import { AuthForm } from "@/components/auth-form";
import { isSupabaseConfigured } from "@/lib/auth";

export default function LoginPage() {
  const configured = isSupabaseConfigured();
  return <main className="grid min-h-screen bg-zinc-950 lg:grid-cols-[1.15fr_.85fr]">
    <section className="relative hidden overflow-hidden border-r border-white/10 p-12 text-white lg:flex lg:flex-col lg:justify-between">
      <div className="absolute inset-0 opacity-30 [background-image:linear-gradient(rgba(255,255,255,.07)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.07)_1px,transparent_1px)] [background-size:48px_48px]" />
      <div className="relative flex items-center gap-3 text-lg font-semibold"><span className="grid h-9 w-9 place-items-center rounded-lg bg-white text-zinc-950">知</span>知见</div>
      <div className="relative max-w-xl">
        <p className="font-mono text-xs tracking-[.22em] text-blue-300">PRIVATE EVIDENCE WORKSPACE</p>
        <h1 className="mt-5 text-5xl font-semibold leading-[1.12] tracking-tight">你的资料，只回答你的问题。</h1>
        <p className="mt-6 max-w-lg text-base leading-8 text-zinc-300">每个账户拥有独立的文档、检索范围和对话记忆。答案保留原文引用，也保留问题如何一步步推进。</p>
      </div>
      <p className="relative text-xs text-zinc-500">身份由 Supabase 验证 · 业务数据保存在本地</p>
    </section>
    <section className="grid place-items-center bg-zinc-50 px-6 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 lg:hidden"><span className="grid h-10 w-10 place-items-center rounded-lg bg-zinc-900 font-semibold text-white">知</span></div>
        <h2 className="text-3xl font-semibold tracking-tight">回到你的知识空间</h2>
        <p className="mt-2 text-sm leading-6 text-zinc-500">登录后查看个人文档和历史聊天。</p>
        <div className="mt-8 rounded-xl border bg-white p-6 shadow-sm">
          {configured ? <AuthForm /> : <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">尚未配置 Supabase。请在环境变量中设置项目 URL 和匿名公钥后重新启动前端。</div>}
        </div>
      </div>
    </section>
  </main>;
}
