"""Review hosted testnet memory with owner authority kept on this Mac."""
import argparse
import fcntl
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError
from eth_account import Account

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from owner_cli import Owner, proposal_view, public_json, review_view
from memory import require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('inbox', help='Show signed proposals and verified resolution status')
    commands.add_parser('apps', help='Show current application permissions')
    commands.add_parser('resume', help='Reconcile or resend the exact previously confirmed request')
    for name in ('approve', 'reject', 'revoke'):
        sub = commands.add_parser(name, help='Review before confirming this change')
        sub.add_argument('id', help='Full proposal ID or application address')
        sub.add_argument('--confirm', metavar='CHECKPOINT', help='Confirm the exact checkpoint shown by a previous preview')
    args = parser.parse_args()
    # Help and parsing need no Keychain access. The MCP bridge never imports this module.
    from hosted import secrets, DIRECTORY, ORIGIN, public_state, save_report
    wallet, host = secrets()
    config = {**host['config'], 'serviceId': host['serviceId'], 'registry': {'rpcUrl': 'https://testnet-rpc.monad.xyz'}}
    require(config['domain']['chainId'] == 10143, 'TESTNET_REQUIRED')
    owner = Owner(ORIGIN, config, wallet['ownerKey'], bytes.fromhex(wallet['recoveryKey']), DIRECTORY / 'owner-cli')
    with open(owner.directory / 'operator.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'inbox':
            before = owner.current()
            print(public_json({'sequence': before['control']['sequence'], 'checkpoint': before['checkpoint']['controlDigest'], 'proposals': [proposal_view(i, before) for i in owner.inbox(before)]}))
            return
        if args.command == 'apps':
            import time
            before = owner.current()
            names = {Account.from_key(wallet[k]).address.lower(): label for k, label in [('planningKey', 'Planning reference client'), ('codingKey', 'Coding reference client')]}
            for name,label in [('claude-code','Claude Code'),('codex','Codex')]:
                profile = DIRECTORY / name / 'profile.json'
                if profile.exists():
                    names[json.loads(profile.read_text())['application']] = label
            grants = {g['application']: g for g in before['control']['grants']}
            apps = []
            for address in sorted(set(names) | set(grants)):
                grant = grants.get(address)
                apps.append({'application': address, 'label': names.get(address, 'Application'), 'status': 'not granted' if grant is None else 'expired' if int(grant['expiresAt']) < int(time.time()) else 'active', 'grant': grant})
            print(public_json({'sequence': before['control']['sequence'], 'applications': apps}))
            return
        if args.command == 'resume':
            result = owner.resume()
        else:
            # A supplied confirmation must reference the saved preview, never a new review.
            if args.confirm:
                state = owner.load()
                require(state is not None and state['action'] == args.command and state['target'] == args.id.lower(), 'CONFIRMATION_MISMATCH')
            else:
                state = owner.prepare(args.command, args.id)
            print(public_json(review_view(state)), flush=True)
            confirmation = args.confirm
            if confirmation is None and sys.stdin.isatty():
                confirmation = input('To sign this exact change, paste its full confirmation value (Enter cancels): ').strip()
            if not confirmation:
                print('Preview only. No approval signed or committed. Run the same command with --confirm followed by the confirmation value to approve this exact review.')
                return
            result = owner.confirm(confirmation)
        print(public_json(result), flush=True)
        # Keep the hosted read-check expectation aligned, using fresh verified current records.
        current = owner.current()
        report = public_state()
        report.update(acceptedDigest=current['checkpoint']['controlDigest'], expectedRecords=current['records'])
        if 'backup' in report:
            report['backup']['current'] = False
        save_report(report)


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        if isinstance(error, HTTPError):
            try:
                code = json.load(error).get('code', 'SERVICE_UNAVAILABLE')
            except Exception:
                code = 'SERVICE_UNAVAILABLE'
        else:
            code = str(error) if isinstance(error, ValueError) else type(error).__name__
        if not isinstance(code, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', code):
            code = 'OPERATION_INTERRUPTED'
        hints = {'AUTHORITY_UNAVAILABLE': 'The chain could not be freshly verified. Retry the preview shortly; use resume if you already confirmed.',
                 'CONTENT_UNAVAILABLE': 'Required memory content is unavailable. No unverified preview is shown; use resume if you already confirmed.',
                 'BASE_CONFLICT': 'The accepted revision changed. Review again; stale proposals need resubmission by their author.',
                 'REVIEW_EXPIRED': 'This review expired. An unsigned preview can be prepared again. For a signed request, run resume to reconcile; do not delete its journal.',
                 'RESUME_REQUIRED': 'Run ./memory resume before preparing another change.',
                 'COMMIT_PENDING': 'Acceptance is not yet verified. Run ./memory resume.',
                 'CONFIRMATION_MISMATCH': 'Use the exact action, ID and confirmation value from your saved preview.',
                 'ALREADY_RESOLVED': 'This proposal already has an owner resolution.'}
        print(public_json({'code': code, 'help': hints.get(code, 'No success claimed. If you confirmed a change, run ./memory resume to check it before trying another action.')}), file=sys.stderr)
        sys.exit(1)
