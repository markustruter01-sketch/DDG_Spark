"""Send one tiny request to each tier's model and report the result.

    uv run python -m spark.gateway.smoke

For checking connections by hand. It makes real calls to connected
providers (free tiers have daily limits); tests never run it. Keys are
never printed.
"""

from __future__ import annotations

import time

from spark.gateway.service import build_configured_gateway


def main() -> None:
    gateway = build_configured_gateway()
    config = gateway.config
    print(f"Profile: {config.profile}")
    for tier_name, tier in config.tiers.items():
        for key in [tier.default, *([tier.escalation] if tier.escalation else [])]:
            model = config.models[key]
            label = f"{tier_name:7} {model.provider:11} {model.model_id}"
            if not gateway.is_live(model.model_id):
                print(f"{label}: not connected (mock)")
                continue
            started = time.monotonic()
            try:
                reply = gateway.adapters[model.model_id].complete(
                    [{"role": "user", "content": "Reply with the single word: ready"}]
                )
                seconds = time.monotonic() - started
                print(
                    f"{label}: OK in {seconds:.1f} s, "
                    f"{reply.tokens_in} in / {reply.tokens_out} out, "
                    f"reply {reply.text.strip()[:40]!r}"
                )
            except Exception as error:  # noqa: BLE001 - report any provider error
                print(f"{label}: FAILED ({type(error).__name__}: {str(error)[:160]})")


if __name__ == "__main__":
    main()
