#!/usr/bin/env python3
"""Publish and sign a dual-chain bootstrap checkpoint bundle from a running node.

Exports an explicit-signer-bootstrap bundle without private consumer state.
Historical validity is not implied; this produces source-authenticated state.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ziokt.checkpoint_capture import capture_pair


def build_config_from_node_root(node_root):
    node_root = Path(node_root).resolve()
    corium_root = node_root / 'corium'
    dna_root = node_root / 'dna-sidechain'
    if not corium_root.is_dir() or not dna_root.is_dir():
        if (node_root / 'primary').is_dir() and (node_root / 'dna').is_dir():
            corium_root = node_root / 'primary'
            dna_root = node_root / 'dna'
        else:
            raise ValueError(f'Cannot find dual-chain roots in {node_root}')

    candidates = [
        node_root / 'bin/corix_v108.sh',
        node_root / 'native/corix_v108.sh',
        Path('/home/admin/.local/share/ziokt-production/bin/corix_v108.sh'),
        Path('/home/admin/Corium/corix_v108.sh'),
    ]
    native_source = next((p for p in candidates if p.is_file()), None)
    if not native_source:
        raise ValueError('Cannot locate native source corix_v108.sh')

    corium_net_dir = corium_root / 'etc/corix/networks'
    dna_net_dir = dna_root / 'etc/corix/networks'
    corium_net = 'ziokt-main'
    dna_net = 'ziokt-dna-side-20261024'
    if corium_net_dir.is_dir():
        nets = [p.name for p in corium_net_dir.iterdir() if p.is_dir() and (p / 'identity.key').is_file()]
        if nets:
            corium_net = nets[0]
    if dna_net_dir.is_dir():
        nets = [p.name for p in dna_net_dir.iterdir() if p.is_dir() and (p / 'identity.key').is_file()]
        if nets:
            dna_net = nets[0]

    sha256 = hashlib.sha256(native_source.read_bytes()).hexdigest()
    return {
        'schema': 'ziokt.local-checkpoint-capture.v1',
        'scope': 'explicit-signer-bootstrap',
        'native_source': str(native_source),
        'native_sha256': sha256,
        'chains': {
            'primary': {
                'root': str(corium_root),
                'network_id': corium_net,
                'consumers': []
            },
            'dna': {
                'root': str(dna_root),
                'network_id': dna_net,
                'consumers': []
            }
        }
    }


def publish_checkpoint(config, output_bundle, output_sha256=None, web_dir=None, store_root=None):
    output_bundle = Path(output_bundle).resolve()
    output_bundle.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output_bundle.exists():
        output_bundle.unlink()

    with tempfile.TemporaryDirectory(prefix='ziokt-checkpoint-publish-') as tmp:
        store = Path(store_root).resolve() if store_root else Path(tmp) / 'store'
        result = capture_pair(config, str(store), bundle=str(output_bundle), scope='explicit-signer-bootstrap')

    bundle_bytes = output_bundle.read_bytes()
    digest = hashlib.sha256(bundle_bytes).hexdigest()

    if output_sha256:
        output_sha256 = Path(output_sha256).resolve()
        output_sha256.write_text(f'{digest}  {output_bundle.name}\n')
    else:
        output_sha256 = output_bundle.with_name(output_bundle.name + '.sha256')
        output_sha256.write_text(f'{digest}  {output_bundle.name}\n')

    deployed_web = None
    if web_dir:
        web_path = Path(web_dir).resolve()
        web_path.mkdir(parents=True, exist_ok=True)
        target_bundle = web_path / output_bundle.name
        target_sha256 = web_path / output_sha256.name
        shutil.copyfile(output_bundle, target_bundle)
        target_bundle.chmod(0o644)
        shutil.copyfile(output_sha256, target_sha256)
        target_sha256.chmod(0o644)
        deployed_web = str(target_bundle)

    return {
        'schema': 'ziokt.checkpoint-publication-receipt.v1',
        'snapshot_hash': result['snapshot_hash'],
        'pair_commitment': result['pair_commitment'],
        'scope': 'explicit-signer-bootstrap',
        'verification_level': result['verification_level'],
        'chains': result['chains'],
        'bundle_path': str(output_bundle),
        'bundle_sha256': digest,
        'sha256_path': str(output_sha256),
        'deployed_web': deployed_web,
        'historical_validity_proved': False
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, help='Local checkpoint capture JSON configuration')
    parser.add_argument('--node-root', type=Path, default=Path('/home/admin/.local/share/ziokt-production'), help='Root directory of the running node')
    parser.add_argument('--output-bundle', type=Path, required=True, help='Output path for .zip checkpoint bundle')
    parser.add_argument('--output-sha256', type=Path, help='Output path for .zip.sha256 digest file')
    parser.add_argument('--web-dir', type=Path, help='Public web directory to copy the bundle and digest to')
    parser.add_argument('--store', type=Path, help='Checkpoint store directory')
    args = parser.parse_args()

    if args.config:
        config = json.loads(args.config.read_text())
        config['scope'] = 'explicit-signer-bootstrap'
    else:
        config = build_config_from_node_root(args.node_root)

    receipt = publish_checkpoint(
        config,
        args.output_bundle,
        output_sha256=args.output_sha256,
        web_dir=args.web_dir,
        store_root=args.store
    )
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
