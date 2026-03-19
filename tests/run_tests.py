# Copyright 2026 mp3monster.org
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import sys

import pytest


SUITES = {
    "provider-error-responses": ["provider/tests/test_error_responses.py"],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        choices=sorted(SUITES.keys()),
        required=True,
        help="named test suite to execute",
    )
    args = parser.parse_args()
    return pytest.main(SUITES[args.suite])


if __name__ == "__main__":
    raise SystemExit(main())
