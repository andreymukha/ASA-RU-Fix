import base64
import hashlib
import json
import unittest

from tools.client_release import ClientPublisher
from tools.github_publish import BOT, GitHubError, GitHubPublisher


HEAD = 'b' * 40


class MemoryGitHub:
    """Apply git tree overlays to actual bytes; merely checking base_tree is insufficient."""
    def __init__(self):
        self.head = HEAD
        self.files = {'stable.json': b'{"schema":1, "untouched":true}\n',
                      'automation.json': b'\xef\xbb\xbf {"schema":1}\r\n',
                      'client.json': b'{ "schema": 1, "version":"0.9.0" }\r\n',
                      'unknown.bin': b'\x00\xff\x01'}
        self.blobs = {}
        self.trees = {'initial-tree': dict(self.files)}
        self.commits = {HEAD: 'initial-tree'}
        self.calls = []
        self.race = False

    def api(self, route, *, method='GET', body=None, binary=False):
        self.calls.append((route, method, body))
        if route == 'git/ref/heads/channel' and method == 'GET':
            return {'object': {'sha': self.head}}
        if route.startswith('contents/'):
            filename = route.removeprefix('contents/').split('?ref=')[0]
            raw = self.trees[self.commits[self.head]][filename]
            return {'encoding': 'base64', 'content': base64.b64encode(raw).decode()}
        if route.startswith('git/commits/') and method == 'GET':
            return {'tree': {'sha': self.commits[route.rsplit('/', 1)[1]]}}
        if route == 'git/blobs':
            raw = base64.b64decode(body['content'])
            sha = hashlib.sha256(raw).hexdigest()
            self.blobs[sha] = raw
            return {'sha': sha}
        if route == 'git/trees':
            files = dict(self.trees[body['base_tree']]) if 'base_tree' in body else {}
            files.update({entry['path']: self.blobs[entry['sha']] for entry in body['tree']})
            sha = f'tree-{len(self.trees)}'
            self.trees[sha] = files
            return {'sha': sha}
        if route == 'git/commits':
            sha = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:40]
            self.commits[sha] = body['tree']
            if self.race:
                self.head = 'c' * 40
            return {'sha': sha}
        if route == 'git/refs/heads/channel' and method == 'PATCH':
            assert body['force'] is False
            self.head = body['sha']
            return {'object': {'sha': self.head}}
        raise AssertionError((route, method, body))

    def current(self):
        return self.trees[self.commits[self.head]]


class ChannelPreservationTests(unittest.TestCase):
    def setUp(self):
        self.fake = MemoryGitHub()

    def publisher(self, cls):
        publisher = cls('owner/repo')
        publisher._api = self.fake.api
        return publisher

    def test_server_state_update_preserves_client_and_unknown_file_byte_for_byte(self):
        original = dict(self.fake.files)
        self.publisher(GitHubPublisher).write_channel({'schema': 1, 'version': '1.0.1'},
                                                     {'schema': 1, 'changed': True}, HEAD, 'server')
        self.assertEqual(self.fake.current()['client.json'], original['client.json'])
        self.assertEqual(self.fake.current()['unknown.bin'], original['unknown.bin'])
        self.assertNotEqual(self.fake.current()['stable.json'], original['stable.json'])

    def test_client_update_preserves_server_files_and_unknown_bytes(self):
        original = dict(self.fake.files)
        record = {'schema': 1, 'version': '1.0.0'}
        sha = self.publisher(ClientPublisher).write_client_channel(record, HEAD)
        for name in ('stable.json', 'automation.json', 'unknown.bin'):
            self.assertEqual(self.fake.current()[name], original[name])
        self.assertEqual(json.loads(self.fake.current()['client.json']), record)
        commit = next(body for route, _, body in self.fake.calls if route == 'git/commits')
        self.assertEqual(commit['parents'], [HEAD])
        self.assertEqual(commit['author'], BOT)
        self.assertEqual(commit['committer'], BOT)
        self.assertEqual(self.fake.head, sha)

    def test_client_refuses_stale_channel_and_race_after_commit(self):
        publisher = self.publisher(ClientPublisher)
        with self.assertRaisesRegex(GitHubError, 'changed'):
            publisher.write_client_channel({'schema': 1}, 'a' * 40)
        self.assertEqual(len(self.fake.calls), 1)
        self.fake.calls.clear()
        self.fake.race = True
        with self.assertRaisesRegex(GitHubError, 'changed'):
            publisher.write_client_channel({'schema': 1}, HEAD)
        self.assertFalse(any(method == 'PATCH' for _, method, _ in self.fake.calls))

    def test_identical_client_manifest_retry_does_not_create_a_commit(self):
        publisher = self.publisher(ClientPublisher)
        record = {'schema': 1, 'version': '1.0.0'}
        first = publisher.write_client_channel(record, HEAD)
        self.fake.calls.clear()
        self.assertEqual(publisher.write_client_channel(record, first), first)
        self.assertFalse(any(method != 'GET' for _, method, _ in self.fake.calls))


if __name__ == '__main__':
    unittest.main()
