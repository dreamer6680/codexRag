# Frontend Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the five confirmed frontend review issues and add automated regression coverage for query failures, submitted-question rendering, mobile navigation, upload size enforcement, and lint execution.

**Architecture:** Keep the existing Next.js App Router structure. Extract query response validation into a small client-safe module, keep page state in `Home`, render a compact mobile navigation in the existing header, and reject oversized files at the upload proxy boundary before reading their contents. Vitest and React Testing Library provide focused regression tests without adding a browser E2E framework.

**Tech Stack:** Next.js 15.5, React 19, TypeScript 5, Tailwind CSS 4, Vitest, React Testing Library, ESLint 9 with `eslint-config-next`.

## Global Constraints

- The query limit is exactly 4000 characters, matching `QueryRequest.question` in the Python RAG service.
- The upload limit is exactly 50 MB (`50 * 1024 * 1024` bytes), matching `.env.example` and the Python RAG default.
- Non-2xx, invalid JSON, and structurally invalid query responses must render an `unavailable` result with an empty `citations` array.
- The desktop sidebar remains unchanged; mobile navigation is visible below the `lg` breakpoint.
- Do not introduce Playwright or refactor unrelated demo content.

---

### Task 1: Test Harness and Query Response Normalization

**Files:**
- Modify: `apps/web/package.json`
- Modify: `apps/web/package-lock.json`
- Create: `apps/web/vitest.config.ts`
- Create: `apps/web/test/setup.ts`
- Create: `apps/web/lib/query-result.ts`
- Test: `apps/web/lib/query-result.test.ts`

**Interfaces:**
- Produces: `Citation`, `QueryResult`, `UNAVAILABLE_RESULT`, and `readQueryResult(response: Response): Promise<QueryResult>`.
- `readQueryResult` returns the upstream result only for an OK response with valid `status`, string `answer`, and array `citations`.

- [ ] **Step 1: Install the test dependencies and add the test script**

Run from `apps/web`:

```powershell
npm install --save-dev vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

Set the package script to:

```json
"test": "vitest run"
```

- [ ] **Step 2: Configure Vitest**

Create `vitest.config.ts` with the React-compatible jsdom environment, `@/` alias, and `test/setup.ts`. Import `@testing-library/jest-dom/vitest` from the setup file.

- [ ] **Step 3: Write failing query normalization tests**

Cover these cases in `lib/query-result.test.ts`:

```ts
const validResult = {
  status: "answered" as const,
  answer: "可核验答案",
  citations: [],
};

it("returns a valid successful query result", async () => {
  const response = Response.json(validResult);
  await expect(readQueryResult(response)).resolves.toEqual(validResult);
});

it("converts a 422 response into unavailable", async () => {
  const response = Response.json({ detail: "too long" }, { status: 422 });
  await expect(readQueryResult(response)).resolves.toMatchObject({
    status: "unavailable",
    citations: [],
  });
});

it("converts invalid JSON into unavailable", async () => {
  const response = new Response("not-json", { status: 200 });
  await expect(readQueryResult(response)).resolves.toMatchObject({
    status: "unavailable",
    citations: [],
  });
});

