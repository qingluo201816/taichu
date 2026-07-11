import assert from "node:assert/strict";

import {
  isSelectableModel,
  selectInitialModelId,
} from "../../src/lib/llm/model-selection";
import type { PublicLLMModel } from "../../src/lib/types/llm";
import {
  appendWritingStreamText,
  monitoredCostLabel,
  monitoredStatusLabel,
  writingStreamFailure,
} from "../../src/lib/llm/view-model";
import {
  tokenTrendRangeStart,
  tokenTrendTickIndexes,
} from "../../src/lib/llm/token-trend";

const models: PublicLLMModel[] = [
  model("disabled", { enabled: false }),
  model("unavailable", { availability: "unavailable" }),
  model("deepseek-v4-pro", { is_default: true }),
  model("gpt-5-6-luna"),
];

assert.equal(
  selectInitialModelId(models, "deepseek-v4-pro", ""),
  "deepseek-v4-pro",
  "默认模型应来自后端目录",
);
assert.equal(
  selectInitialModelId(models, "deepseek-v4-pro", "gpt-5-6-luna"),
  "gpt-5-6-luna",
  "可记住最近一次有效选择",
);
assert.equal(
  selectInitialModelId(models, "deepseek-v4-pro", "unavailable"),
  "deepseek-v4-pro",
  "不可用模型不能恢复为当前选择",
);
assert.equal(isSelectableModel(models[0]), false, "禁用模型不能选择");
assert.equal(isSelectableModel(models[1]), false, "不可用模型不能选择");
assert.equal(
  selectInitialModelId(
    [
      model("deepseek-v4-pro", {
        is_default: true,
        enabled: false,
        availability: "unavailable",
      }),
      model("gpt-5-6-luna"),
    ],
    "deepseek-v4-pro",
    "",
  ),
  "gpt-5-6-luna",
  "服务端默认模型不可用时应选择首个可用模型",
);

console.log("ok - 模型列表加载、默认选择与不可用状态规则");

assert.equal(
  appendWritingStreamText("秦浩", { type: "text_delta", delta: "轩" }),
  "秦浩轩",
);
assert.equal(
  writingStreamFailure({ type: "run_failed", run_id: "run", message: "调用失败" }),
  "调用失败",
);
assert.equal(
  monitoredCostLabel({
    cost_amount: null,
    cost_currency: "CNY",
    cost_kind: "unavailable",
  }),
  "未配置价格",
);
assert.equal(monitoredStatusLabel("completed"), "成功");
assert.equal(
  tokenTrendRangeStart("24h", Date.parse("2026-07-12T00:00:00Z")),
  "2026-07-11T00:00:00.000Z",
);
assert.equal(tokenTrendRangeStart("all", 0), undefined);
assert.deepEqual(tokenTrendTickIndexes(12), [0, 3, 6, 9, 11]);
console.log("ok - 流式增量、失败状态、费用提示和中文监控文案");

function model(
  id: string,
  overrides: Partial<PublicLLMModel> = {},
): PublicLLMModel {
  return {
    id,
    display_name: id,
    enabled: true,
    is_default: false,
    supports_streaming: true,
    availability: "unknown",
    upstream_verified: false,
    ...overrides,
  };
}
