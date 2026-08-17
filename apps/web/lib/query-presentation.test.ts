import assert from "node:assert/strict";
import test from "node:test";

import { evidenceBanner } from "./query-presentation.ts";

test("does not present candidate count as confidence when backend confidence is none", () => {
  assert.equal(evidenceBanner("none", 12), null);
});

test("uses cautious wording for low-confidence evidence", () => {
  assert.deepEqual(evidenceBanner("low", 4), {
    className: "border-amber-500 bg-amber-50 text-amber-800",
    label: "检索到 4 条相关性较弱的证据，请结合原文核验",
  });
});

test("shows high confidence only when the backend reports high", () => {
  assert.deepEqual(evidenceBanner("high", 2), {
    className: "border-emerald-500 bg-emerald-50 text-emerald-800",
    label: "检索到 2 条高相关证据",
  });
});
