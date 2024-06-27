from datetime import datetime, timezone
import glob
import json
from pathlib import Path
import shutil
import socket
import uuid
import zipfile
import pytest
import requests
import logging


class TestTracerPlugin:
    TEST_TRACER_RESULTS_PATH = "./test_tracer"
    TEST_TRACER_BASE_URL = "https://api.testtracer.io"
    test_data = {}
    name = "Test Tracer for Pytest"

    def __init__(self, config):
        log_level = logging.DEBUG if config.option.verbose > 1 else logging.INFO
        logging.basicConfig(level=log_level)
        self.logger = logging.getLogger(self.name)
        self.__validate_arguments(config)
        self.test_data = {}
        self.__reset_results_folder()

    # hooks

    def pytest_sessionfinish(self, session):
        if not self.enabled:
            return

        self.__zip_results()

        if self.should_upload_results == True:
            self.__upload_results()
            self.__process_results()
        else:
            self.logger.debug(
                "Not uploading results as the --test-tracer-no-upload argument was used"
            )

    @pytest.mark.hookwrapper
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo):
        # make a note of the test start time.
        # it's not always reliably available from Pytest itself
        if call.when == "setup":
            self.start_time = datetime.fromtimestamp(call.start, timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%f%z"
            )

        outcome = yield

        # don't do anything on the 'call' part of the lifecycle
        if call.when != "call":
            return

        self.save_test_report(item, call, outcome)

    # end hooks

    def __validate_arguments(self, config):
        self.enabled = config.getoption("--use-test-tracer")

        if self.enabled == False:
            self.logger.debug(
                "Test Tracer is not enabled. Add the --use-test-tracer argument to enable it"
            )
            return

        self.run_reference = config.getoption("--test-tracer-run-reference")
        self.build_version = config.getoption("--build-version")
        self.build_revision = config.getoption("--build-revision")

        if self.build_revision is None:
            raise ValueError("Test Tracer requires a --build-revision argument")

        self.project_name = config.getoption("--test-tracer-project-name")

        if self.project_name is None:
            raise ValueError(
                "Test Tracer requires a --test-tracer-project-name argument"
            )

        self.branch_name = config.getoption("--branch-name")

        if self.branch_name is None:
            raise ValueError("Test Tracer requires a --branch-name argument")

        self.should_upload_results = (
            config.getoption("--test-tracer-no-upload") == False
        )
        self.upload_token = config.getoption("--test-tracer-upload-token")

        if self.upload_token is None and self.should_upload_results:
            raise ValueError(
                "You must provide a --test-tracer-upload-token argument in order to upload results"
            )

    def __reset_results_folder(self):
        if not self.enabled:
            return

        self.logger.debug("Create empty test_tracer folder")
        shutil.rmtree(
            self.TEST_TRACER_RESULTS_PATH,
        )
        Path(self.TEST_TRACER_RESULTS_PATH).mkdir(exist_ok=True)

    def __zip_results(self):
        """
        Compress all the result .json files into a zip file, ready for uploading
        """
        with zipfile.ZipFile(f"{self.TEST_TRACER_RESULTS_PATH}/results.zip", "w") as f:
            for file in glob.glob(f"{self.TEST_TRACER_RESULTS_PATH}/*.json"):
                f.write(file)

    def __upload_results(self):
        self.logger.info("Uploading results to Test Tracer...")
        self.__make_request(
            self.upload_token,
            f"{self.TEST_TRACER_BASE_URL}/api/test-data/upload",
            {"file": open(f"{self.TEST_TRACER_RESULTS_PATH}/results.zip", "rb")},
        )

    def __process_results(self):
        self.logger.info("Processing results on Test Tracer...")
        self.__make_request(
            self.upload_token,
            f"{self.TEST_TRACER_BASE_URL}/api/test-data/process",
            None,
        )

    def __make_request(self, token, url, files):
        if token is None:
            raise ValueError(
                "You must provide a --test-tracer-upload-token parameter in order to upload results"
            )

        response = requests.post(
            url,
            headers={"x-api-key": token, "Accept-Encoding": "gzip, deflate"},
            files=files,
        )

        if response.status_code >= 200 and response.status_code < 400:
            return

        if response.status_code == 401:
            self.logger.fatal(
                "Failed to authenticate with Test Tracer.  Ensure that your API Token is valid"
            )
        elif response.status_code == 403:
            self.logger.fatal(
                "Your API Token does not have permission to upload results"
            )
        else:
            self.logger.warn(
                f"Test Tracer responded with a {response.status_code} status code. It will be back up and running soon"
            )

    def save_test_report(self, item: pytest.Item, call, outcome):
        if not self.enabled:
            return

        result = outcome.get_result()

        # write the failure information if the test failed
        if result.longrepr and result.outcome == "failed":
            self.test_data["failure"] = {
                "reason": result.longrepr.reprcrash.message,
                "trace": str(result.longrepr.reprtraceback),
            }

        # save tags, not including the three default pytest markers
        tags = [
            marker.name
            for marker in item.own_markers
            if marker.name != "parametrize"
            and marker.name != "flaky"
            and marker.name != "usefixtures"
        ]

        # the value might have been put there by an extenstion of pytest (such as pytest-bdd), so don't overwrite it
        if "uniqueName" not in self.test_data:
            self.test_data["uniqueName"] = result.nodeid

        if "displayName" not in self.test_data:
            self.test_data["displayName"] = result.head_line.replace(
                "test_", ""
            ).replace("_", " ")

        self.test_data["result"] = (
            self.test_data["result"] if "result" in self.test_data else result.outcome
        )

        if "startTime" not in self.test_data:
            self.test_data["startTime"] = self.start_time

        if "endTime" not in self.test_data:
            self.test_data["endTime"] = datetime.fromtimestamp(
                result.stop, timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S.%f%z")

        self.test_data["tags"] = tags
        self.test_data["testCount"] = item.session.testscollected

        if "testLibrary" not in self.test_data:
            self.test_data["testLibrary"] = "Pytest"

        if "feature" not in self.test_data:
            self.test_data["feature"] = {
                "displayName": item.parent.name.replace(".py", ""),
                "description": None,
            }

        if "uniqueName" not in self.test_data["feature"]:
            self.test_data["feature"]["uniqueName"] = item.parent.nodeid

        self.test_data["externalReference"] = self.run_reference
        self.test_data["machineName"] = socket.gethostname()
        self.test_data["buildVersion"] = self.build_version
        self.test_data["buildRevision"] = self.build_revision
        self.test_data["branch"] = self.branch_name
        self.test_data["project"] = self.project_name
        self.test_data["testCaseRunId"] = str(uuid.uuid4())

        if "metadata" not in self.test_data:
            self.test_data["metadata"] = []

        with open(
            f"{self.TEST_TRACER_RESULTS_PATH}/{uuid.uuid4()}.json", "w"
        ) as outfile:
            outfile.write(json.dumps(self.test_data))
