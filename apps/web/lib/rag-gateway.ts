export type TokenProvider = () => Promise<string | null>;
export type Fetcher = (input: string | URL | Request, init?: RequestInit) => Promise<Response>;

export function createRagGateway(getToken: TokenProvider, fetcher: Fetcher, baseUrl: string) {
  return async (path: string, init: RequestInit = {}): Promise<Response> => {
    const token = await getToken();
    if (!token) {
      return Response.json({ detail: "请先登录" }, { status: 401 });
    }
    const headers = new Headers(init.headers);
    headers.set("authorization", `Bearer ${token}`);
    try {
      return await fetcher(`${baseUrl.replace(/\/$/, "")}${path}`, {
        ...init,
        headers,
        cache: "no-store",
      });
    } catch {
      return Response.json({ detail: "无法连接本地 RAG 服务" }, { status: 503 });
    }
  };
}
