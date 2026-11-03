import asyncio
import json
import subprocess
import types
from agno.tools.gitlab import GitlabTools

source = subprocess.check_output(['git', 'show', 'upstream/main:libs/agno/agno/tools/gitlab.py'], text=True)
baseline = types.ModuleType('gitlab_before')
exec(compile(source, 'gitlab_before.py', 'exec'), baseline.__dict__)
before = baseline.GitlabTools()
print('BEFORE, upstream main')
print('Merge request metadata tool registered:', 'get_merge_request' in before.functions)
print('Merge request diffs tool registered:', 'get_merge_request_diffs' in before.functions)

async def main():
    tools = GitlabTools(enable_get_merge_request_diffs=True, timeout=20)
    try:
        sync_fn = tools.functions['get_merge_request_diffs'].entrypoint
        async_fn = tools.async_functions['get_merge_request_diffs'].entrypoint
        sync = json.loads(sync_fn('gitlab-org/cli', 4300, page=1, per_page=1))
        asynchronous = json.loads(await async_fn('gitlab-org/cli', 4300, page=1, per_page=1))
        assert sync == asynchronous
        assert 'error' not in sync and sync['data'][0]['diff']
        print('\nAFTER, registered agent tool calls against public GitLab')
        print('Project: gitlab-org/cli, merge request: !4300')
        print('Sync and async results match:', sync == asynchronous)
        print('Page metadata:', json.dumps(sync['meta']))
        print('Changed file:', sync['data'][0]['new_path'])
        print('Patch characters retrieved:', len(sync['data'][0]['diff']))
        print('Requests were read-only, no model calls or API keys used')
    finally:
        await tools.aclose()

asyncio.run(main())
