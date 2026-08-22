"""Placeholder: mini-swe-agent's ContreeEnvironment does not yet support this contree-sdk release.

`ContreeEnvironment` (`minisweagent.environments.extra.contree`, mini-swe-agent
2.4.6, the latest release as of this writing) still targets the
pre-redesign contree-sdk API: it imports `from contree_sdk import ContreeSync`,
`contree_sdk.config.ContreeConfig`, and
`contree_sdk.sdk.objects.image.ContreeImageSync`, none of which exist in this
release (contree-sdk now builds on `contree_sdk.session.ContreeSession`; see
`examples/langchain/langchain_basic.py` for the equivalent integration shape
against deepagents).

The fix has to land upstream in mini-swe-agent
(https://github.com/SWE-agent/mini-swe-agent) before `ContreeEnvironment` can
be constructed against this contree-sdk release. Until then, this example is
a placeholder rather than a working script.
"""


def main() -> None:
    raise RuntimeError(
        "mini-swe-agent's ContreeEnvironment does not yet support this contree-sdk release; "
        "see this file's module docstring for details"
    )


if __name__ == "__main__":
    main()
