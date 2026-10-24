"""cdk-factory wizard toolkit.

A generic, reusable, fully-unit-testable toolkit for building guided,
``aws``-style CLI wizards on top of :class:`CdkDeploymentCommand`.

This package is imported ONLY when a wizard subcommand runs. It is kept
side-effect-free at import time: importing ``cdk_factory.wizard`` (or any of its
submodules) triggers zero ``boto3`` client creation and does NOT eagerly import
``questionary``/``rich`` — those heavy, operator-only dependencies are imported
lazily inside the classes that use them. This is what keeps the wizard off the
synth path and out of any bundled Lambda asset (design §2.1/§2.12, NFR-2).
"""
