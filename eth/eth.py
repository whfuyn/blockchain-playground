#!/usr/bin/python3
import os
import subprocess
import tempfile
import pathlib
import shutil
import json
import time

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
  "gasLimit": "8000000",
}
'''
# Example `extradata` and `alloc`
#   "extradata": "0x0000000000000000000000000000000000000000000000000000000000000000bf24AaE62D2495c0e6C0876618dbbB9E64a795A5D3066A63689FE7F9ec49cD0aFD0E5D61C37ce1600000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
#   "alloc": {
#     "bf24AaE62D2495c0e6C0876618dbbB9E64a795A5": { "balance": "300000" },
#     "D3066A63689FE7F9ec49cD0aFD0E5D61C37ce160": { "balance": "400000" }
#   }


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
        cmd = [
            'geth',
            '--datadir', tmpstore,
            'account', 'new',
            '--password', super_secret
        ]

        for _ in range(key_count):
            p = subprocess.run(cmd, text=True, check=True, capture_output=True)
            addr, sk_path = parse_key_output(p.stdout)

            to = os.path.join(keystore, addr)
            shutil.copyfile(sk_path, to)

            keys[addr] = to
    return keys


def gen_genesis(addrs):
    genesis = json.loads(genesis_block)

    # build extradata for clique, the Proof of Authority consensus engine
    ex_vanity = '0' * 32 * 2
    ex_seal = '0' * 65 * 2
    extradata = '0x' + ex_vanity + ''.join(addrs) + ex_seal
    genesis["extradata"] = extradata

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


def start_node(datadir, authority, password, networkid, port, bootnodes):
    networkid = str(networkid)
    port = str(port)
    log = open(os.path.join(datadir, 'geth.log'), 'a')
    start_cmd = [
        'geth',
        '--datadir', datadir,
        '--networkid', networkid,
        '--unlock', authority,
        '--password', password,
        '--mine',
        '--port', port,
        '--syncmode', 'full',
        '--bootnodes', ','.join(bootnodes),
    ]
    print(start_cmd)

    return subprocess.Popen(start_cmd, text=True, stdout=log, stderr=log)


def init_node(datadir, genesis, authority_sk, password):
    mkdirp(datadir)
    shutil.copy(password, datadir)

    keystore = os.path.join(datadir, 'keystore')
    mkdirp(keystore)
    shutil.copy(authority_sk, keystore)

    init_cmd = ['geth', '--datadir', datadir, 'init', genesis]
    subprocess.run(init_cmd, text=True, check=True, capture_output=True)


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
    genesis = gen_genesis(authorities)

    print("Initializing nodes data..")
    for addr, sk in authorities.items():
        datadir = os.path.join(nodes, addr)
        init_node(datadir, genesis, sk, super_secret)
    print("Finished. Authorities are ", list(authorities.keys()))


def start_net():
    nodes = os.path.join(output_dir, 'nodes')
    super_secret = os.path.join(output_dir, 'super_secret')

    networkid = 314159

    # node's datadir name is its miner(authority) address
    _, addrs, _ = next(os.walk(nodes))

    pid_list = []
    port = 30303
    node_handles = []

    # start nodes
    bootnodes = []
    for addr in addrs:
        datadir = os.path.join(nodes, addr)
        p = start_node(datadir, addr, super_secret, networkid, port, bootnodes)
        if not bootnodes:
            wait_time = 10
            print(f'Sleep {wait_time} seconds, wait for bootnode ready..')
            time.sleep(wait_time)
            bootnodes.append(get_node_url(datadir))
        pid_list.append(str(p.pid))
        node_handles.append(p)
        print(f'Node 0x{addr} started at port {port}.')
        port += 1

    with open(os.path.join(output_dir, 'pid_list'), 'wt') as f:
        f.write('\n'.join(pid_list))

    print('Local ethereum net started.')
    for h in node_handles:
        h.wait()


def get_node_url(datadir):
    ipc = os.path.join(datadir, 'geth.ipc')
    cmd = ['geth', 'attach', ipc, '--exec', 'admin.nodeInfo.enode']

    p = subprocess.run(cmd, text=True, check=True, capture_output=True)
    node_url = p.stdout.strip().strip('"')
    return node_url


def add_peer(datadir, peer_url):
    ipc = os.path.join(datadir, 'geth.ipc')
    add_peer = f'admin.addPeer("{peer_url}")'
    cmd = ['geth', 'attach', ipc, '--exec', add_peer]

    subprocess.run(cmd, text=True, check=True, stdout=subprocess.DEVNULL)


def stop_net():
    pid_list = os.path.join(output_dir, 'pid_list')
    if os.path.exists(pid_list):
        with open(pid_list, 'rt') as f:
            for l in f.read().splitlines():
                subprocess.run(['kill', l])


def remove_net():
    shutil.rmtree(output_dir)


def main():
    # print('stop net')
    # stop_net()
    # print('removing net')
    # remove_net()
    if not os.path.exists(output_dir):
        print('init net')
        init_net(4)
    print('start net')
    start_net()


if __name__ == '__main__':
    main()