it("converts a malformed success payload into unavailable", async () => {
  const response = Response.json({ status: "answered", answer: "missing citations" });
  await expect(readQueryResult(response)).resolves.toMatchObject({
    status: "unavailable",
    citations: [],
  });
});
```

- [ ] **Step 4: Run the tests and verify RED**

Run: `npm test -- lib/query-result.test.ts`

Expected: FAIL because `readQueryResult` and its module do not exist.

- [ ] **Step 5: Implement the minimal parser**

Create `lib/query-result.ts`. Parse JSON inside `try/catch`, require `response.ok`, validate the three required fields, and otherwise return a fresh unavailable object with `answer: "无法完成本次查询，请稍后重试。"` and `citations: []`.

- [ ] **Step 6: Run the focused tests and verify GREEN**

Run: `npm test -- lib/query-result.test.ts`

Expected: all four tests PASS.

- [ ] **Step 7: Commit the query parser and test harness**

```powershell
git add apps/web/package.json apps/web/package-lock.json apps/web/vitest.config.ts apps/web/test/setup.ts apps/web/lib/query-result.ts apps/web/lib/query-result.test.ts
git commit -m "test: add frontend query regression harness"
```

---

### Task 2: Safe Query State and Correct Submitted Question

**Files:**
- Modify: `apps/web/app/page.tsx`
- Test: `apps/web/app/page.test.tsx`

**Interfaces:**
- Consumes: `QueryResult` and `readQueryResult` from `@/lib/query-result`.
- Produces: `Home` behavior that displays the submitted trimmed question and always renders a structurally safe result.

- [ ] **Step 1: Write failing page interaction tests**

In `app/page.test.tsx`, mock `global.fetch` and cover:

```ts
it("shows the question that was actually submitted", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({
    status: "answered",
    answer: "新答案",
    citations: [],
  })));
  const user = userEvent.setup();
  render(<Home />);
  const input = screen.getByPlaceholderText(/在知识库中提问/);
  await user.type(input, "新的查询内容");
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
```

- [ ] **Step 2: Run the page tests and verify RED**

Run: `npm test -- app/page.test.tsx`

Expected: the submitted-question assertion fails because the bubble is hard-coded; the max-length assertion fails because the attribute is absent.

- [ ] **Step 3: Implement minimal query state changes**

Move the shared query types to `lib/query-result.ts`, import them into the page, add `submittedQuestion` state initialized to the existing demo question, and update it with `question.trim()` immediately before the fetch. Replace direct `response.json()` with `readQueryResult(response)`. Render `submittedQuestion` in the user bubble and add `maxLength={4000}` to `Input`.

- [ ] **Step 4: Run the page tests and verify GREEN**

Run: `npm test -- app/page.test.tsx`

Expected: all page tests PASS without React console warnings.

- [ ] **Step 5: Commit the query UI fix**

```powershell
git add apps/web/app/page.tsx apps/web/app/page.test.tsx
git commit -m "fix: handle query failures and submitted text"
```

---

### Task 3: Reachable Mobile Navigation

**Files:**
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/app/page.test.tsx`

**Interfaces:**
- Produces: a `MobileNav` or equivalent header section with buttons for `chat`, `documents`, and `parsing` and an `aria-current="page"` marker for the active destination.

- [ ] **Step 1: Write the failing navigation test**

Add a test that renders `Home`, finds a navigation landmark named “移动导航”, clicks “我的文档”, asserts that the documents heading appears, then clicks “知识问答” and asserts that the chat heading appears.

- [ ] **Step 2: Run the test and verify RED**

Run: `npm test -- app/page.test.tsx -t "移动导航"`

Expected: FAIL because no mobile navigation landmark exists.

- [ ] **Step 3: Implement the compact mobile navigation**

Add a `lg:hidden` navigation region in or directly below the header. Reuse the existing `nav` destinations, make buttons keyboard-accessible, set the active item for `detail` to `documents`, and add `aria-current="page"` only to the active button.

- [ ] **Step 4: Run the page test suite and verify GREEN**

Run: `npm test -- app/page.test.tsx`

Expected: all interaction and navigation tests PASS.

- [ ] **Step 5: Commit the navigation fix**

```powershell
git add apps/web/app/page.tsx apps/web/app/page.test.tsx
git commit -m "fix: add mobile workspace navigation"
```

---

### Task 4: Reject Oversized Uploads Before PDF Parsing

**Files:**
- Modify: `apps/web/app/api/documents/upload/route.ts`
- Test: `apps/web/app/api/documents/upload/route.test.ts`

**Interfaces:**
- Produces: exported `MAX_UPLOAD_BYTES = 50 * 1024 * 1024` and POST behavior that returns status 413 before calling `File.arrayBuffer()` or `processPdf`.

- [ ] **Step 1: Write the failing route test**

Mock `@firecrawl/pdf-inspector`, create an empty PDF `File`, override its `size` to `MAX_UPLOAD_BYTES + 1`, and replace `arrayBuffer` with a spy that throws if invoked. Pass a minimal request object whose `formData()` returns the file. Assert status 413, the stable size error, and that neither `arrayBuffer` nor `processPdf` was called:

