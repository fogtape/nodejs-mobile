#!/usr/bin/env python3
"""Verify immutable upstream clones and cache transport without public network."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest

CLONE = Path(__file__).with_name('clone-upstream.sh').resolve()


class UpstreamClone(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='node-mobile-upstream-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'upstream'
        self.repo.mkdir()
        self.git(self.repo, 'init', '-q')
        self.git(self.repo, 'config', 'user.name', 'fixture')
        self.git(self.repo, 'config', 'user.email', 'fixture@invalid')
        (self.repo / 'version').write_text('released\n')
        self.git(self.repo, 'add', 'version')
        self.git(self.repo, 'commit', '-qm', 'release')
        self.git(self.repo, 'tag', '-a', 'v26.10.0', '-m', 'release')
        self.released = self.git(self.repo, 'rev-parse', 'HEAD')
        (self.repo / 'version').write_text('proposal\n')
        self.git(self.repo, 'commit', '-qam', 'proposal')
        self.proposal = self.git(self.repo, 'rev-parse', 'HEAD')

    def git(self, repo, *args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()

    def clone(self, repo, ref, dest, *, check=True):
        return subprocess.run([str(CLONE), repo.as_uri(), ref, str(dest)],
                              text=True, capture_output=True, check=check)

    def test_sha_clone_and_cached_reclone_preserve_exact_commit_without_tags(self):
        cache, output = self.root / 'cache', self.root / 'output'
        self.clone(self.repo, self.proposal, cache)
        self.clone(cache, self.proposal, output)
        self.assertEqual(self.git(output, 'rev-parse', 'HEAD'), self.proposal)
        self.assertEqual(self.git(output, 'rev-parse', 'refs/nodejs-mobile/upstream-base'),
                         self.proposal)
        self.assertEqual((output / 'version').read_text(), 'proposal\n')
        self.assertEqual(self.git(output, 'tag', '-l'), '')
        self.assertEqual(self.git(output, 'rev-parse', '--is-shallow-repository'), 'true')

    def test_annotated_release_tag_still_clones(self):
        output = self.root / 'output'
        self.clone(self.repo, 'v26.10.0', output)
        self.assertEqual(self.git(output, 'rev-parse', 'HEAD'), self.released)
        self.assertEqual(self.git(output, 'rev-parse', 'v26.10.0^{commit}'), self.released)

    def test_existing_destination_is_preserved(self):
        output = self.root / 'output'
        output.mkdir()
        (output / 'keep').write_text('existing work\n')
        self.assertNotEqual(self.clone(self.repo, self.proposal, output, check=False).returncode, 0)
        self.assertEqual((output / 'keep').read_text(), 'existing work\n')

    def test_missing_sha_fails_without_checked_out_source(self):
        output = self.root / 'output'
        self.assertNotEqual(self.clone(self.repo, '0' * 40, output, check=False).returncode, 0)
        self.assertFalse((output / 'version').exists())

    def test_ci_upstream_check_verifies_snapshot_sha_and_rejects_mismatch(self):
        workflow = CLONE.parent.parent / '.github/workflows/build.yml'
        match = re.search(r'      - name: Check the pinned upstream base is on this fork\n'
                          r'.*?        run: \|\n((?: {10}[^\n]*\n|\n)+)',
                          workflow.read_text(), re.S)
        self.assertIsNotNone(match)
        script = '\n'.join(line[10:] if line else '' for line in match[1].splitlines())
        (self.root / 'upstream-base.txt').write_text(self.proposal + '\n')
        tools = self.root / 'tools'
        tools.mkdir()
        gh = tools / 'gh'
        gh.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$API_RECORD"\n'
                      'printf "%s\\n" "$API_SHA"\n')
        gh.chmod(0o755)
        record = self.root / 'api-record'
        env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                   API_RECORD=str(record), API_SHA=self.proposal)
        result = subprocess.run(['bash', '-c', script], cwd=self.root,
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Verified upstream PR snapshot', result.stdout)
        self.assertEqual(record.read_text().strip(),
                         f'api repos/nodejs/node/commits/{self.proposal} --jq .sha')
        result = subprocess.run(['bash', '-c', script], cwd=self.root,
                                env=dict(env, API_SHA='0' * 40), capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('snapshot SHA mismatch', result.stdout)


if __name__ == '__main__':
    unittest.main()
