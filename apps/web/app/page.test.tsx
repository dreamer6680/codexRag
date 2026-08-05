import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "./page";

describe("Home", () => {
  beforeEach(() => {
    vi.stubGlobal("React", React);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows the question that was actually submitted", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({
      status: "answered",
      answer: "新答案",
      citations: [],
    })));
    const user = userEvent.setup();
    render(<Home />);
    const input = screen.getByPlaceholderText(/在知识库中提问/);

    await user.type(input, "  新的查询内容  ");
    await user.click(screen.getByRole("button", { name: /发送/ }));

    expect(await screen.findByText("新的查询内容")).toBeInTheDocument();
  });

  it("shows a safe unavailable result for a 422 response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      Response.json({ detail: "too long" }, { status: 422 }),
    ));
    const user = userEvent.setup();
    render(<Home />);

    await user.type(screen.getByPlaceholderText(/在知识库中提问/), "失败查询");
    await user.click(screen.getByRole("button", { name: /发送/ }));

    expect(await screen.findByText("无法完成本次查询，请稍后重试。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "把团队经验，变成可核验的答案。" })).toBeInTheDocument();
  });

  it("limits the question input to 4000 characters", () => {
    render(<Home />);

    expect(screen.getByPlaceholderText(/在知识库中提问/)).toHaveAttribute("maxlength", "4000");
  });

  it("uses the 移动导航 to reach each workspace view", async () => {
    const user = userEvent.setup();
    render(<Home />);
    const mobileNav = screen.getByRole("navigation", { name: "移动导航" });
    const chatButton = within(mobileNav).getByRole("button", { name: "知识问答" });
    const documentsButton = within(mobileNav).getByRole("button", { name: "我的文档" });
    const parsingButton = within(mobileNav).getByRole("button", { name: "解析任务" });

    expect(chatButton).toHaveAttribute("aria-current", "page");
    expect(parsingButton).not.toHaveAttribute("aria-current");
    expect(within(mobileNav).getAllByRole("button", { current: "page" })).toHaveLength(1);
    await user.click(documentsButton);
    expect(screen.getByRole("heading", { name: "我的文档" })).toBeInTheDocument();
    expect(documentsButton).toHaveAttribute("aria-current", "page");
    expect(within(mobileNav).getAllByRole("button", { current: "page" })).toHaveLength(1);

    await user.click(screen.getAllByRole("button", { name: "查看详情" })[0]);
    expect(screen.getByRole("heading", { name: "产品需求管理规范.pdf" })).toBeInTheDocument();
    expect(documentsButton).toHaveAttribute("aria-current", "page");
    expect(within(mobileNav).getAllByRole("button", { current: "page" })).toHaveLength(1);

    await user.click(chatButton);
    expect(screen.getByRole("heading", { name: "把团队经验，变成可核验的答案。" })).toBeInTheDocument();
    expect(chatButton).toHaveAttribute("aria-current", "page");
    expect(within(mobileNav).getAllByRole("button", { current: "page" })).toHaveLength(1);
  });
});
