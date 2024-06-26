import uuid
from .plugin import TestTracerPlugin


def pytest_configure(config):
    config.pluginmanager.register(TestTracerPlugin(config), TestTracerPlugin.name)


def pytest_addoption(parser):
    params = parser.getgroup("Test Tracer")
    params.addoption(
        "--test-tracer-run-reference",
        action="store",
        default=str(uuid.uuid4()),
        required=False,
        help="Group all tests into a single test run by giving it a run reference.",
    )

    params.addoption(
        "--build-version",
        action="store",
        default=None,
        required=False,
        help="The version of the application under test",
    )
    params.addoption(
        "--build-revision",
        action="store",
        required=True,
        help="The revision of the application under test",
    )
    params.addoption(
        "--test-tracer-project-name",
        action="store",
        required=True,
        help="The name of the project of application under test",
    )
    params.addoption(
        "--branch-name",
        action="store",
        required=True,
        help="The name of the branch that is under test",
    )
    params.addoption(
        "--test-tracer-upload-results",
        action="store",
        required=False,
        default=True,
        choices=("True", "False"),
        help="Whether to upload results to Test Tracer when finished",
    )
    params.addoption(
        "--test-tracer-upload-token",
        action="store",
        required=False,
        help="The API token used to authenticate when uploading results",
    )
