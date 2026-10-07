#!/usr/bin/env python3
"""Plan reviewed release PRs and validate explicit manual prerelease requests."""

import argparse
import base64
import binascii
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys

LINES = {'recipe': 24, 'recipe-v26': 26}
NUMBER = r'(?:0|[1-9][0-9]*)'
UPSTREAM_VERSION = re.compile(rf'v?({NUMBER})\.({NUMBER})\.({NUMBER})\Z')
MOBILE_VERSION = re.compile(rf'v?({NUMBER})\.({NUMBER})\.({NUMBER})-({NUMBER})\Z')
FIELDS = ('MAJOR_VERSION', 'MINOR_VERSION', 'PATCH_VERSION', 'REVISION')


class ReleaseError(Exception):
    pass


def parse_version(value, mobile=False):
    match = (MOBILE_VERSION if mobile else UPSTREAM_VERSION).fullmatch(value)
    if not match:
        raise ReleaseError(f'Invalid version {value!r}; expected ' +
                           ('X.Y.Z-R (for example 26.10.0-0)' if mobile else 'X.Y.Z'))
    return tuple(int(part) for part in match.groups())


def version_text(parts):
    return '.'.join(str(part) for part in parts[:3]) + (
        f'-{parts[3]}' if len(parts) == 4 else '')


def snapshot_version(sha):
    process = subprocess.run(
        ['gh', 'api', f'repos/nodejs/node/contents/src/node_version.h?ref={sha}',
         '--jq', '.content'], capture_output=True, text=True)
    if process.returncode:
        raise ReleaseError('Cannot verify the snapshot version on official nodejs/node. Retry later.')
    try:
        source = base64.b64decode(''.join(process.stdout.split()), validate=True).decode('ascii')
    except (ValueError, binascii.Error, UnicodeError) as error:
        raise ReleaseError('Official snapshot version header is invalid') from error
    parts = []
    for field in ('MAJOR', 'MINOR', 'PATCH'):
        matches = re.findall(rf'^#define NODE_{field}_VERSION\s+([0-9]+)\s*$', source, re.M)
        if len(matches) != 1:
            raise ReleaseError(f'Expected one NODE_{field}_VERSION in the official snapshot')
        parts.append(int(matches[0]))
    return tuple(parts)


