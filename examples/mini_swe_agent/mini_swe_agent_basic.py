"""Report the current mini-swe-agent integration incompatibility.

``minisweagent.environments.extra.contree.ContreeEnvironment`` still imports
the removed ``contree_sdk.config.ContreeConfig`` type. It also constructs
``ContreeSync`` from that configuration and cannot accept an explicit client.

The integration must first add support for a user-provided
``contree_client.base.ContreeSyncClient``. Until then, this example cannot use
the current contree-sdk API.
"""


def main() -> None:
    raise RuntimeError("mini-swe-agent's ContreeEnvironment does not support user-provided contree_client clients")


if __name__ == "__main__":
    main()