```ts
const processPdf = vi.hoisted(() => vi.fn());
vi.mock("@firecrawl/pdf-inspector", () => ({ processPdf }));

it("rejects an oversized file before reading or parsing it", async () => {
  const file = new File([], "large.pdf", { type: "application/pdf" });
  const arrayBuffer = vi.fn(() => Promise.reject(new Error("must not read")));
  Object.defineProperty(file, "size", { value: MAX_UPLOAD_BYTES + 1 });
  Object.defineProperty(file, "arrayBuffer", { value: arrayBuffer });
  const form = new FormData();
  form.append("file", file);

  const response = await POST({ formData: async () => form } as NextRequest);

  expect(response.status).toBe(413);
  await expect(response.json()).resolves.toEqual({ detail: "文件不能超过 50 MB" });
  expect(arrayBuffer).not.toHaveBeenCalled();
  expect(processPdf).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run the route test and verify RED**

Run: `npm test -- app/api/documents/upload/route.test.ts`

Expected: FAIL because the route attempts to read/parse the file or because `MAX_UPLOAD_BYTES` is not exported.

- [ ] **Step 3: Add the pre-read size guard**

Immediately after the existing `instanceof File` check, return:

```ts
NextResponse.json(
  { detail: "文件不能超过 50 MB" },
  { status: 413 },
);
```

when `file.size > MAX_UPLOAD_BYTES`.

- [ ] **Step 4: Run the route test and verify GREEN**

Run: `npm test -- app/api/documents/upload/route.test.ts`

Expected: PASS and no parser/read spy calls.

- [ ] **Step 5: Commit the upload guard**

```powershell
git add apps/web/app/api/documents/upload/route.ts apps/web/app/api/documents/upload/route.test.ts
git commit -m "fix: reject oversized uploads before parsing"
```

---

### Task 5: Non-Interactive ESLint Configuration

**Files:**
- Modify: `apps/web/package.json`
- Modify: `apps/web/package-lock.json`
- Create: `apps/web/eslint.config.mjs`

**Interfaces:**
- Produces: `npm run lint` using `eslint . --max-warnings=0` with Next.js core-web-vitals and TypeScript rules.

- [ ] **Step 1: Capture the current failing check**

Run: `npm run lint`

Expected: FAIL by entering the interactive `next lint` configuration prompt.

- [ ] **Step 2: Install matching lint dependencies**

Run from `apps/web`:

```powershell
npm install --save-dev eslint@^9 eslint-config-next@15.5.22
```

- [ ] **Step 3: Configure the ESLint CLI**

Change the script to `eslint . --max-warnings=0`. Create a flat config using `eslint-config-next/core-web-vitals` and `eslint-config-next/typescript`, and globally ignore `.next/**`, `node_modules/**`, and `tsconfig.tsbuildinfo`.

- [ ] **Step 4: Run lint and fix only actionable findings**

Run: `npm run lint`

Expected: PASS non-interactively. Fix rule violations in files already within this plan; do not perform unrelated refactors.

- [ ] **Step 5: Commit the lint configuration**

```powershell
git add apps/web/package.json apps/web/package-lock.json apps/web/eslint.config.mjs apps/web/app/page.tsx apps/web/app/page.test.tsx apps/web/lib/query-result.ts
git commit -m "chore: configure non-interactive frontend lint"
```

---

### Task 6: Full Verification

**Files:**
- Verify only; modify a prior task file only if its check exposes a regression.

**Interfaces:**
- Consumes all preceding deliverables.
- Produces a clean test, lint, type-check, and production-build result.

- [ ] **Step 1: Run all unit and component tests**

Run: `npm test`

Expected: PASS with no failed tests or unhandled errors.

- [ ] **Step 2: Run lint**

Run: `npm run lint`

Expected: PASS non-interactively with zero warnings.

- [ ] **Step 3: Run TypeScript validation**

Run: `npx tsc --noEmit --pretty false`

Expected: PASS with no diagnostics.

- [ ] **Step 4: Run the production build**

Run: `npm run build`

Expected: PASS. The existing multiple-lockfile workspace-root warning may remain because removing unrelated lockfiles is outside scope.

- [ ] **Step 5: Review the final diff**

Run:

```powershell
git status --short
git diff --check
git log --oneline -6
```

Confirm that unrelated user files remain untouched and every requirement in the design has a corresponding passing test or check.
