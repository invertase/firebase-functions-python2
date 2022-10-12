# Copyright 2022 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
Module used to serve Firebase functions locally and remotely.
"""
# pylint: disable=protected-access
import os
import inspect
import enum
import yaml
import importlib
from os import kill, getpid
from signal import SIGTERM

from flask import Flask
from flask import Response

from firebase_functions.private import manifest as _manifest
from firebase_functions.private import util as _util


def get_functions():
    spec = importlib.util.spec_from_file_location("main", "main.py")
    if spec is not None and spec.loader is not None:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        raise Exception(
            "Firebase Functions for Python could not find the main.py file in your project."
        )
    functions = inspect.getmembers(module, inspect.isfunction)
    firebase_functions = {}
    for entry in functions:
        if hasattr(entry[1], "__firebase_endpoint__"):
            name = entry[1].__firebase_endpoint__.entryPoint
            firebase_functions[name] = entry[1]
    return firebase_functions


def to_spec(data: dict) -> dict:

    def convert_value(obj):
        if isinstance(obj, enum.Enum):
            return obj.value
        if isinstance(obj, dict):
            return to_spec(obj)
        if isinstance(obj, list):
            return list(map(convert_value, obj))
        return obj

    without_nones = dict(
        (k, convert_value(v)) for k, v in data.items() if v is not None)
    return without_nones


def functions_as_yaml(functions: dict) -> str:
    endpoints: dict[str, _manifest.ManifestEndpoint] = {}
    for name, function in functions.items():
        endpoint = function.__firebase_endpoint__
        # v2 function name(s) can only contain lower case letters, numbers, hyphens
        endpoints[name.replace("_", "-").lower()] = endpoint

    manifest_stack = _manifest.ManifestStack(endpoints=endpoints)
    manifest_spec = _manifest.manifest_to_spec_dict(manifest_stack)
    manifest_spec_with_sentinels = to_spec(manifest_spec)

    def represent_sentinel(self, _):
        # TODO distinguishing between RESET_VALUE or DEFAULT_VALUE
        # TODO can be done here
        return self.represent_scalar("tag:yaml.org,2002:null", "null")

    yaml.add_representer(_util.Sentinel, represent_sentinel)

    return yaml.dump(manifest_spec_with_sentinels)


def get_functions_yaml() -> Response:
    functions = get_functions()
    functions_yaml = functions_as_yaml(functions)
    return Response(functions_yaml, mimetype="text/yaml")


def quitquitquit():

    def quit_after_close():
        kill(getpid(), SIGTERM)

    response = Response("OK", status=200)
    response.call_on_close(quit_after_close)
    return response


def serve_admin() -> Flask:
    app = Flask(__name__)
    app.add_url_rule(
        "/__/functions.yaml",
        endpoint="functions.yaml",
        view_func=get_functions_yaml,
    )

    app.add_url_rule(
        "/__/quitquitquit",
        endpoint="quitquitquit",
        view_func=quitquitquit,
    )

    return app


def main():
    if os.environ["ADMIN_PORT"] is not None:
        serve_admin().run(port=int(os.environ["ADMIN_PORT"]), debug=False)


if __name__ == "__main__":
    main()
