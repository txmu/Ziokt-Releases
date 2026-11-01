#!/usr/bin/env python3
"""Compare independently authenticated remote checkpoints under an explicit trust policy.

Matching trusted sources is a trust assumption, not proof of historical validity.
Supports optional automatic import into a persistent store and materialization
into staging node databases without independent history replay.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ziokt.checkpoint_store import CheckpointStore, MAX_TOTAL
from ziokt.checkpoint_restore import materialize_local


def verify_peer_checkpoints(policy_dict, sources, quorum=2, import_to=None, materialize_to=None):
    if quorum < 2 or len(set(sources)) < quorum:
        raise ValueError('at least quorum distinct sources are required')
    expected, signers = policy_dict['expected'], {key: set(value) for key, value in policy_dict['signers'].items()}
    if set(expected) != {'primary', 'dna'} or set(signers) != set(expected):
        raise ValueError('policy must pin both chain domains and trusted signer sets')
    os.umask(0o077)
    groups = {}
    with tempfile.TemporaryDirectory(prefix='ziokt-peer-checkpoints-') as tmp:
        for index, url in enumerate(sources):
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme not in {'https', 'file'}:
                raise ValueError('sources must be HTTPS or file URLs')
            if parsed.scheme == 'https' and (not parsed.hostname or parsed.username or parsed.password):
                raise ValueError('sources must be credential-free HTTPS URLs')
            destination = Path(tmp) / (str(index) + '.zip')
            if parsed.scheme == 'file':
                source_path = Path(parsed.path)
                if not source_path.is_file():
                    raise ValueError(f'local file source does not exist: {source_path}')
                destination.write_bytes(source_path.read_bytes())
            else:
                with urllib.request.urlopen(url, timeout=30) as response, destination.open('xb') as out:
                    if urllib.parse.urlsplit(response.geturl()).scheme != 'https':
                        raise ValueError('HTTPS downgrade rejected')
                    total = 0
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_TOTAL + 2 * 1024 * 1024:
                            raise ValueError('checkpoint bundle too large')
                        out.write(chunk)
            store = CheckpointStore(Path(tmp) / ('store-' + str(index)), expected, signers)
            value = store.import_bundle(destination, allow_bootstrap=True)
            manifest = value.manifest
            if manifest['scope'] != 'explicit-signer-bootstrap':
                raise ValueError('remote source must publish an explicit bootstrap checkpoint')
            identities = tuple(manifest['signatures'][role]['identity'] for role in ('primary', 'dna'))
            groups.setdefault(manifest['pair_commitment'], []).append((identities, manifest, destination))

        for commitment, entries in groups.items():
            chosen = []
            for identities, manifest, bundle_path in entries:
                if all(identities[0] != old[0][0] and identities[1] != old[0][1] for old in chosen):
                    chosen.append((identities, manifest, bundle_path))
            if len(chosen) >= quorum:
                chains = chosen[0][1]['chains']
                winning_bundle = chosen[0][2]
                imported_store = None
                materialized_result = None

                if import_to:
                    dest_store = Path(import_to).resolve()
                    imported_store = CheckpointStore(dest_store, expected, signers)
                    imported_store.import_bundle(winning_bundle, allow_bootstrap=True)

                if materialize_to:
                    if imported_store is None:
                        target_store = CheckpointStore(Path(tmp) / ('target-store-' + commitment[:12]), expected, signers)
                        target_store.import_bundle(winning_bundle, allow_bootstrap=True)
                    else:
                        target_store = imported_store
                    dest_target = Path(materialize_to).resolve()
                    materialized_result = materialize_local(target_store, dest_target, allow_bootstrap=True)

                return {
                    'schema': 'ziokt.peer-checkpoint-verification.v1',
                    'pair_commitment': commitment,
                    'snapshot_hash': chosen[0][1]['snapshot_hash'],
                    'independent_signers': len(chosen),
                    'chains': {role: {key: chains[role][key] for key in ('network_id', 'height', 'block_hash', 'state_root')} for role in chains},
                    'verification_level': 'explicitly trusted sources; historical validity not independently proven',
                    'imported_to': str(Path(import_to).resolve()) if import_to else None,
                    'materialized_to': str(Path(materialize_to).resolve()) if materialize_to else None,
                    'installed': bool(import_to or materialize_to),
                    'independent_history_replay_proved': False
                }
        raise ValueError('no matching checkpoint from the required number of distinct trusted signers')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, required=True, help='JSON containing expected chain domains and trusted signer identities')
    parser.add_argument('--source', action='append', required=True, help='HTTPS checkpoint bundle URL; repeat for independent nodes')
    parser.add_argument('--quorum', type=int, default=2)
    parser.add_argument('--import-to', type=Path, help='CheckpointStore root directory to import the verified bundle into')
    parser.add_argument('--materialize-to', type=Path, help='Target directory to materialize verified native SQLite databases')
    args = parser.parse_args()

    policy = json.loads(args.policy.read_text())
    result = verify_peer_checkpoints(
        policy,
        args.source,
        quorum=args.quorum,
        import_to=args.import_to,
        materialize_to=args.materialize_to
    )
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
