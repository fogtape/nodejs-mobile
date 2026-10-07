#!/usr/bin/env python3
"""Release version selection, API failure handling and manual publish guards."""

import importlib.util
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('release_control', Path(__file__).with_name('release-control.py'))
CONTROL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTROL)


class ReleaseControl(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='node-mobile-release-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'mobile-src/src').mkdir(parents=True)
        (self.root / 'docs').mkdir()
        self.fixture()
        self.refs = set()
        self.exists = lambda kind, name: (kind, name) in self.refs

    def fixture(self, version='26.10.0-0'):
        parts = CONTROL.parse_version(version, mobile=True)
        (self.root / 'upstream-base.txt').write_text('# pinned upstream\nv' + CONTROL.version_text(parts[:3]) + '\n')
        (self.root / 'mobile-src/src/node_mobile_version.h').write_text('\n'.join(
            f'#define NODE_MOBILE_{field} {part}' for field, part in zip(CONTROL.FIELDS, parts)) + '\n')
        (self.root / 'docs/CHANGELOG.md').write_text(f'''<table>
<a href="#{version}">{version} (unreleased)</a><br/>
<a href="#26.1.0-0">26.1.0-0</a><br/>
</table>
<a id="{version}"></a>
## Unreleased, Version {version} (Current)

- Temporal and FFI.
  This source upgrade does not arm publication.
- Preserve the next release-note bullet.

<a id="26.1.0-0"></a>
## 2026-05-01, Version 26.1.0-0

- Previous release.
''')

    def plan(self, version='auto', line='recipe-v26', snapshot=''):
        return CONTROL.plan(self.root, line, version, self.exists, snapshot)

    def check(self, *, event='workflow_dispatch', ref='refs/heads/recipe-v26',
              operation='prerelease', version='26.10.0-0', snapshot=''):
        return CONTROL.check(self.root, event, ref, operation, version, self.exists, snapshot)

    def arm(self, version='26.10.0-0'):
        (self.root / 'release-ready.txt').write_text(version + '\n')

    def test_auto_and_explicit_upstream_choose_free_revision(self):
        self.refs.update({('tags', 'v26.10.0-0'), ('tags', 'nodejs-mobile-26.10.0-1'),
                          ('heads', 'release/v26.10.0-2')})
        for version in ['auto', '26.10.0', 'v26.10.0']:
            with self.subTest(version=version):
                result = self.plan(version)
                self.assertEqual(result['version'], '26.10.0-3')
                self.assertTrue(result['prerelease'])
                self.assertFalse(result['latest'])

    def test_choose_exact_unused_version(self):
        self.assertEqual(self.plan('v26.10.0-7')['version'], '26.10.0-7')

    def test_upstream_pr_snapshot_builds_but_cannot_arm_or_publish(self):
        (self.root / 'upstream-base.txt').write_text('7f68d75ee7963cd38ddc3783dd529f826bbde614\n')
        for event in ('push', 'pull_request', 'workflow_dispatch'):
            with self.subTest(event=event):
                result = self.check(event=event, operation='build', version='')
                self.assertEqual(result['release'], 'false')
        with self.assertRaisesRegex(CONTROL.ReleaseError, 'unreleased upstream PR'):
            self.plan()
        for operation in ('prerelease', 'prerelease-dryrun'):
            with self.subTest(operation=operation), self.assertRaisesRegex(
                    CONTROL.ReleaseError, 'unreleased upstream PR'):
                self.check(operation=operation)

    def test_plan_never_mutates_source(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.plan('26.10.0-0')
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_snapshot_requires_exact_manual_opt_in_and_reviewed_sha_marker(self):
        sha = '49072a0be4c7410982557aebf5b5c924fe7db597'
        (self.root / 'upstream-base.txt').write_text(sha + '\n')
        with patch.object(CONTROL, 'snapshot_version', return_value=(26, 10, 0)):
            for invalid in ('', sha[:10], '0' * 40, sha + ';echo bad'):
                with self.subTest(invalid=invalid), self.assertRaises(CONTROL.ReleaseError):
                    self.plan(snapshot=invalid)
            release_plan = self.plan('26.10.0-0', snapshot=sha)
            self.assertEqual(release_plan['upstream_snapshot'], sha)
            self.arm()
            with self.assertRaisesRegex(CONTROL.ReleaseError, 'reviewed Cut release PR'):
                self.check(snapshot=sha)
            CONTROL.prepare(self.root, release_plan)
            self.assertEqual((self.root / 'release-upstream-snapshot.txt').read_text(), sha + '\n')
            for operation in ('prerelease', 'prerelease-dryrun'):
                result = self.check(snapshot=sha, operation=operation)
                self.assertEqual(result['cold'], 'true')
                self.assertEqual(result['release'], 'true' if operation == 'prerelease' else 'false')
            (self.root / 'release-upstream-snapshot.txt').write_text('0' * 40 + '\n')
            with self.assertRaises(CONTROL.ReleaseError):
                self.check(snapshot=sha)

    def test_snapshot_version_is_verified_against_official_source(self):
        sha = '4' * 40
        header = b'#define NODE_MAJOR_VERSION 26\n#define NODE_MINOR_VERSION 11\n#define NODE_PATCH_VERSION 0\n'
        response = subprocess.CompletedProcess([], 0, base64.b64encode(header).decode() + '\n', '')
        with patch.object(CONTROL.subprocess, 'run', return_value=response) as run:
            self.assertEqual(CONTROL.snapshot_version(sha), (26, 11, 0))
            self.assertIn(f'repos/nodejs/node/contents/src/node_version.h?ref={sha}', run.call_args[0][0])
        for response in (subprocess.CompletedProcess([], 1, '', 'HTTP 403'),
                         subprocess.CompletedProcess([], 0, 'not base64', ''),
                         subprocess.CompletedProcess([], 0, base64.b64encode(b'no macros').decode(), '')):
            with self.subTest(response=response), patch.object(CONTROL.subprocess, 'run', return_value=response), \
                    self.assertRaises(CONTROL.ReleaseError):
                CONTROL.snapshot_version(sha)
        (self.root / 'upstream-base.txt').write_text(sha + '\n')
        with patch.object(CONTROL, 'snapshot_version', return_value=(26, 11, 0)):
            with self.assertRaisesRegex(CONTROL.ReleaseError, 'currently pins 26.11.0'):
                self.plan('26.10.0-0', snapshot=sha)
            self.arm()
            with self.assertRaisesRegex(CONTROL.ReleaseError, 'upstream 26.11.0'):
                self.check(snapshot=sha)

    def test_snapshot_input_cannot_change_normal_tag_releases_or_builds(self):
        with self.assertRaises(CONTROL.ReleaseError):
            self.plan(snapshot='4' * 40)
        with self.assertRaises(CONTROL.ReleaseError):
            self.check(operation='build', version='', snapshot='4' * 40)
        self.arm()
        with self.assertRaises(CONTROL.ReleaseError):
            self.check(snapshot='4' * 40)
        for event in ('push', 'pull_request'):
            self.assertEqual(self.check(event=event, snapshot='4' * 40)['release'], 'false')

    def test_official_release_preparation_clears_previous_snapshot_marker(self):
        (self.root / 'release-upstream-snapshot.txt').write_text('4' * 40 + '\n')
        CONTROL.prepare(self.root, self.plan())
        self.assertEqual((self.root / 'release-upstream-snapshot.txt').read_text(), '')

    def test_wrong_version_or_line_is_rejected(self):
        for line, version in [('recipe', '26.10.0'), ('recipe-v26', '26.1.0'),
                              ('dev', '26.10.0'), ('recipe-v26', '24.21.0-0')]:
            with self.subTest(line=line, version=version), self.assertRaises(CONTROL.ReleaseError):
                self.plan(version, line)

    def test_invalid_version_cannot_be_shell_or_path_input(self):
        for version in ['26.10', '26.10.0-01', '26.10.0-0;echo bad', '../26.10.0',
                        '026.10.0', '26.10.0-0\n', '', '26.10.0-rc.1']:
            with self.subTest(version=version), self.assertRaises(CONTROL.ReleaseError):
                self.plan(version)

    def test_existing_tags_or_release_branches_are_not_overwritten(self):
        for kind, name in [('tags', 'v26.10.0-0'), ('tags', 'nodejs-mobile-26.10.0-0'),
                           ('heads', 'release/v26.10.0-0')]:
            with self.subTest(kind=kind, name=name):
                self.refs = {(kind, name)}
                with self.assertRaises(CONTROL.ReleaseError):
                    self.plan('26.10.0-0')

    def test_preparation_preserves_existing_notes_without_duplicate_anchors(self):
        CONTROL.prepare(self.root, self.plan('26.10.0-0'))
        notes = (self.root / 'docs/CHANGELOG.md').read_text()
        self.assertEqual(notes.count('<a id="26.10.0-0">'), 1)
        self.assertEqual(notes.count('<a href="#26.10.0-0">'), 1)
        self.assertIn('Temporal and FFI.', notes)
        self.assertNotIn('TODO', notes)
        self.assertNotIn('does not arm publication', notes)
        self.assertIn('\n- Preserve the next release-note bullet.', notes)
        self.assertEqual((self.root / 'release-ready.txt').read_text(), '26.10.0-0\n')

    def test_new_revision_has_review_stub_and_updated_header(self):
        CONTROL.prepare(self.root, self.plan('26.10.0-2'))
        self.assertEqual(CONTROL.recorded_version(self.root), (26, 10, 0, 2))
        self.assertIn('TODO', (self.root / 'docs/CHANGELOG.md').read_text())

    def test_pr_and_push_never_publish_even_when_armed(self):
        self.arm()
        for event in ['push', 'pull_request', 'pull_request_target', 'schedule']:
            with self.subTest(event=event):
                self.assertEqual(self.check(event=event),
                                 dict(version='26.10.0-0', release='false', dryrun='false', cold='false'))

    def test_manual_build_does_not_need_arm_or_probe_tags(self):
        self.refs.add(('tags', 'v26.10.0-0'))
        answer = self.check(operation='build', version='', ref='refs/heads/dev')
        self.assertEqual(answer['release'], 'false')
        self.assertEqual(answer['cold'], 'false')

    def test_valid_prerelease_and_rehearsal_are_cold_and_distinct(self):
        self.arm()
        release = self.check()
        rehearsal = self.check(operation='prerelease-dryrun')
        self.assertEqual((release['release'], release['dryrun'], release['cold']), ('true', 'false', 'true'))
        self.assertEqual((rehearsal['release'], rehearsal['dryrun'], rehearsal['cold']), ('false', 'true', 'true'))

    def test_explicit_version_marker_and_maintained_branch_are_required(self):
        with self.assertRaises(CONTROL.ReleaseError):
            self.check()
        self.arm('26.1.0-0')
        with self.assertRaises(CONTROL.ReleaseError):
            self.check()
        self.arm()
        for request in [{'version': ''}, {'version': '26.10.0'}, {'version': '26.10.0-1'},
                        {'ref': 'refs/heads/dev'}, {'ref': 'refs/tags/v26.10.0-0'},
                        {'ref': 'refs/heads/recipe'}, {'operation': 'stable'},
                        {'operation': 'build', 'version': '26.10.0-0'}]:
            with self.subTest(request=request), self.assertRaises(CONTROL.ReleaseError):
                self.check(**request)

    def test_existing_tag_blocks_publication_and_dryrun(self):
        self.arm()
        for tag in ['v26.10.0-0', 'nodejs-mobile-26.10.0-0']:
            self.refs = {('tags', tag)}
            for operation in ['prerelease', 'prerelease-dryrun']:
                with self.subTest(tag=tag, operation=operation), self.assertRaises(CONTROL.ReleaseError):
                    self.check(operation=operation)

    def test_node24_and_node26_use_independent_lines(self):
        self.fixture('24.21.0-1')
        self.arm('24.21.0-1')
        self.assertEqual(self.plan('24.21.0-1', 'recipe')['version'], '24.21.0-1')
        self.assertEqual(self.check(ref='refs/heads/recipe', version='24.21.0-1')['release'], 'true')

    def test_only_404_means_missing_ref(self):
        responses = [
            (subprocess.CompletedProcess([], 0, '{}', ''), True),
            (subprocess.CompletedProcess([], 1, '', 'gh: Not Found (HTTP 404)'), False),
        ]
        for response, expected in responses:
            with patch.object(CONTROL.subprocess, 'run', return_value=response):
                self.assertEqual(CONTROL.ref_exists('owner/repo', 'tags', 'v26.10.0-0'), expected)
        for status in [403, 429, 500, 502]:
            response = subprocess.CompletedProcess([], 1, '', f'gh: API failed (HTTP {status})')
            with patch.object(CONTROL.subprocess, 'run', return_value=response), self.assertRaises(CONTROL.ReleaseError):
                CONTROL.ref_exists('owner/repo', 'tags', 'v26.10.0-0')

    def test_output_versions_are_normalized_and_action_booleans_are_strings(self):
        self.arm()
        output = self.root / 'outputs'
        with patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}):
            CONTROL.emit(self.check(version='v26.10.0-0'))
        self.assertIn('version=26.10.0-0\n', output.read_text())
        self.assertIn('release=true\n', output.read_text())


if __name__ == '__main__':
    unittest.main()
