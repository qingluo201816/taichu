"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { listLLMModels } from "@/lib/api/llm";
import {
  isSelectableModel,
  selectInitialModelId,
} from "@/lib/llm/model-selection";
import type { PublicLLMModel } from "@/lib/types/llm";

const STORAGE_KEY = "taichu:last-llm-model-id";

export function useModelSelection() {
  const [models, setModels] = useState<PublicLLMModel[]>([]);
  const [modelId, setModelIdState] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void listLLMModels()
      .then(response => {
        if (!active) return;
        setModels(response.models);
        const remembered = window.localStorage.getItem(STORAGE_KEY) ?? "";
        const selectable = response.models.filter(isSelectableModel);
        const selected = selectInitialModelId(
          response.models,
          response.default_model_id,
          remembered,
        );
        setModelIdState(selected);
        setError(selectable.length ? "" : "当前没有可选择的模型。");
      })
      .catch(caught => {
        if (!active) return;
        setError(caught instanceof Error ? caught.message : "模型列表加载失败。");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const setModelId = useCallback((value: string) => {
    const selectable = models.some(
      model => model.id === value && isSelectableModel(model),
    );
    if (!selectable) return;
    setModelIdState(value);
    window.localStorage.setItem(STORAGE_KEY, value);
  }, [models]);

  return useMemo(
    () => ({ models, modelId, setModelId, loading, error }),
    [models, modelId, setModelId, loading, error],
  );
}
