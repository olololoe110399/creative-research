# Documentation

Start with the capture workflow to acquire a dataset, or the consumer guide to
process an existing handoff. Documentation describes the 1.0 CLI.

| Task | Guide |
| --- | --- |
| Install the package and dependencies | [Installation](installation.md) |
| Configure accounts, credentials, paths and timeouts | [Configuration](configuration.md) |
| Run acquisition and find the output to hand off | [Capture workflow](capture-workflow.md) |
| Resume, inspect stage states and understand partial runs | [Pipeline contract](pipeline-contract.md) |
| Read an extracted dataset in another system | [Consumer guide](consume-dataset.md) |
| Implement dataset/schema compatibility | [Dataset contract](dataset-contract.md) |
| Find CLI options, defaults and exit codes | [CLI reference](cli-reference.md), [command catalog](commands.md) |
| Resolve capture, download or publication errors | [Troubleshooting](troubleshooting.md) |
| Maintain or release this package | [Architecture](architecture.md), [development](development.md) |

The command catalog is generated from cli/registry.py. Run `make docs-check` to
check catalog drift, local links and CLI syntax in shell examples. This parses
examples without running acquisition or making provider requests; it does not
certify that a live provider or account will succeed.
