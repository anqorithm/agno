import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from agno.tools.gitlab import GitlabTools


@pytest.fixture
def gitlab_api():
    requests = []
    reply = {
        "status": 200,
        "body": [
            {"old_path": "agent.py", "new_path": "agent.py", "diff": "@@ -1 +1 @@\n-old\n+new\n"},
            {"old_path": "large.py", "new_path": "large.py", "diff": "", "too_large": True, "collapsed": True},
        ],
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get("PRIVATE-TOKEN")))
            self.send_response(reply["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Next-Page", "3")
            self.end_headers()
            self.wfile.write(json.dumps(reply["body"]).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests, reply
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_diff_tool_is_opt_in():
    tools = GitlabTools()
    assert "get_merge_request_diffs" not in tools.functions
    assert "get_merge_request_diffs" not in tools.async_functions
    enabled = GitlabTools(enable_get_merge_request_diffs=True)
    assert "get_merge_request_diffs" in enabled.functions
    assert "get_merge_request_diffs" in enabled.async_functions


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("project", ["42", "group/subgroup/project"])
async def test_read_diffs_preserves_patches_and_omission_flags(gitlab_api, asynchronous, project):
    base_url, requests, reply = gitlab_api
    tools = GitlabTools(access_token="test-token", base_url=base_url)
    try:
        if asynchronous:
            result = await tools.aget_merge_request_diffs(project, 7, page=2, per_page=3)
        else:
            result = tools.get_merge_request_diffs(project, 7, page=2, per_page=3)
    finally:
        await tools.aclose()

    assert json.loads(result) == {
        "data": reply["body"],
        "meta": {"current_page": 2, "per_page": 3, "returned_items": 2},
    }
    encoded = project.replace("/", "%2F")
    assert requests == [(f"/api/v4/projects/{encoded}/merge_requests/7/diffs?page=2&per_page=3", "test-token")]


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(("requested", "bounded"), [(0, 1), (200, 100)])
async def test_diff_page_size_is_bounded_and_empty_page_is_preserved(gitlab_api, asynchronous, requested, bounded):
    base_url, requests, reply = gitlab_api
    reply["body"] = []
    tools = GitlabTools(base_url=base_url)
    try:
        if asynchronous:
            result = await tools.aget_merge_request_diffs("42", 7, per_page=requested)
        else:
            result = tools.get_merge_request_diffs("42", 7, per_page=requested)
    finally:
        await tools.aclose()

    assert json.loads(result) == {"data": [], "meta": {"current_page": 1, "per_page": bounded, "returned_items": 0}}
    assert requests == [(f"/api/v4/projects/42/merge_requests/7/diffs?page=1&per_page={bounded}", None)]


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("status", [401, 404, 500])
async def test_diff_api_errors_are_returned_as_errors(gitlab_api, asynchronous, status):
    base_url, requests, reply = gitlab_api
    reply.update(status=status, body={"message": "Diff request failed"})
    tools = GitlabTools(base_url=base_url)
    try:
        if asynchronous:
            result = await tools.aget_merge_request_diffs("42", 7)
        else:
            result = tools.get_merge_request_diffs("42", 7)
    finally:
        await tools.aclose()

    error = json.loads(result)["error"]
    assert str(status) in error
    assert "Diff request failed" in error
    assert len(requests) == 1
