import uuid
from .plugin import TestTracerPlugin
from . import constants


def pytest_configure(config):
    config.pluginmanager.register(TestTracerPlugin(config), TestTracerPlugin.name)


def pytest_addoption(parser):
    params = parser.getgroup("Test Tracer")
    params.addoption(
        constants.ARG_RUN_REFERENCE,
        action="store",
        default=str(uuid.uuid4()),
        required=False,
        help="Group all tests into a single test run by giving it a run reference.",
    )

    params.addoption(
        constants.ARG_BUILD_VERSION,
        action="store",
        default=None,
        required=False,
        help="The version of the application under test",
    )
    params.addoption(
        constants.ARG_BUILD_REVISION,
        action="store",
        required=False,
        help="The revision of the application under test",
    )
    params.addoption(
        constants.ARG_PROJECT_NAME,
        action="store",
        required=False,
        help="The name of the project of application under test",
    )
    params.addoption(
        constants.ARG_BRANCH_NAME,
        action="store",
        required=False,
        help="The name of the branch that is under test",
    )
    params.addoption(
        constants.ARG_NO_UPLOAD,
        action="store_true",
        required=False,
        default=False,
        help="Whether to upload results to Test Tracer when finished",
    )
    params.addoption(
        constants.ARG_USE_TEST_TRACER,
        action="store_true",
        required=False,
        default=False,
        help="Whether you want to enable the Test Tracer plugin",
    )
    params.addoption(
        constants.ARG_UPLOAD_TOKEN,
        action="store",
        required=False,
        help="The API token used to authenticate when uploading results",
    )
