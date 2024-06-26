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
        self.test_data = {}
        log_level = logging.DEBUG if config.option.verbose > 1 else logging.INFO
        logging.basicConfig(level=log_level)
        self.logger = logging.getLogger(self.name)
        self.__reset_results_folder()

    # hooks

    def pytest_sessionfinish(self, session):
        self.__zip_results()

        if session.config.getoption("--test-tracer-upload-results") == "True":
            token = session.config.getoption("--test-tracer-upload-token")

            self.__upload_results(token)
            self.__process_results(token)
        else:
            self.logger.debug(
                "Not uploading results as the --test-tracer-upload-results flag is False"
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

    def __reset_results_folder(self):
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

    def __upload_results(self, token):
        self.logger.info("Uploading results to Test Tracer...")
        self.__make_request(
            token,
            f"{self.TEST_TRACER_BASE_URL}/api/test-data/upload",
            {"file": open(f"{self.TEST_TRACER_RESULTS_PATH}/results.zip", "rb")},
        )

    def __process_results(self, token):
        self.logger.info("Processing results on Test Tracer...")
        self.__make_request(
            token, f"{self.TEST_TRACER_BASE_URL}/api/test-data/process", None
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
            verify=False,
        )

        if response.status_code == 401:
            self.logger.fatal(
                "Failed to authenticate with Test Tracer.  Ensure that your API Token is valid"
            )
        elif response.status_code == 403:
            self.logger.fatal(
                "Your API Token does not have permission to upload results"
            )

    def save_test_report(self, item: pytest.Item, call, outcome):
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

        self.test_data["externalReference"] = item.config.getoption(
            "--test-tracer-run-reference"
        )
        self.test_data["machineName"] = socket.gethostname()
        self.test_data["buildVersion"] = item.config.getoption("--build-version")
        self.test_data["buildRevision"] = item.config.getoption("--build-revision")
        self.test_data["branch"] = item.config.getoption("--branch-name")
        self.test_data["project"] = item.config.getoption("--test-tracer-project-name")
        self.test_data["testCaseRunId"] = str(uuid.uuid4())

        if "metadata" not in self.test_data:
            self.test_data["metadata"] = []

        with open(
            f"{self.TEST_TRACER_RESULTS_PATH}/{uuid.uuid4()}.json", "w"
        ) as outfile:
            outfile.write(json.dumps(self.test_data))
