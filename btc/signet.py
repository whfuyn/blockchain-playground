import os
import subprocess
import tempfile
import time
import json
import pathlib
import shutil


def mkdirp(d):
    pathlib.Path(d).mkdir(parents=True, exist_ok=True)


def remove_0x(s):
    return s[2:] if s.startswith('0x') else s


class Account:
    def __init__(self, addr, pubkey, privkey):
        self.addr = addr
        self.pubkey = pubkey
        self.privkey = privkey


def build_signet_challenge(signer_pubkeys, required_sigs):
    # m of n multisig
    m = required_sigs
    n = len(signer_pubkeys)

    if not (0 < n < 16):
        raise RuntimeError("invalid signers num, must be in [1, 16]")

    if not (0 < m <= n):
        raise RuntimeError(
            "invalid required_sigs, must be in [1, signer_pubkeys]"
        )

    # This script is constructed according to https://en.bitcoin.it/wiki/Signet
    sig_cnt = remove_0x(hex(int('51', 16) + (n - 1)))
    pk_len = remove_0x(hex(n * 33))
    pks = ''.join(signer_pubkeys)
    pk_cnt = remove_0x(hex(m))
    op = 'ae'

    script = f'{sig_cnt}{pk_len}{pks}{pk_cnt}{op}'
    return script


def build_bitcoin_conf(signet_challenge, port, rpc_port, bootnodes):
    conf = [
        'signet=1',
        '[signet]',
        'daemon=1',
        f'signetchallenge={signet_challenge}',
        f'port={port}',
        f'rpcport={rpc_port}',
    ]
    conf.extend(f'addnode={bootnode}' for bootnode in bootnodes)

    return '\n'.join(conf)


def run_cmd(cmd):
    try:
        p = subprocess.run(cmd, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(e.stderr)
    return p.stdout.strip()


def spawn_cmd(cmd):
    return subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def gen_accounts(account_cnt):
    accounts = []

    with tempfile.TemporaryDirectory() as tmpstore:
        mkdirp(tmpstore)

        # use tmp port to avoid port clash
        tmpport = 21555
        tmprpcport = 22555

        # common cmd
        cli_cmd = [
            'bitcoin-cli',
            '-regtest',
            f'-datadir={tmpstore}',
            f'-rpcport={tmprpcport}',
        ]
        bitcoind_cmd = [
            'bitcoind',
            '-regtest',
            f'-datadir={tmpstore}',
            f'-port={tmpport}',
            f'-rpcport={tmprpcport}',
        ]

        bitcoind = spawn_cmd(bitcoind_cmd)

        # wait for bitcoind start
        time.sleep(5)

        # create wallet
        tmpwallet = 'tmpwallet'
        run_cmd([*cli_cmd, 'createwallet', tmpwallet])

        for _ in range(account_cnt):
            new_addr = run_cmd([*cli_cmd, 'getnewaddress', '', 'bech32'])
            pubkey = json.loads(
                run_cmd([*cli_cmd, 'getaddressinfo', new_addr])
            )['pubkey']
            privkey = run_cmd([*cli_cmd, 'dumpprivkey', new_addr])
            accounts.append(Account(new_addr, pubkey, privkey))

        run_cmd([*cli_cmd, 'stop'])
        bitcoind.wait(5)

    return accounts


def init_issuer(
    datadir, account, signet_challenge, port, rpc_port, bootnodes
):
    mkdirp(datadir)
    addr, pubkey, privkey = account.addr, account.pubkey, account.privkey
    addr_file = os.path.join(datadir, 'address')
    with open(addr_file, 'wt') as f:
        f.write(addr)

    pubkey_file = os.path.join(datadir, 'pubkey')
    with open(pubkey_file, 'wt') as f:
        f.write(pubkey)

    privkey_file = os.path.join(datadir, 'privkey')
    with open(privkey_file, 'wt') as f:
        f.write(privkey)

    conf_file = os.path.join(datadir, 'bitcoin.conf')
    with open(conf_file, 'wt') as f:
        f.write(
            build_bitcoin_conf(signet_challenge, port, rpc_port, bootnodes)
        )


def init_net(output_dir, issuer_cnt):
    print('initializing bitcoin signet..')
    mkdirp(output_dir)

    print('generating accounts..')
    issuers = gen_accounts(issuer_cnt)
    print('build signet challenge..')
    signet_challenge = build_signet_challenge(
        [issuer.pubkey for issuer in issuers],
        len(issuers)
    )

    print('initializing issuers..')
    basic_port = 19555
    basic_rpc_port = 20555
    bootnodes = []
    for i, issuer in enumerate(issuers):
        datadir = os.path.join(output_dir, 'issuers', str(i))
        port = basic_port + 10 * i
        rpc_port = basic_rpc_port + 10 * i

        init_issuer(
            datadir, issuer, signet_challenge,
            port, rpc_port, bootnodes
        )

        # Use the first node as bootnode
        if not bootnodes:
            bootnodes.append(f'127.0.0.1:{port}')

    print('bitcoin signet initialized.')


def start_issuer(datadir):
    cmd = [
        'bitcoind',
        f'-datadir={datadir}',
        '-daemon'
    ]
    return run_cmd(cmd)


def start_net(net_dir):
    # start issuers
    issuers_dir = os.path.join(net_dir, 'issuers')
    _, issuers, _ = next(os.walk(issuers_dir))

    for issuer in issuers:
        datadir = os.path.join(issuers_dir, issuer)
        start_issuer(datadir)


def clear_net(net_dir):
    if os.path.exists(net_dir):
        pid_list = os.path.join(net_dir, 'pid_list')
        with open(pid_list, 'rt') as f:
            for l in f.read().splitlines():
                subprocess.run(['kill', l])
        shutil.rmtree(net_dir)


def main():
    outpudir = os.path.join(os.getcwd(), 'bitcoin_signet')
    if not os.path.exists(outpudir):
        init_net(outpudir, 4)


if __name__ == '__main__':
    main()
