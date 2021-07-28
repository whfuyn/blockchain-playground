#!/usr/bin/python3
import os
import subprocess
import tempfile
import pathlib
import shutil
import json
import time
import argparse

output_dir = os.path.join(os.getcwd(), "tutorial-net")

genesis_block = '''
{
  "config": {
    "chainId": 20210618,
    "homesteadBlock": 0,
    "eip150Block": 0,
    "eip155Block": 0,
    "eip158Block": 0,
    "byzantiumBlock": 0,
    "constantinopleBlock": 0,
    "petersburgBlock": 0,
    "clique": {
      "period": 5,
      "epoch": 30000
    }
  },
  "difficulty": "1",
  "gasLimit": "8000000"
}
'''
# Example `extradata` and `alloc`
#   "extradata": "0x0000000000000000000000000000000000000000000000000000000000000000bf24AaE62D2495c0e6C0876618dbbB9E64a795A5D3066A63689FE7F9ec49cD0aFD0E5D61C37ce1600000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
#   "alloc": {
#     "bf24AaE62D2495c0e6C0876618dbbB9E64a795A5": { "balance": "300000" },
#     "D3066A63689FE7F9ec49cD0aFD0E5D61C37ce160": { "balance": "400000" }
#   }


def run_cmd(cmd):
    try:
        p = subprocess.run(cmd, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(e.stderr)
    return p.stdout.strip()


def spawn_cmd(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
    return subprocess.Popen(
        cmd, text=True, stdout=stdout, stderr=stderr
    )


def parse_key_output(output):
    addr_begin = 'Public address of the key:   '
    sk_begin = 'Path of the secret key file: '

    addr = next(
        l.lstrip(addr_begin)
        for l in output.splitlines() if l.startswith(addr_begin)
    )
    sk_path = next(
        l.lstrip(sk_begin)
        for l in output.splitlines() if l.startswith(sk_begin)
    )
    return (remove_0x(addr), sk_path)


def gen_keys(key_count, keystore):
    mkdirp(keystore)

    keys = {}
    with tempfile.TemporaryDirectory() as tmpstore:
        super_secret = os.path.join(output_dir, 'super_secret')
        create_cmd = [
            'geth',
            '--datadir', tmpstore,
            'account', 'new',
            '--password', super_secret
        ]

        for _ in range(key_count):
            key_output = run_cmd(create_cmd)
            addr, sk_path = parse_key_output(key_output)

            to = os.path.join(keystore, addr)
            shutil.copyfile(sk_path, to)

            keys[addr] = to
    return keys


def gen_genesis(addrs):
    # TODO:
    # I'm not sure whether this sorting is correct.
    # But it seems to work regardless of my sorting.
    # EIP-225 (https://eips.ethereum.org/EIPS/eip-225) says:
    # "The list of signers in checkpoint block extra-data sections
    #  must be sorted in ascending order."
    addrs = sorted(addrs, key=lambda addr: int(addr, 16))
    genesis = json.loads(genesis_block)

    # build extradata for clique, the Proof of Authority consensus engine
    extra_vanity = '0' * 32 * 2
    extra_seal = '0' * 65 * 2
    genesis["extradata"] = '0x' + extra_vanity + ''.join(addrs) + extra_seal

    # build init balance
    balance = {
        # 100 ether
        addr: {"balance": str(100 * 10**18)}
        for addr in addrs
    }
    genesis["alloc"] = balance

    # write genesis
    genesis_path = os.path.join(output_dir, "genesis.json")
    with open(genesis_path, "w") as f:
        f.write(json.dumps(genesis, indent=2))

    return genesis_path


def remove_0x(s):
    return s[2:] if s.startswith('0x') else s


def mkdirp(d):
    pathlib.Path(d).mkdir(parents=True, exist_ok=True)


def start_node(
    datadir, authority, password,
    networkid, port, rpc_port, vhosts,
    bootnodes
):
    networkid = str(networkid)
    log = open(os.path.join(datadir, 'geth.log'), 'a')
    start_cmd = [
        'geth',
        '--datadir', datadir,
        '--networkid', networkid,
        '--unlock', authority,
        '--password', password,
        '--mine',
        '--port', str(port),
        '--http',
        '--http.addr', "0.0.0.0",
        '--http.port', str(rpc_port),
        '--http.api', 'db,eth,net,web3,personal',
        '--http.corsdomain', '*',
        '--http.vhosts', ','.join(vhosts),
        '--allow-insecure-unlock',
        '--syncmode', 'full',
        '--bootnodes', ','.join(bootnodes),
    ]

    return spawn_cmd(start_cmd, log, log)


def init_node(datadir, genesis, authority_sk, password):
    mkdirp(datadir)
    shutil.copy(password, datadir)

    keystore = os.path.join(datadir, 'keystore')
    mkdirp(keystore)
    shutil.copy(authority_sk, keystore)

    init_cmd = ['geth', '--datadir', datadir, 'init', genesis]
    run_cmd(init_cmd)


def init_net(authority_count):
    mkdirp(output_dir)

    nodes = os.path.join(output_dir, 'nodes')
    keystore = os.path.join(output_dir, 'keys')

    super_secret = os.path.join(output_dir, 'super_secret')
    with open(super_secret, 'wt') as f:
        f.write('woshiyizhidahuamao')

    print("Generating authority keys..")
    authorities = gen_keys(authority_count, keystore)

    print("Generating genesis block..")
    genesis = gen_genesis(authorities.keys())

    print("Initializing nodes data..")
    for addr, sk in authorities.items():
        datadir = os.path.join(nodes, addr)
        init_node(datadir, genesis, sk, super_secret)
    print("Finished. Authorities are ", list(authorities.keys()))


def start_net(vhosts):
    nodes = os.path.join(output_dir, 'nodes')
    super_secret = os.path.join(output_dir, 'super_secret')

    networkid = 314159

    # node's datadir name is its miner(authority) address
    _, addrs, _ = next(os.walk(nodes))

    pid_list = []
    port = 30303
    rpc_port = 8545
    node_handles = []

    # start nodes
    bootnodes = []
    for addr in addrs:
        datadir = os.path.join(nodes, addr)
        p = start_node(
            datadir, addr, super_secret,
            networkid, port, rpc_port, vhosts,
            bootnodes
        )
        if not bootnodes:
            while True:
                try:
                    wait_time = 5
                    print(
                        f'Sleep {wait_time} seconds, wait for bootnode ready..'
                    )
                    time.sleep(wait_time)
                    bootnodes.append(get_node_url(datadir))
                    break
                except RuntimeError as e:
                    if 'connection refused' in str(e):
                        print("bootnode haven't started yet, retrying..")
                    else:
                        raise e
        pid_list.append(str(p.pid))
        node_handles.append(p)
        print(f'Node 0x{addr} started at port {port} and rpc_port {rpc_port}.')
        port += 1
        rpc_port += 1

    with open(os.path.join(output_dir, 'pid_list'), 'wt') as f:
        f.write('\n'.join(pid_list))

    print('Local ethereum net started.')
    for h in node_handles:
        h.wait()


def get_node_url(datadir):
    ipc = os.path.join(datadir, 'geth.ipc')
    node_url = run_cmd(
        ['geth', 'attach', ipc, '--exec', 'admin.nodeInfo.enode']
    ).strip('"')
    return node_url


def stop_net():
    pid_list = os.path.join(output_dir, 'pid_list')
    if os.path.exists(pid_list):
        with open(pid_list, 'rt') as f:
            for l in f.read().splitlines():
                run_cmd(['kill', l])


def remove_net():
    shutil.rmtree(output_dir)


def main():
    parser = argparse.ArgumentParser(
        description='Sample Ethereum PoA network.'
    )
    parser.add_argument(
        '--authority_num',
        type=int,
        help='the number of authority for this PoA network',
        default=4,
    )
    parser.add_argument(
        '--vhosts',
        nargs='+',
        help='the list of the vhosts to serve RPC requests',
        default=['localhost'],
    )

    args = parser.parse_args()
    authority_num = args.authority_num
    vhosts = args.vhosts

    if not os.path.exists(output_dir) or not os.listdir(output_dir):
        print(f'Initializing a new network with {authority_num} authorities..')
        init_net(authority_num)
    else:
        print('The network is already intitialized.')

    print('start net')
    start_net(vhosts)


if __name__ == '__main__':
    main()