def upstream(root, snapshot=''):
    lines = [line.strip() for line in (root / 'upstream-base.txt').read_text().splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    if len(lines) != 1:
        raise ReleaseError('upstream-base.txt must pin exactly one upstream ref')
    if re.fullmatch(r'[0-9a-f]{40}', lines[0]):
        if not snapshot:
            raise ReleaseError('This source pins an unreleased upstream PR commit. '
                               'Pin an official release tag, or explicitly provide upstream_snapshot '
                               'with this exact SHA to prepare/publish an upstream snapshot prerelease.')
        if snapshot != lines[0]:
            raise ReleaseError('upstream_snapshot must exactly match the full SHA in upstream-base.txt')
        return snapshot_version(snapshot)
    if snapshot:
        raise ReleaseError('upstream_snapshot is only valid for a SHA-pinned upstream proposal')
    return parse_version(lines[0])


def recorded_version(root):
    source = (root / 'mobile-src/src/node_mobile_version.h').read_text()
    parts = []
    for field in FIELDS:
        matches = re.findall(rf'^#define NODE_MOBILE_{field}\s+([0-9]+)\s*$', source, re.M)
        if len(matches) != 1:
            raise ReleaseError(f'Expected one NODE_MOBILE_{field} in version header')
        parts.append(int(matches[0]))
    return tuple(parts)


def ref_exists(repository, kind, name):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ReleaseError('GITHUB_REPOSITORY must identify owner/repository')
    process = subprocess.run(['gh', 'api', f'repos/{repository}/git/ref/{kind}/{name}'],
                             capture_output=True, text=True)
    if process.returncode == 0:
        return True
    if re.search(r'\bHTTP 404\b', process.stderr + process.stdout):
        return False
    raise ReleaseError(f'Cannot check {kind}/{name}; GitHub API did not return a 404. Retry later.')


def require_line(line, base):
    if line not in LINES:
        raise ReleaseError('Select maintained release line recipe or recipe-v26')
    if base[0] != LINES[line]:
        raise ReleaseError(f'{line} is the Node {LINES[line]} line, but its source pins Node {base[0]}')


def plan(root, line, requested, exists, snapshot=''):
    base = upstream(root, snapshot)
    require_line(line, base)
    if requested == 'auto':
        selected, revision = base, None
    elif MOBILE_VERSION.fullmatch(requested):
        parts = parse_version(requested, mobile=True)
        selected, revision = parts[:3], parts[3]
    else:
        selected, revision = parse_version(requested), None
    if selected != base:
        raise ReleaseError(f'{line} currently pins {version_text(base)}, not {version_text(selected)}. '
                           'Merge the upstream upgrade into that line before preparing this version.')

    def taken(candidate):
        return (exists('tags', f'v{candidate}') or
                exists('tags', f'nodejs-mobile-{candidate}') or
                exists('heads', f'release/v{candidate}'))

    if revision is None:
        revision = 0
        while taken(version_text((*base, revision))):
            revision += 1
    version = version_text((*base, revision))
    if taken(version):
        raise ReleaseError(f'{version} already has a tag or release PR branch; choose another '
                           'revision or review the existing release PR. Nothing will be overwritten.')
    return {'line': line, 'upstream': 'v' + version_text(base), 'version': version,
            'tag': 'v' + version, 'release_branch': 'release/v' + version,
            'prerelease': True, 'latest': False, 'upstream_snapshot': snapshot}


def prepare(root, release_plan):
    version = release_plan['version']
    snapshot = release_plan.get('upstream_snapshot', '')
    parts = parse_version(version, mobile=True)
    if parts[:3] != upstream(root, snapshot):
        raise ReleaseError('The release plan does not match the checked-out source')
    header = root / 'mobile-src/src/node_mobile_version.h'
    source = header.read_text()
    for field, value in zip(FIELDS, parts):
        source, count = re.subn(rf'(^#define NODE_MOBILE_{field}\s+)[0-9]+(?=\s*$)',
                                lambda match: match[1] + str(value), source, flags=re.M)
        if count != 1:
            raise ReleaseError(f'Expected one NODE_MOBILE_{field} in version header')

    changelog = root / 'docs/CHANGELOG.md'
    notes = changelog.read_text()
    section = re.compile(r'^<a id="' + re.escape(version) +
                         r'"></a>\n(.*?)(?=^<a id="|\Z)', re.M | re.S)
    existing = section.search(notes)
    body = '- _TODO: summarize changes before publishing._\n\n'
    if existing:
        content = existing[1]
        heading, _, original = content.partition('\n')
        if not heading.startswith('## ') or f'Version {version}' not in heading:
            raise ReleaseError('Existing CHANGELOG entry has an unexpected heading')
        body = original.lstrip('\n')
        body = re.sub(r'^[ \t]*This source upgrade does not arm publication\.\n',
                      '', body, flags=re.M)
        if not body.strip():
            body = '- _TODO: summarize changes before publishing._\n\n'
        notes = section.sub('', notes)
    notes = re.sub(r'^<a href="#' + re.escape(version) + r'">[^<]*</a><br/>\n',
                   '', notes, flags=re.M)
    anchor = re.search(r'^<a id="', notes, re.M)
    toc = re.search(r'^<a href="#', notes, re.M)
    if not anchor or not toc:
        raise ReleaseError('CHANGELOG must contain version anchors and a table of contents')
    notes = re.sub(r'^(## .+, Version .+) \(Current\)$', r'\1', notes, flags=re.M)
    anchor = re.search(r'^<a id="', notes, re.M)
    new_section = (f'<a id="{version}"></a>\n## {datetime.date.today().isoformat()}, '
                   f'Version {version} (Current)\n\n{body.rstrip()}\n\n')
    notes = notes[:anchor.start()] + new_section + notes[anchor.start():]
    toc = re.search(r'^<a href="#', notes, re.M)
    notes = notes[:toc.start()] + f'<a href="#{version}">{version}</a><br/>\n' + notes[toc.start():]
    header.write_text(source)
    changelog.write_text(notes)
    (root / 'release-ready.txt').write_text(version + '\n')
    (root / 'release-upstream-snapshot.txt').write_text(snapshot + '\n' if snapshot else '')


def check(root, event, ref, operation, requested, exists, snapshot=''):
    version = version_text(recorded_version(root))
    answer = dict(version=version, release='false', dryrun='false', cold='false')
    # PR/push builds never publish, regardless of a marker or commit message.
    if event != 'workflow_dispatch':
        return answer
    if operation not in ('build', 'prerelease-dryrun', 'prerelease'):
        raise ReleaseError('Unknown operation; choose build, prerelease-dryrun or prerelease')
    if operation == 'build':
        if requested or snapshot:
            raise ReleaseError('The version and upstream_snapshot inputs are for prerelease/dryrun only; '
                               'clear them for a build')
        return answer
    line = ref.removeprefix('refs/heads/')
    if ref != 'refs/heads/' + line:
        raise ReleaseError('Prereleases must run on a maintained branch, not a tag')
    base = upstream(root, snapshot)
    require_line(line, base)
    selected = version_text(parse_version(requested, mobile=True))
    if selected != version or parse_version(version, mobile=True)[:3] != base:
        raise ReleaseError(f'Requested {selected}, but this source records {version} on '
                           f'upstream {version_text(base)}. Use Cut release to prepare the desired version.')
    marker = root / 'release-ready.txt'
    if not marker.is_file() or marker.read_text().strip() != version:
        raise ReleaseError(f'{version} is not armed: merge its reviewed Cut release PR first')
    if snapshot:
        snapshot_marker = root / 'release-upstream-snapshot.txt'
        if not snapshot_marker.is_file() or snapshot_marker.read_text().strip() != snapshot:
            raise ReleaseError('The reviewed Cut release PR must arm this exact upstream snapshot SHA')
    for tag in ('v' + version, 'nodejs-mobile-' + version):
        if exists('tags', tag):
            raise ReleaseError(f'Tag {tag} already exists; inspect/resume its original publish '
                               'run instead of overwriting a release')
    answer.update(cold='true', release='true' if operation == 'prerelease' else 'false',
                  dryrun='true' if operation == 'prerelease-dryrun' else 'false')
    return answer


def emit(values):
    for key, value in values.items():
        print(f'{key}={value}')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            for key, value in values.items():
                output.write(f'{key}={str(value).lower() if isinstance(value, bool) else value}\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    planner = sub.add_parser('plan')
    planner.add_argument('--root', type=Path, default=Path('.'))
    planner.add_argument('--line', required=True, choices=LINES)
    planner.add_argument('--version', default='auto')
    planner.add_argument('--out', type=Path, required=True)
    planner.add_argument('--upstream-snapshot', default='')
    preparer = sub.add_parser('prepare')
    preparer.add_argument('--root', type=Path, default=Path('.'))
    preparer.add_argument('--plan', type=Path, required=True)
    checker = sub.add_parser('check')
    checker.add_argument('--root', type=Path, default=Path('.'))
    checker.add_argument('--event', default=os.environ.get('GITHUB_EVENT_NAME', ''))
    checker.add_argument('--ref', default=os.environ.get('GITHUB_REF', ''))
    checker.add_argument('--operation', default=os.environ.get('RELEASE_OPERATION', 'build'))
    checker.add_argument('--version', default=os.environ.get('RELEASE_VERSION', ''))
    checker.add_argument('--upstream-snapshot', default=os.environ.get('UPSTREAM_SNAPSHOT', ''))
    args = parser.parse_args()
    exists = lambda kind, name: ref_exists(os.environ.get('GITHUB_REPOSITORY', ''), kind, name)
    try:
        if args.command == 'plan':
            result = plan(args.root, args.line, args.version, exists, args.upstream_snapshot)
            args.out.write_text(json.dumps(result, indent=2) + '\n')
            emit(result)
        elif args.command == 'prepare':
            prepare(args.root, json.loads(args.plan.read_text()))
        else:
            emit(check(args.root, args.event, args.ref, args.operation, args.version, exists,
                       args.upstream_snapshot))
    except (ReleaseError, FileNotFoundError) as error:
        print(f'::error::{error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
