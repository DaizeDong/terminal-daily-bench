"""adapters/single_shot.py -- the one-shot patch scaffold.

Gives the model the file(s) to fix and its failing tests, asks for ONE unified diff,
and returns it. No repo exploration, no multi-turn loop. Model call goes to the
generic OpenAI-compatible endpoint configured by env (OPENAI_BASE_URL/OPENAI_API_KEY).
"""
from __future__ import annotations

from typing import Any, List

from .base import AdapterResult, HarnessAdapter


class SingleShotAdapter(HarnessAdapter):
    name = "single_shot"

    def produce_patch(self, task_dir: str, failing_test_ids: List[str],
                      model: str, *, max_tokens: int = 4096, timeout: int = 180,
                      **kwargs: Any) -> AdapterResult:
        try:
            # Local import keeps the registry importable while eval owns adapter
            # selection (and avoids a package-initialization cycle).
            from .. import eval as _eval

            cfg = _eval.load_task(task_dir)
            sif = (cfg.get("environment", {}) or {}).get("docker_image", "")
            targets = _eval.solution_target_files(task_dir)
            import os
            ctx = _eval.extract_repo_files(sif, targets) if sif and os.path.exists(sif) else {}
            instruction = _eval._read(os.path.join(task_dir, "instruction.md"))
            prompt = _eval.build_prompt(instruction, ctx, targets)
            raw = _eval.call_model(model, prompt, max_tokens=max_tokens, timeout=timeout)
            diff = _eval.extract_diff(raw)
            return AdapterResult(patch=diff, telemetry={"model_raw_len": len(raw),
                                                        "touches_tests": _eval.diff_touches_tests(diff)})
        except Exception as e:  # noqa: BLE001 -- a harness failure is a 0-reward attempt, never a crash
            return AdapterResult(patch="", error=f"{type(e).__name__}: {e}")
