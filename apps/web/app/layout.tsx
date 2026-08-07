import "./globals.css";

export const metadata = {
  title: "知见 · 团队知识库",
  description: "可追溯的团队 RAG 知识工作台",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
